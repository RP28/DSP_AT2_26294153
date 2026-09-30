"""Frankfurter API integration and bounded Streamlit caching."""

from datetime import date
import json
from urllib.parse import urlencode

import streamlit as st

from api import get_url

BASE_URL = "https://api.frankfurter.app"

CURRENCIES_CACHE_TTL = 7 * 24 * 60 * 60
CURRENCIES_CACHE_MAX_ENTRIES = 1
LATEST_RATE_CACHE_TTL = 60 * 60
LATEST_RATE_CACHE_MAX_ENTRIES = 128
HISTORICAL_RATE_CACHE_TTL = 30 * 24 * 60 * 60
HISTORICAL_RATE_CACHE_MAX_ENTRIES = 512
TREND_CACHE_TTL = 24 * 60 * 60
TREND_CACHE_MAX_ENTRIES = 64


class _FrankfurterError(RuntimeError):
    """Internal exception used so failed API calls are not cached as valid data."""


def _load_json(url: str) -> dict:
    """Fetch one Frankfurter URL and return a validated JSON object."""
    status_code, response_text = get_url(url)
    if status_code != 200:
        raise _FrankfurterError(response_text)
    try:
        payload = json.loads(response_text)
    except (json.JSONDecodeError, TypeError) as exc:
        raise _FrankfurterError("Frankfurter returned invalid JSON.") from exc
    if not isinstance(payload, dict):
        raise _FrankfurterError("Frankfurter returned an unexpected response shape.")
    return payload


def _normalise_currency(currency: str) -> str:
    """Normalise and minimally validate a currency code."""
    code = str(currency).strip().upper()
    if len(code) != 3 or not code.isalpha():
        raise _FrankfurterError("Invalid currency code.")
    return code


def _normalise_date(value) -> str:
    """Return an ISO date string and reject invalid or future dates."""
    value_text = value.isoformat() if hasattr(value, "isoformat") else str(value)
    try:
        parsed_date = date.fromisoformat(value_text)
    except (TypeError, ValueError) as exc:
        raise _FrankfurterError("Invalid date.") from exc
    if parsed_date > date.today():
        raise _FrankfurterError("Historical dates cannot be in the future.")
    return parsed_date.isoformat()


def _extract_rate(payload: dict, to_currency: str) -> float:
    """Extract one positive numeric rate from a v1 Frankfurter response."""
    rates = payload.get("rates")
    if not isinstance(rates, dict) or to_currency not in rates:
        raise _FrankfurterError("The requested rate was not present in the response.")
    rate = rates[to_currency]
    if not isinstance(rate, (int, float)) or rate <= 0:
        raise _FrankfurterError("The requested rate was invalid.")
    return float(rate)


