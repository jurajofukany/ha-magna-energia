"""Data fetching for the Magna Energia iPortal integration.

Unlike ZSD's diportal (see custom_components/diportal/), the Magna Energia customer portal
(iportal.magna-energia.sk) has a plain username/password login with NO captcha and no CSRF
token - so this integration logs in for itself on every refresh instead of importing a
session captured externally. A fresh aiohttp session (with its own cookie jar) is opened,
used for one login + a handful of ajax/load.php calls, and closed again at the end of each
coordinator refresh; nothing is persisted across polls.

Reverse-engineered endpoints (see js/scripts.min.js served by the portal, and live traffic
captured while logged in):
  - POST /ajax/login.php   {login, heslo}                 -> {"err": false, "text": "Login ok"}
  - POST /ajax/load.php    {chartType, date, interval,
                            typ, eic, granularity,
                            poradie[], force}              -> JSON with data_sets + text_sumar

/ajax/load.php's response content-type header is (incorrectly) "text/html" even though the
body is JSON, so we always parse the raw text ourselves rather than relying on aiohttp's
content-type sniffing.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
import json
import logging
import re
from typing import Any

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    BAND_LABELS_SK,
    CHART_TYPE_LINES,
    CHART_TYPE_STACKED,
    DAY_LAG_DAYS,
    DEFAULT_SCAN_INTERVAL,
    DELIVERY_POINTS,
    DOMAIN,
    EP_LOAD,
    EP_LOGIN,
    GRANULARITY_15MIN,
    GRANULARITY_DAY,
    GRANULARITY_HOUR,
    INTERVAL_DAY,
    INTERVAL_MONTH,
    PORTAL_BASE_URL,
    TARIFF_TYPE_4T,
)

_LOGGER = logging.getLogger(__name__)

_STATIC_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "sk-SK,sk;q=0.9,en;q=0.8",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": f"{PORTAL_BASE_URL}/",
    "Origin": PORTAL_BASE_URL,
    "X-Requested-With": "XMLHttpRequest",
}

_SUMAR_ROW_RE = re.compile(r"<td>([^<]+)</td>\s*<td class='num'>([^<]+)</td>")
_SUMAR_VALUE_RE = re.compile(r"^(-?[\d.,]+)\s*(kWh|kW|EUR)?$")


class MagnaAuthError(Exception):
    """Login was rejected (bad username/password)."""


class MagnaConnectionError(Exception):
    """Network error, or the portal returned something we didn't expect."""


