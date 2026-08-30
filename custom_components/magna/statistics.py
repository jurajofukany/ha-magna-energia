"""Push Magna Energia's per-day totals into Home Assistant long-term statistics.

iPortal only exposes settled totals, and a given day's real values land several days late
(see ``const.DAY_LAG_DAYS``), so a live "today" sensor is always ~0. The month view, however,
already returns a per-day, per-band breakdown in its ``data_sets``. We turn that into one
external statistic per delivery point and 4T band (plus a total) and import it with each
day's real timestamp.

The whole month - plus the previous one - is re-imported on every coordinator refresh, so
late settlement just overwrites the affected days and HA recomputes the running sum.

External statistic ids are ``magna:<point>_<key>`` (e.g. ``magna:spotreba_total``,
``magna:vyroba_noc``); they show up under Developer Tools -> Statistics, in the Statistics
Graph card, and can be added to the Energy dashboard.
"""
from __future__ import annotations

from datetime import datetime, timedelta
import logging

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    statistics_during_period,
)
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import BAND_KEYS, BAND_SERIES_ID_TO_KEY, DELIVERY_POINTS, DOMAIN

_LOGGER = logging.getLogger(__name__)

# statistic key -> Slovak label fragment used in the statistic's display name
_STAT_LABELS_SK: dict[str, str] = {
    "total": "spolu",
    "rano_vecer": "Ráno/Večer",
    "dopoludnie": "Dopoludnie",
    "popoludnie": "Popoludnie",
    "noc": "Noc",
}


def parse_daily_bands(month_payload: dict) -> dict[str, dict[str, float]]:
    """Month ``data_sets`` -> ``{"YYYY-MM-DD": {"rano_vecer": kWh, ..., "total": kWh}}``.

    Each of the 4 series carries ``nazov`` = band id ("1".."4", see BAND_SERIES_ID_TO_KEY)
    and ``data`` = ``[[day_of_month, kWh], ...]``. The calendar month comes from
    ``params.dateFrom``.
    """
    data = month_payload.get("data") or {}
    params = month_payload.get("params") or {}
    first = dt_util.parse_date(params.get("dateFrom") or "")
    if first is None:
        return {}
    month_start = first.replace(day=1)

    per_day: dict[str, dict[str, float]] = {}
    for series in data.get("data_sets") or []:
        band_key = BAND_SERIES_ID_TO_KEY.get(str(series.get("nazov")))
        if band_key is None:
            continue
        for pair in series.get("data") or []:
            try:
                day_num = int(pair[0])
                value = float(pair[1])
            except (TypeError, ValueError, IndexError):
                continue
            day = month_start + timedelta(days=day_num - 1)
            if day.month != month_start.month:
                continue  # day index ran past the end of the month
            slot = per_day.setdefault(day.isoformat(), {key: 0.0 for key in BAND_KEYS})
            slot[band_key] = value

    for slot in per_day.values():
        slot["total"] = round(sum(slot[key] for key in BAND_KEYS), 3)
    return per_day


def combined_daily_bands(payloads: list[dict]) -> dict[str, dict[str, float]]:
    """Merge several month payloads (e.g. this month + last month) into one per-day map."""
    per_day: dict[str, dict[str, float]] = {}
    for payload in payloads:
        per_day.update(parse_daily_bands(payload))
    return per_day


def last_settled_iso(*per_days: dict[str, dict[str, float]]) -> str | None:
    """Latest ISO date carrying any non-zero total across the given per-day maps.

    The portal fills a day in days-to-weeks late, so this - not a fixed offset - is what
    "the last day we actually have data for" means in practice.
    """
    candidates = [
        iso
        for per_day in per_days
        for iso, slot in per_day.items()
        if slot.get("total", 0.0) > 0
    ]
    return max(candidates) if candidates else None


async def _baseline_sum(
    hass: HomeAssistant, statistic_id: str, before: datetime
) -> float:
    """Running sum of ``statistic_id`` accumulated strictly before ``before`` (0 if none)."""
    result = await get_instance(hass).async_add_executor_job(
        statistics_during_period,
        hass,
        dt_util.utc_from_timestamp(0),
        before,
        {statistic_id},
        "month",
        None,
        {"sum"},
    )
    rows = result.get(statistic_id) or []
    if rows and rows[-1].get("sum") is not None:
        return float(rows[-1]["sum"])
    return 0.0


async def async_import_daily_statistics(
    hass: HomeAssistant, month_payloads: dict[str, list[dict]]
) -> None:
    """Import per-day statistics for every delivery point from its month payload(s)."""
    for point_key, payloads in month_payloads.items():
        point = DELIVERY_POINTS.get(point_key)
        if point is None:
            continue

        per_day: dict[str, dict[str, float]] = {}
        for payload in payloads:
            per_day.update(parse_daily_bands(payload))
        if not per_day:
            continue

        stat_keys = ("total", *BAND_KEYS) if point["band_sensors"] else ("total",)
        window_start = dt_util.start_of_local_day(dt_util.parse_date(min(per_day)))

        for stat_key in stat_keys:
            statistic_id = f"{DOMAIN}:{point_key}_{stat_key}"
            metadata = StatisticMetaData(
                has_mean=False,
                has_sum=True,
                name=f"Magna {point['label']} – {_STAT_LABELS_SK[stat_key]}",
                source=DOMAIN,
                statistic_id=statistic_id,
                unit_of_measurement="kWh",
            )

            running = await _baseline_sum(hass, statistic_id, window_start)
            stats: list[StatisticData] = []
            for iso in sorted(per_day):
                value = per_day[iso].get(stat_key, 0.0)
                running = round(running + value, 3)
                stats.append(
                    StatisticData(
                        start=dt_util.start_of_local_day(dt_util.parse_date(iso)),
                        state=value,
                        sum=running,
                    )
                )

            async_add_external_statistics(hass, metadata, stats)
            _LOGGER.debug(
                "Magna štatistiky: %d dní importovaných pre %s", len(stats), statistic_id
            )
