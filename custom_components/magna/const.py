"""Constants for the Magna Energia iPortal integration."""
from __future__ import annotations

from datetime import timedelta

DOMAIN = "magna"

PORTAL_BASE_URL = "https://iportal.magna-energia.sk"
EP_LOGIN = "/ajax/login.php"
EP_LOAD = "/ajax/load.php"

# Magna's iPortal (dodavatel/supplier) is a billing portal, not a telemetry feed - it only
# ever shows daily/monthly totals, never anything real-time. On top of that, the underlying
# interval data has a settlement lag: as of "today" the newest day with real (non-zero) values
# is consistently 2 days back (verified empirically - "yesterday" is still all zeros, the day
# before that already has real kWh). Polling more often than that would just re-read the same
# numbers, so every 4 hours is plenty to notice new data during the day without hammering the
# portal's login endpoint (we log in fresh on every refresh - see coordinator.py).
DEFAULT_SCAN_INTERVAL = timedelta(hours=4)
DAY_LAG_DAYS = 2

# ajax/load.php request parameters (reverse-engineered from js/scripts.min.js + live traffic).
INTERVAL_DAY = 1
INTERVAL_MONTH = 3

GRANULARITY_HOUR = 2
GRANULARITY_DAY = 3
# The only granularity that makes chartType=lines ("KAPACITY" / peak-power) return true
# instantaneous kW peaks - anything coarser silently degrades "Maximum - vykon" into an
# hourly/daily *energy* average (unit flips from kW to kWh) instead of an actual power peak.
GRANULARITY_15MIN = 1

CHART_TYPE_STACKED = "stacked"  # 4T time-band energy view (what we use for consumption/production)
CHART_TYPE_LINES = "lines"  # power-over-time view (what "KAPACITY" / rezervovana-kapacita uses)

# data.typ: "0" = 4T Univerzal (variable time-band tariff), "1" = standard 1T/2T.
# The account this integration was built against is on 4T Univerzal (see
# packages/ems_savings_statistics.yaml), so we always ask for typ=0.
TARIFF_TYPE_4T = "0"

# Time-band series id -> our internal key. Verified directly from the portal's own JSON
# (data.options.series_names) and from the legend markup (data-set attributes) on /spotreba:
#   1 = "Rano / Vecer", 2 = "Dopoludnie", 3 = "Popoludnie", 4 = "Noc"
# These match the 4 bands documented in packages/ems_savings_statistics.yaml for the
# MAGNA ENERGIA 4T Univerzal tariff (noc 22:00-06:00, rano/vecer 06:00-09:00 + 19:00-22:00,
# dopoludnie 09:00-13:00, popoludnie 13:00-19:00).
BAND_SERIES_ID_TO_KEY = {
    "1": "rano_vecer",
    "2": "dopoludnie",
    "3": "popoludnie",
    "4": "noc",
}
BAND_KEYS: tuple[str, ...] = ("rano_vecer", "dopoludnie", "popoludnie", "noc")
BAND_LABELS_SK = {
    "rano_vecer": "Ráno / Večer",
    "dopoludnie": "Dopoludnie",
    "popoludnie": "Popoludnie",
    "noc": "Noc",
}

# The 3 "miesta" (delivery points / EICs) available on this account's "spotreba" page,
# identified by their dropdown index (data-value of .custom_select.miesto .option - this
# index, NOT the EIC string, is what the "eic" POST parameter to ajax/load.php actually wants).
#
# The day/month "stacked" (4T time-band) view is fetched for ALL THREE points - that's where
# even the plain totals come from - but not every point gets the full set of sensors:
#   band_sensors: expose the 4 individual time-band sensors (not just the total). Skipped for
#         pozicovna: the "borrowed electricity" it tracks is only meaningfully a single
#         returned-energy total, and per-band numbers there stay 0 all month until invoicing
#         (see the portal's own warning text for this option) - so a per-band breakdown would
#         mostly just be 4 empty sensors.
#   cost: whether the portal's own "Celkove naklady v 4T" EUR figure is meaningful for this
#         point (it is only ever "0.00 EUR" for vyroba/pozicovna - Magna doesn't cost out
#         production/returned energy the same way as consumption - so we don't expose it there).
#   peak_power: whether the "KAPACITY" (chartType=lines) view makes sense for this point.
#         Pozicovna (borrowed/returned electricity) has no meaningful "power" curve, so we
#         keep it to plain kWh totals only.
DELIVERY_POINTS: dict[str, dict] = {
    "spotreba": {
        "eic_index": 0,
        "eic": "24ZZS5245061000Q",
        "label": "Spotreba (odber zo siete)",
        "band_sensors": True,
        "cost": True,
        "peak_power": True,
    },
    "vyroba": {
        "eic_index": 2,
        "eic": "24ZZSVYR00347858",
        "label": "Prebytok výroby",
        "band_sensors": True,
        "cost": False,
        "peak_power": True,
    },
    "pozicovna": {
        "eic_index": 1,
        "eic": "POZZSVYR00347858",
        "label": "Požičovňa (vrátená elektrina)",
        "band_sensors": False,
        "cost": False,
        "peak_power": False,
    },
}
