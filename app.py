"""Streamlit interface for the Frankfurter currency converter."""

import datetime

import streamlit as st

from currency import format_output
from frankfurter import (
    get_currencies_list,
    get_historical_rate,
    get_latest_rates,
    get_rate_trend
)

TREND_YEARS = 3
DEFAULT_HISTORICAL_DATE = datetime.date(2024, 9, 1)
MIN_HISTORICAL_DATE = datetime.date(1999, 1, 4)


def _query_value(name: str, default: str) -> str:
    value = st.query_params.get(name, default)
    if isinstance(value, list):
        return value[-1] if value else default
    return value or default


def _saved_amount(default: float) -> float:
    try:
        value = float(_query_value("amount", str(default)))
    except ValueError:
        return default
    return value if value >= 0 else default


def _saved_currency_index(name: str, currencies: list, default: int) -> int:
    code = _query_value(name, "").strip().upper()
    return currencies.index(code) if code in currencies else default


def _saved_date(default: datetime.date) -> datetime.date:
    latest_allowed = datetime.date.today() - datetime.timedelta(days=1)
    try:
        saved = datetime.date.fromisoformat(
            _query_value("historical_date", default.isoformat())
        )
    except ValueError:
        return default
    return saved if MIN_HISTORICAL_DATE <= saved <= latest_allowed else default


def _save_inputs(amount, from_currency, to_currency, historical_date) -> None:
    """Keep form inputs in the URL so a browser refresh restores them."""
    values = {
        "amount": str(round(amount, 2)),
        "from_currency": from_currency,
        "to_currency": to_currency,
        "historical_date": historical_date.isoformat()
    }
    for key, value in values.items():
        if _query_value(key, "") != value:
            st.query_params[key] = value


def _show_result(title: str, result: dict) -> None:
    st.subheader(title)
    st.write(
        format_output(
            result["date"],
            result["from_currency"],
            result["to_currency"],
            result["rate"],
            result["amount"]
        )
    )


def _show_trend(trend: dict) -> None:
    if not trend:
        st.warning(
            "The conversion was successful, but trend data is unavailable right now."
        )
        return
    points = sorted(trend.items())
    chart_data = {
        "Date": [rate_date for rate_date, _ in points],
        "Rate": [rate for _, rate in points]
    }
    st.subheader(f"Rate Trend Over the Last {TREND_YEARS} Years")
    with st.spinner("Rendering the 3-year rate trend chart..."):
        st.line_chart(chart_data, x="Date", y="Rate")


st.set_page_config(page_title="FX Converter", layout="centered")
st.title("FX Converter")

with st.spinner("Loading supported currencies..."):
    currencies = get_currencies_list()

if not currencies:
    st.error(
        "The supported currency list could not be loaded. "
        "Please check your connection and try again shortly."
    )
    st.stop()

aud_index = currencies.index("AUD") if "AUD" in currencies else 0
usd_index = (
    currencies.index("USD") if "USD" in currencies else min(1, len(currencies) - 1)
)

amount = st.number_input(
    "Enter the amount to be converted:",
    min_value=0.0,
    value=_saved_amount(50.0),
    step=1.0,
    format="%.2f"
)
from_currency = st.selectbox(
    "From Currency:",
    currencies,
    index=_saved_currency_index("from_currency", currencies, aud_index)
)
to_currency = st.selectbox(
    "To Currency:",
    currencies,
    index=_saved_currency_index("to_currency", currencies, usd_index)
)
latest_clicked = st.button("Get Latest Rate")
latest_area = st.container()

historical_date = st.date_input(
    "Select a date for historical rates:",
    value=_saved_date(DEFAULT_HISTORICAL_DATE),
    min_value=MIN_HISTORICAL_DATE,
    max_value=datetime.date.today() - datetime.timedelta(days=1)
)
historical_clicked = st.button("Conversion Rate")
historical_area = st.container()

if latest_clicked:
    for key in ("latest_result", "latest_trend", "historical_result"):
        st.session_state.pop(key, None)
    with latest_area:
        with st.spinner("Fetching the latest exchange rate..."):
            latest_date, latest_rate = get_latest_rates(
                from_currency,
                to_currency,
                amount
            )
        if latest_date is None or latest_rate is None:
            st.error(
                "The latest conversion rate could not be loaded. "
                "Please try again shortly."
            )
        else:
            st.session_state["latest_result"] = {
                "date": latest_date,
                "from_currency": from_currency,
                "to_currency": to_currency,
                "rate": latest_rate,
                "amount": amount
            }
            _show_result(
                "Latest Conversion Rate", st.session_state["latest_result"]
            )
            with st.spinner("Fetching the 3-year rate trend..."):
                st.session_state["latest_trend"] = get_rate_trend(
                    from_currency,
                    to_currency,
                    TREND_YEARS
                )
            _show_trend(st.session_state["latest_trend"])

if historical_clicked:
    for key in ("latest_result", "latest_trend", "historical_result"):
        st.session_state.pop(key, None)
    with historical_area:
        with st.spinner("Fetching the historical exchange rate..."):
            historical_rate = get_historical_rate(
                from_currency,
                to_currency,
                historical_date,
                amount
            )
        if historical_rate is None:
            st.error(
                "No historical rate could be loaded for that selection. "
                "Try another date or try again shortly."
            )
        else:
            st.session_state["historical_result"] = {
                "date": historical_date.isoformat(),
                "from_currency": from_currency,
                "to_currency": to_currency,
                "rate": historical_rate,
                "amount": amount
            }

# Keep the last successful result visible during normal Streamlit reruns.
if "latest_result" in st.session_state and not latest_clicked:
    with latest_area:
        _show_result(
            "Latest Conversion Rate", st.session_state["latest_result"]
        )
        _show_trend(st.session_state.get("latest_trend", {}))
if "historical_result" in st.session_state:
    with historical_area:
        _show_result("Conversion Rate", st.session_state["historical_result"])
_save_inputs(amount, from_currency, to_currency, historical_date)