"""Frankfurter API calls and small in-memory caches."""

from collections import OrderedDict
from datetime import date, timedelta
import json
from time import monotonic
from urllib.parse import urlencode

import streamlit as st

from api import get_url

BASE_URL = "https://api.frankfurter.app"

CURRENCIES_CACHE_TTL = 7 * 24 * 60 * 60
LATEST_RATE_CACHE_TTL = 60 * 60
HISTORICAL_RATE_CACHE_TTL = 30 * 24 * 60 * 60
TREND_CACHE_TTL_SECONDS = 7 * 24 * 60 * 60
TREND_CACHE_MAX_ENTRIES = 64

# Each trend entry stores the date ranges already downloaded and their daily
# rates. This lets overlapping requests fetch only the missing periods.
_TREND_CACHE = OrderedDict()


class _FrankfurterError(RuntimeError):
    """Internal exception so failed requests are never cached as valid data."""


def _load_json(url: str) -> dict:
    status_code, response_text = get_url(url)
    if status_code != 200:
        raise _FrankfurterError(response_text)
    try:
        payload = json.loads(response_text)
    except (json.JSONDecodeError, TypeError) as exc:
        raise _FrankfurterError("Frankfurter returned invalid JSON.") from exc
    if not isinstance(payload, dict):
        raise _FrankfurterError("Frankfurter returned an unexpected response.")
    return payload


def _normalise_currency(currency: str) -> str:
    code = str(currency).strip().upper()
    if len(code) != 3 or not code.isalpha():
        raise _FrankfurterError("Invalid currency code.")
    return code


def _normalise_date(value) -> str:
    value = value.isoformat() if hasattr(value, "isoformat") else str(value)
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise _FrankfurterError("Invalid date.") from exc

    if parsed > date.today():
        raise _FrankfurterError("Historical dates cannot be in the future.")
    return parsed.isoformat()


def _extract_rate(payload: dict, to_currency: str) -> float:
    rates = payload.get("rates")
    if not isinstance(rates, dict) or to_currency not in rates:
        raise _FrankfurterError("The requested rate was not returned.")

    rate = rates[to_currency]
    if not isinstance(rate, (int, float)) or rate <= 0:
        raise _FrankfurterError("The requested rate was invalid.")
    return float(rate)


@st.cache_data(ttl=CURRENCIES_CACHE_TTL, max_entries=1, show_spinner=False)
def _cached_currencies() -> list:
    payload = _load_json(f"{BASE_URL}/currencies")
    currencies = sorted(
        code.upper()
        for code in payload
        if isinstance(code, str) and len(code) == 3 and code.isalpha()
    )
    if not currencies:
        raise _FrankfurterError("No supported currencies were returned.")
    return currencies


def get_currencies_list():
    """
    Get the currency codes supported by Frankfurter.

    Returns
    -------
    list
        List of available currencies, or None if the API call fails.
    """
    try:
        return _cached_currencies()
    except _FrankfurterError:
        return None


@st.cache_data(ttl=LATEST_RATE_CACHE_TTL, max_entries=128, show_spinner=False)
def _cached_latest_unit_rate(from_currency: str, to_currency: str) -> tuple:
    query = urlencode({"from": from_currency, "to": to_currency})
    payload = _load_json(f"{BASE_URL}/latest?{query}")
    rate_date = payload.get("date")
    if not isinstance(rate_date, str):
        raise _FrankfurterError("The latest-rate response had no date.")
    return rate_date, _extract_rate(payload, to_currency)


def get_latest_rates(from_currency, to_currency, amount):
    """
    Get the latest unit conversion rate and its date.

    ``amount`` remains in the starter signature, but it is intentionally not
    part of the cache key because one unit rate can be reused for any amount.

    Returns
    -------
    str
        Date of the latest rate, or None on failure.
    float
        Latest unit rate, or None on failure.
    """
    del amount
    try:
        from_code = _normalise_currency(from_currency)
        to_code = _normalise_currency(to_currency)
        if from_code == to_code:
            return date.today().isoformat(), 1.0
        return _cached_latest_unit_rate(from_code, to_code)
    except _FrankfurterError:
        return None, None


@st.cache_data(
    ttl=HISTORICAL_RATE_CACHE_TTL,
    max_entries=512,
    show_spinner=False,
)
def _cached_historical_unit_rate(
    from_currency: str,
    to_currency: str,
    from_date: str,
) -> float:
    query = urlencode({"from": from_currency, "to": to_currency})
    payload = _load_json(f"{BASE_URL}/{from_date}?{query}")
    return _extract_rate(payload, to_currency)


