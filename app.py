"""Streamlit interface for the Frankfurter currency converter."""

from datetime import date, timedelta

import streamlit as st

from currency import format_output
from frankfurter import (
    get_currencies_list,
    get_historical_rate,
    get_latest_rates,
    get_rate_trend
)

TREND_YEARS = 3
DEFAULT_HISTORICAL_DATE = date(2024, 9, 1)
MIN_HISTORICAL_DATE = date(1999, 1, 4)


@st.cache_data(max_entries=1)
def _cached_currencies():
    if not (result := get_currencies_list()):
        raise RuntimeError
    return result


@st.cache_data(max_entries=1, ttl=3600)
def _cached_latest_rate(from_currency: str, to_currency: str):
    if None in (result := get_latest_rates(from_currency, to_currency, 1.0)):
        raise RuntimeError
    return result


@st.cache_data(max_entries=1)
def _cached_historical_rate(from_currency: str, to_currency: str, historical_date: str):
    if (result := get_historical_rate(
        from_currency, to_currency, historical_date, 1.0
    )) is None:
        raise RuntimeError
    return result


@st.cache_data(max_entries=1)
def _cached_rate_trend(from_currency: str, to_currency: str):
    if not (result := get_rate_trend(from_currency, to_currency, TREND_YEARS)):
        raise RuntimeError
    return result


def _clear_results() -> None:
    for key in ("latest_result", "latest_trend", "historical_result"):
        st.session_state.pop(key, None)


def _save_inputs(clear_latest: bool = False) -> None:
    """Persist widget state in the URL using Streamlit's query-parameter API."""
    st.query_params.from_dict({
        "amount": f"{st.session_state.amount:.2f}",
        "from_currency": st.session_state.from_currency,
        "to_currency": st.session_state.to_currency,
        "historical_date": st.session_state.historical_date.isoformat()
    })
    _clear_results() if clear_latest else st.session_state.pop("historical_result", None)


def _show_result(title: str, result: tuple) -> None:
    st.subheader(title)
    st.text_area(
        f"{title} text",
        value=format_output(*result),
        height=90,
        disabled=True,
        label_visibility="collapsed"
    )


def _show_trend(trend: dict) -> None:
    if not trend:
        st.warning("The conversion was successful, but trend data is unavailable right now.")
        return
    dates, rates = zip(*sorted(trend.items()))
    st.subheader(f"Rate Trend Over the Last {TREND_YEARS} years")
    with st.spinner("Rendering the 3-year rate trend chart..."):
        st.line_chart({"Date": dates, "Rate": rates}, x="Date", y="Rate")


st.set_page_config(page_title="FX Converter", layout="centered")
st.title("FX Converter")

try:
    with st.spinner("Loading supported currencies..."):
        currencies = _cached_currencies()
except RuntimeError:
    st.error(
        "The supported currency list could not be loaded. "
        "Please check your connection and try again shortly."
    )
    st.stop()

params = st.query_params
max_historical_date = date.today() - timedelta(days=1)
default_from = "AUD" if "AUD" in currencies else currencies[0]
default_to = "USD" if "USD" in currencies else currencies[min(1, len(currencies) - 1)]

if "amount" not in st.session_state:
    try:
        st.session_state.amount = (
            saved if (saved := float(params.get("amount", 50.0))) >= 0 else 50.0
        )
    except (TypeError, ValueError):
        st.session_state.amount = 50.0

for key, default in (("from_currency", default_from), ("to_currency", default_to)):
    if key not in st.session_state:
        st.session_state[key] = (
            value if (value := str(params.get(key, default)).upper()) in currencies else default
        )

if "historical_date" not in st.session_state:
    try:
        saved_date = date.fromisoformat(
            str(params.get("historical_date", DEFAULT_HISTORICAL_DATE.isoformat()))
        )
        st.session_state.historical_date = (
            saved_date
            if MIN_HISTORICAL_DATE <= saved_date <= max_historical_date
            else DEFAULT_HISTORICAL_DATE
        )
    except ValueError:
        st.session_state.historical_date = DEFAULT_HISTORICAL_DATE

amount = st.number_input(
    "Enter the amount to be converted:",
    min_value=0.0,
    step=1.0,
    format="%.2f",
    key="amount",
    on_change=_save_inputs,
    args=[True]
)
from_currency = st.selectbox(
    "From Currency:",
    currencies,
    key="from_currency",
    on_change=_save_inputs,
    args=[True]
)
to_currency = st.selectbox(
    "To Currency:",
    currencies,
    key="to_currency",
    on_change=_save_inputs,
    args=[True]
)
latest_clicked = st.button("Get Latest Rate")
latest_area = st.container()

historical_date = st.date_input(
    "Select a date for historical rates:",
    min_value=MIN_HISTORICAL_DATE,
    max_value=max_historical_date,
    key="historical_date",
    on_change=_save_inputs
)
historical_clicked = st.button("Conversion Rate")
historical_area = st.container()

if latest_clicked:
    _clear_results()
    try:
        with st.spinner("Fetching the latest exchange rate..."):
            latest_date, latest_rate = _cached_latest_rate(from_currency, to_currency)
        st.session_state.latest_result = (
            latest_date,
            from_currency,
            to_currency,
            latest_rate,
            amount
        )
        try:
            with st.spinner("Fetching the 3-year rate trend..."):
                st.session_state.latest_trend = _cached_rate_trend(
                    from_currency, to_currency
                )
        except RuntimeError:
            st.session_state.latest_trend = {}
    except RuntimeError:
        with latest_area:
            st.error("The latest conversion rate could not be loaded. Please try again shortly.")

if historical_clicked:
    _clear_results()
    try:
        with st.spinner("Fetching the historical exchange rate..."):
            historical_rate = _cached_historical_rate(
                from_currency,
                to_currency,
                historical_date.isoformat()
            )
        st.session_state.historical_result = (
            historical_date.isoformat(),
            from_currency,
            to_currency,
            historical_rate,
            amount
        )
    except RuntimeError:
        with historical_area:
            st.error(
                "No historical rate could be loaded for that selection. "
                "Try another date or try again shortly."
            )

if result := st.session_state.get("latest_result"):
    with latest_area:
        _show_result("Latest Conversion Rate", result)
        _show_trend(st.session_state.get("latest_trend", {}))

if result := st.session_state.get("historical_result"):
    with historical_area:
        _show_result("Conversion Rate", result)