@st.cache_data(
    ttl=CURRENCIES_CACHE_TTL,
    max_entries=CURRENCIES_CACHE_MAX_ENTRIES,
    show_spinner=False
)
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
    Function that will call the relevant API endpoint from Frankfurter in order to get the list of available currencies.
    After the API call, it will perform a check to see if the API call was successful.
    If it is the case, it will load the response as JSON, extract the list of currency codes and return it as Python list.
    Otherwise it will return the value None.

    Parameters
    ----------
    None

    Returns
    -------
    list
        List of available currencies or None in case of error
    """
    try:
        return _cached_currencies()
    except _FrankfurterError:
        return None


@st.cache_data(
    ttl=LATEST_RATE_CACHE_TTL,
    max_entries=LATEST_RATE_CACHE_MAX_ENTRIES,
    show_spinner=False,
)
def _cached_latest_unit_rate(from_currency: str, to_currency: str) -> tuple:
    query = urlencode({"from": from_currency, "to": to_currency})
    payload = _load_json(f"{BASE_URL}/latest?{query}")
    rate_date = payload.get("date")
    if not isinstance(rate_date, str):
        raise _FrankfurterError("The latest-rate response did not contain a date.")
    return rate_date, _extract_rate(payload, to_currency)


def get_latest_rates(from_currency, to_currency, amount):
    """
    Function that will call the relevant API endpoint from Frankfurter in order to get the latest conversion rate between the provided currencies.
    After the API call, it will perform a check to see if the API call was successful.
    If it is the case, it will load the response as JSON, extract the latest conversion rate and the date and return them as 2 separate objects.
    Otherwise it will return the value None twice.

    The starter signature includes ``amount`` and is intentionally preserved. The
    downstream request is for a unit rate, so changing only the amount does not
    create a different cache entry or API request.

    Parameters
    ----------
    from_currency : str
        Code for the origin currency
    to_currency : str
        Code for the destination currency
    amount : float
        The amount (in origin currency) to be converted

    Returns
    -------
    str
        Date of latest FX conversion rate or None in case of error
    float
        Latest FX conversion rate or None in case of error
    """
    del amount  # Kept in the public signature for starter compatibility.
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
    max_entries=HISTORICAL_RATE_CACHE_MAX_ENTRIES,
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
    Function that will call the relevant API endpoint from Frankfurter in order to get the conversion rate for the given currencies and date
    After the API call, it will perform a check to see if the API call was successful.
    If it is the case, it will load the response as JSON, extract the conversion rate and return it.
    Otherwise it will return the value None.

    The starter signature includes ``amount`` and is intentionally preserved. The
    cached value is the unit rate for the currency pair and date.

    Parameters
    ----------
    from_currency : str
        Code for the origin currency
    to_currency : str
        Code for the destination currency
    amount : float
        The amount (in origin currency) to be converted
    from_date : str
        Date when the conversion rate was recorded

    Returns
    -------
    float
        Historical FX conversion rate or None in case of error
    """
    del amount  # Kept in the public signature for starter compatibility.
    try:
        from_code = _normalise_currency(from_currency)
        to_code = _normalise_currency(to_currency)
        date_text = _normalise_date(from_date)
        if from_code == to_code:
            return 1.0
        return _cached_historical_unit_rate(from_code, to_code, date_text)
    except _FrankfurterError:
        return None


@st.cache_data(
    ttl=TREND_CACHE_TTL,
    max_entries=TREND_CACHE_MAX_ENTRIES,
    show_spinner=False,
)
def _cached_rate_trend(
    from_currency: str,
    to_currency: str,
    start_date: str,
    end_date: str,
) -> dict:
    query = urlencode({"from": from_currency, "to": to_currency})
    payload = _load_json(f"{BASE_URL}/{start_date}..{end_date}?{query}")
    daily_rates = payload.get("rates")
    if not isinstance(daily_rates, dict):
        raise _FrankfurterError("The trend response did not contain rate history.")

    # Keep the latest available observation in each calendar quarter. This turns
    # one time-series request into a compact chart instead of making many calls.
    quarterly = {}
    for rate_date in sorted(daily_rates):
        day_data = daily_rates[rate_date]
        if not isinstance(day_data, dict):
            continue
        rate = day_data.get(to_currency)
        if not isinstance(rate, (int, float)) or rate <= 0:
            continue
        parsed = date.fromisoformat(rate_date)
        quarter = (parsed.year, (parsed.month - 1) // 3 + 1)
        quarterly[quarter] = (rate_date, float(rate))

    if not quarterly:
        raise _FrankfurterError("No usable trend data was returned.")
    return {rate_date: rate for rate_date, rate in quarterly.values()}


def get_rate_trend(from_currency: str, to_currency: str, years: int) -> dict:
    """
    Fetches historical rates for the past N years on a quarterly basis and returns a dictionary with dates as keys and rates as values.

    Parameters
    ----------
    from_currency : str
        Code for the origin currency
    to_currency : str
        Code for the destination currency
    years : int
        Number of years in the past for which to fetch rates

    Returns
    -------
    dict
        Dictionary containing dates and their corresponding rates
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
        except ValueError:  # 29 February -> 28 February in a non-leap year.
            start = today.replace(month=2, day=28, year=today.year - years)

        if from_code == to_code:
            # No downstream request is needed for a mathematically constant pair.
            trend = {}
            cursor_year, cursor_month = start.year, start.month
            while (cursor_year, cursor_month) <= (today.year, today.month):
                trend[f"{cursor_year:04d}-{cursor_month:02d}-01"] = 1.0
                cursor_month += 3
                if cursor_month > 12:
                    cursor_month -= 12
                    cursor_year += 1
            return trend

        return _cached_rate_trend(
            from_code,
            to_code,
            start.isoformat(),
            today.isoformat(),
        )
    except (_FrankfurterError, TypeError, ValueError):
        return {}