async def _async_post(session: aiohttp.ClientSession, path: str, form: aiohttp.FormData) -> dict:
    """POST to one of Magna's ajax/*.php endpoints and parse the JSON body.

    The endpoints always answer 200 with a JSON body, even for auth/validation errors -
    the "text/html" content-type header they send is misleading and ignored here.
    """
    url = f"{PORTAL_BASE_URL}{path}"
    try:
        async with session.post(url, data=form, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            resp.raise_for_status()
            raw = await resp.text()
    except aiohttp.ClientError as err:
        raise MagnaConnectionError(f"Nepodarilo sa spojiť s portálom Magna Energia ({path}): {err}") from err

    try:
        return json.loads(raw)
    except json.JSONDecodeError as err:
        raise MagnaConnectionError(
            f"Neočakávaná odpoveď portálu ({path}): {raw[:200]!r}"
        ) from err


async def async_login(session: aiohttp.ClientSession, username: str, password: str) -> None:
    """Log in; raises MagnaAuthError for bad credentials, MagnaConnectionError otherwise."""
    form = aiohttp.FormData()
    form.add_field("login", username)
    form.add_field("heslo", password)

    payload = await _async_post(session, EP_LOGIN, form)
    if payload.get("err"):
        raise MagnaAuthError(payload.get("text") or "Prihlásenie zlyhalo")


async def async_load(
    session: aiohttp.ClientSession,
    eic_index: int,
    interval: int,
    granularity: int,
    chart_type: str,
    date_str: str,
) -> dict:
    """Call ajax/load.php for one delivery point / period / view combination."""
    form = aiohttp.FormData()
    form.add_field("chartType", chart_type)
    form.add_field("date", date_str)
    form.add_field("interval", str(interval))
    form.add_field("typ", TARIFF_TYPE_4T)
    form.add_field("eic", str(eic_index))
    # Band display order - doesn't change the data, but the portal expects the field.
    for series_id in ("4", "3", "2", "1"):
        form.add_field("poradie[]", series_id)
    form.add_field("force", "0")
    form.add_field("granularity", str(granularity))

    payload = await _async_post(session, EP_LOAD, form)
    if payload.get("err"):
        # We always log in immediately before calling this, so an auth-shaped error here would
        # be unusual - most likely a transient portal-side issue - but surface it either way.
        raise MagnaConnectionError(f"Portál vrátil chybu pre ajax/load.php: {payload.get('text')}")
    return payload


def _parse_sumar_value(raw: str) -> float | str:
    """Parse one 'text_sumar' cell, e.g. '22.64 kWh' -> 22.64, '22.08.2026 12:00' -> unchanged."""
    raw = raw.strip()
    match = _SUMAR_VALUE_RE.match(raw)
    if not match or not match.group(2):
        return raw
    return float(match.group(1).replace(",", "."))


def parse_text_sumar(html: str) -> dict[str, float | str]:
    """Parse the small 'text_sumar' HTML summary table the portal embeds in every load.php reply."""
    return {label.strip(): _parse_sumar_value(value) for label, value in _SUMAR_ROW_RE.findall(html)}


def compute_band_metrics(payload: dict, period_label_sk: str) -> dict[str, Any]:
    """Extract per-band + total kWh (and, if present, EUR cost) for one day/month reply.

    period_label_sk is "deň" or "mesiac" - it's how the portal's own summary table labels
    the row, e.g. "Celková spotreba za deň" / "Celková spotreba za mesiac".
    """
    summary = parse_text_sumar(payload.get("text_sumar") or "")
    params = payload.get("params") or {}

    metrics: dict[str, Any] = {
        "date_from": params.get("dateFrom"),
        "date_to": params.get("dateTo"),
        "total_kwh": summary.get(f"Celková spotreba za {period_label_sk}"),
        "total_eur": summary.get(f"Celkové náklady v 4T za {period_label_sk}"),
    }
    for band_key, band_label in BAND_LABELS_SK.items():
        metrics[f"{band_key}_kwh"] = summary.get(band_label)
    return metrics


def compute_peak_power_metrics(payload: dict) -> dict[str, Any]:
    """Extract the 'KAPACITY' view's peak-power figure + when it happened."""
    summary = parse_text_sumar(payload.get("text_sumar") or "")
    max_at_raw = summary.get("Maximum - dátum")
    max_at: datetime | None = None
    if isinstance(max_at_raw, str):
        try:
            naive = datetime.strptime(max_at_raw, "%d.%m.%Y %H:%M")
        except ValueError:
            naive = None
        if naive is not None:
            # The portal returns this as a plain local timestamp with no timezone info.
            # SensorDeviceClass.TIMESTAMP requires a tz-aware datetime, so attach HA's
            # configured local timezone (the best available assumption for a Slovak portal).
            max_at = naive.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
    return {
        "max_power_kw": summary.get("Maximum - výkon"),
        "max_power_at": max_at,
    }


class MagnaCoordinator(DataUpdateCoordinator[dict[str, dict]]):
    """Logs in and fetches day/month (and, where applicable, peak-power) metrics per point."""

    def __init__(self, hass: HomeAssistant, username: str, password: str) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=DEFAULT_SCAN_INTERVAL,
        )
        self._username = username
        self._password = password

    async def _async_update_data(self) -> dict[str, dict]:
        target_date = date.today() - timedelta(days=DAY_LAG_DAYS)
        date_str = target_date.isoformat()

        async with aiohttp.ClientSession(
            headers=_STATIC_HEADERS, cookie_jar=aiohttp.CookieJar()
        ) as session:
            try:
                await async_login(session, self._username, self._password)
            except MagnaAuthError as err:
                raise ConfigEntryAuthFailed(f"Prihlásenie do Magna Energia iPortal zlyhalo: {err}") from err
            except MagnaConnectionError as err:
                raise UpdateFailed(str(err)) from err

            results: dict[str, dict] = {}
            for point_key, point in DELIVERY_POINTS.items():
                try:
                    metrics: dict[str, Any] = {}

                    # The stacked (4T time-band) view is the source of the plain kWh totals
                    # too, so it's fetched for every point - see the "band_sensors" comment
                    # in const.py for which points also get a per-band sensor breakdown.
                    day_payload = await async_load(
                        session,
                        point["eic_index"],
                        INTERVAL_DAY,
                        GRANULARITY_HOUR,
                        CHART_TYPE_STACKED,
                        date_str,
                    )
                    month_payload = await async_load(
                        session,
                        point["eic_index"],
                        INTERVAL_MONTH,
                        GRANULARITY_DAY,
                        CHART_TYPE_STACKED,
                        date_str,
                    )
                    metrics["day"] = compute_band_metrics(day_payload, "deň")
                    metrics["month"] = compute_band_metrics(month_payload, "mesiac")

                    if point["peak_power"]:
                        peak_payload = await async_load(
                            session,
                            point["eic_index"],
                            INTERVAL_MONTH,
                            GRANULARITY_15MIN,
                            CHART_TYPE_LINES,
                            date_str,
                        )
                        metrics["peak"] = compute_peak_power_metrics(peak_payload)

                    results[point_key] = metrics
                except MagnaConnectionError as err:
                    _LOGGER.warning("Nepodarilo sa načítať dáta pre %s: %s", point_key, err)

        if not results:
            raise UpdateFailed("Nepodarilo sa načítať žiadne dáta z portálu Magna Energia")

        return results
