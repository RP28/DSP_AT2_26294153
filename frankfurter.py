"""Frankfurter API calls and response validation."""

from datetime import date
import json
from urllib.parse import urlencode

from api import get_url

BASE_URL = "https://api.frankfurter.app"


class _FrankfurterError(RuntimeError):
    """Internal exception used to handle invalid API responses consistently."""


def get_currencies_list():
    """
    Get the currency codes supported by Frankfurter.

    Returns
    -------
    list
        List of available currencies, or None if the API call fails.
    """
    try:
        if not (currencies := sorted(
            code.upper()
            for code in _load_json(f"{BASE_URL}/currencies")
            if isinstance(code, str) and len(code) == 3 and code.isalpha()
        )):
            raise _FrankfurterError("No supported currencies were returned.")
        return currencies
    except _FrankfurterError:
        return None


def get_latest_rates(from_currency, to_currency, amount):
    """
    Get the latest unit conversion rate and its date.

    ``amount`` is retained because it is part of the starter function
    signature. Frankfurter is queried for the unit exchange rate only; the
    user's amount is applied later by ``currency.format_output()``. Therefore
    the amount must not affect this API request. ``del amount`` makes that
    deliberate non-use explicit while preserving the required signature.

    Returns
    -------
    tuple
        Latest rate date and unit rate, or ``(None, None)`` on failure.
    """
    del amount
    try:
        from_code = _normalise_currency(from_currency)
        to_code = _normalise_currency(to_currency)
        if from_code == to_code:
            return date.today().isoformat(), 1.0
        query = urlencode({"from": from_code, "to": to_code})
        payload = _load_json(f"{BASE_URL}/latest?{query}")
        if not isinstance(rate_date := payload.get("date"), str):
            raise _FrankfurterError("The latest-rate response had no date.")
        return rate_date, _extract_rate(payload, to_code)
    except _FrankfurterError:
        return None, None


def get_historical_rate(from_currency, to_currency, from_date, amount):
    """
    Get the unit conversion rate for a selected historical date.

    ``amount`` is retained because it is part of the starter function
    signature. The historical endpoint supplies a unit exchange rate and the
    user's amount is applied later by ``currency.format_output()``. Therefore
    the amount must not affect this API request. ``del amount`` makes that
    deliberate non-use explicit while preserving the required signature.

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
        return _historical_unit_rate(from_code, to_code, date_text)[1]
    except _FrankfurterError:
        return None


def get_rate_trend(from_currency: str, to_currency: str, years: int) -> dict:
    """
    Fetch historical rates for the past N years on a quarterly basis.

    The trend deliberately uses repeated calls to the historical endpoint
    required by the assignment. No separate time-series/range endpoint is used.

    Returns
    -------
    dict
        Dictionary containing quarterly dates and their corresponding rates.
    """
    try:
        if (years := int(years)) <= 0:
            raise _FrankfurterError("Years must be positive.")
        from_code = _normalise_currency(from_currency)
        to_code = _normalise_currency(to_currency)
        points = _quarterly_dates(years)
        if from_code == to_code:
            return {point.isoformat(): 1.0 for point in points}
        return dict(
            _historical_unit_rate(from_code, to_code, point.isoformat())
            for point in points
        )
    except (_FrankfurterError, TypeError, ValueError):
        return {}
    

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
    if len(code := str(currency).strip().upper()) != 3 or not code.isalpha():
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
    if not isinstance(rates := payload.get("rates"), dict) or to_currency not in rates:
        raise _FrankfurterError("The requested rate was not returned.")
    if not isinstance(rate := rates[to_currency], (int, float)) or rate <= 0:
        raise _FrankfurterError("The requested rate was invalid.")
    return float(rate)


def _historical_unit_rate(from_currency: str, to_currency: str, from_date: str):
    """Return the effective date and unit rate from the historical endpoint."""
    query = urlencode({"from": from_currency, "to": to_currency})
    payload = _load_json(f"{BASE_URL}/{from_date}?{query}")
    return (
        rate_date if isinstance(rate_date := payload.get("date"), str) else from_date,
        _extract_rate(payload, to_currency)
    )


def _quarterly_dates(years: int) -> list:
    """Return quarter-start dates covering the requested number of years."""
    today = date.today()
    try:
        start = today.replace(year=today.year - years)
    except ValueError:
        start = today.replace(year=today.year - years, month=2, day=28)
    quarter_month = ((start.month - 1) // 3) * 3 + 1
    point = date(start.year, quarter_month, 1)
    if point < start:
        point = (
            date(start.year + 1, 1, 1)
            if quarter_month == 10
            else date(start.year, quarter_month + 3, 1)
        )
    points = []
    while point <= today:
        points.append(point)
        point = (
            date(point.year + 1, 1, 1)
            if point.month == 10
            else date(point.year, point.month + 3, 1)
        )
    return points