def get_historical_rate(from_currency, to_currency, from_date, amount):
    """
    Get the unit conversion rate for a selected historical date.

    ``amount`` remains in the starter signature but is excluded from the cache
    key because it does not change the underlying unit rate.

    Returns
    -------
    float
        Historical unit rate, or None on failure.
    """
    del amount
    try:
        from_code = _normalise_currency(from_currency)
        to_code = _normalise_currency(to_currency)
        date_text = _normalise_date(from_date)
        if from_code == to_code:
            return 1.0
        return _cached_historical_unit_rate(from_code, to_code, date_text)
    except _FrankfurterError:
        return None


def _trend_cache_entry(from_currency: str, to_currency: str) -> dict:
    """Return a live trend entry and keep at most 64 currency pairs."""
    key = (from_currency, to_currency)
    now = monotonic()
    entry = _TREND_CACHE.get(key)

    if entry and entry["expires_at"] > now:
        _TREND_CACHE.move_to_end(key)
        return entry
    if entry:
        del _TREND_CACHE[key]
    while len(_TREND_CACHE) >= TREND_CACHE_MAX_ENTRIES:
        _TREND_CACHE.popitem(last=False)
    entry = {
        "expires_at": now + TREND_CACHE_TTL_SECONDS,
        "ranges": [],
        "rates": {},
    }
    _TREND_CACHE[key] = entry
    return entry


def _merge_ranges(ranges: list) -> list:
    """Merge overlapping or adjacent date ranges."""
    merged = []
    for start, end in sorted(ranges):
        if not merged or start > merged[-1][1] + timedelta(days=1):
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)
    return [(start, end) for start, end in merged]


def _missing_ranges(start: date, end: date, covered: list) -> list:
    """Return only the date windows not already represented by covered."""
    missing = []
    cursor = start
    for covered_start, covered_end in sorted(covered):
        if covered_end < cursor:
            continue
        if covered_start > end:
            break
        if covered_start > cursor:
            missing.append((cursor, min(covered_start - timedelta(days=1), end)))
        cursor = max(cursor, covered_end + timedelta(days=1))
        if cursor > end:
            break
    if cursor <= end:
        missing.append((cursor, end))
    return missing


def _fetch_trend_window(
    from_currency: str,
    to_currency: str,
    start: date,
    end: date,
) -> dict:
    """Fetch daily rates for one missing trend period."""
    query = urlencode({"from": from_currency, "to": to_currency})
    payload = _load_json(
        f"{BASE_URL}/{start.isoformat()}..{end.isoformat()}?{query}"
    )
    history = payload.get("rates")
    if not isinstance(history, dict):
        raise _FrankfurterError("The trend response had no rate history.")
    daily_rates = {}
    for rate_date, values in history.items():
        if not isinstance(values, dict):
            continue
        rate = values.get(to_currency)
        if not isinstance(rate, (int, float)) or rate <= 0:
            continue
        try:
            daily_rates[date.fromisoformat(rate_date)] = float(rate)
        except ValueError:
            continue
    if not daily_rates:
        raise _FrankfurterError("No usable trend rates were returned.")
    return daily_rates


def get_rate_trend(from_currency: str, to_currency: str, years: int) -> dict:
    """
    Fetch historical rates for the past N years on a quarterly basis.

    Overlapping requests reuse already downloaded daily data and call the API
    only for missing date ranges.

    Returns
    -------
    dict
        Dictionary containing quarterly dates and their corresponding rates.
    """
    try:
        years = int(years)
        if years <= 0:
            raise _FrankfurterError("Years must be positive.")
        from_code = _normalise_currency(from_currency)
        to_code = _normalise_currency(to_currency)
        today = date.today()
        try:
            start = today.replace(year=today.year - years)
        except ValueError:
            start = today.replace(year=today.year - years, month=2, day=28)
        if from_code == to_code:
            trend = {}
            for year in range(start.year, today.year + 1):
                for month in (1, 4, 7, 10):
                    point = date(year, month, 1)
                    if start <= point <= today:
                        trend[point.isoformat()] = 1.0
            return trend or {today.isoformat(): 1.0}
        entry = _trend_cache_entry(from_code, to_code)
        missing = _missing_ranges(start, today, entry["ranges"])
        for missing_start, missing_end in missing:
            entry["rates"].update(
                _fetch_trend_window(
                    from_code,
                    to_code,
                    missing_start,
                    missing_end,
                )
            )
            entry["ranges"] = _merge_ranges(
                entry["ranges"] + [(missing_start, missing_end)]
            )
        requested_rates = {
            rate_date: rate
            for rate_date, rate in entry["rates"].items()
            if start <= rate_date <= today
        }
        if not requested_rates:
            raise _FrankfurterError("No usable trend data was returned.")
        quarterly = {}
        for rate_date in sorted(requested_rates):
            quarter = (rate_date.year, (rate_date.month - 1) // 3 + 1)
            quarterly[quarter] = (rate_date, requested_rates[rate_date])
        return {
            rate_date.isoformat(): rate
            for rate_date, rate in quarterly.values()
        }
    except (_FrankfurterError, TypeError, ValueError):
        return {}