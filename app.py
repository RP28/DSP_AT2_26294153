"""Streamlit interface for the Frankfurter currency converter."""

import datetime

import streamlit as st

from frankfurter import (
    get_currencies_list,
    get_historical_rate,
    get_latest_rates,
    get_rate_trend
)
from currency import format_output

TREND_YEARS = 3
DEFAULT_HISTORICAL_DATE = datetime.date(2024, 9, 1)
MIN_HISTORICAL_DATE = datetime.date(1999, 1, 4)


def _get_query_value(name: str, default: str) -> str:
    """Read one URL query parameter value with a fallback."""
    value = st.query_params.get(name, default)
    if isinstance(value, list):
        return value[-1] if value else default
    return value or default


def _query_amount(default: float) -> float:
    """Return the amount stored in the URL, or the default amount."""
    try:
        amount = float(_get_query_value("amount", str(default)))
    except ValueError:
        return default
    return amount if amount >= 0 else default


def _query_currency_index(name: str, currencies: list, default_index: int) -> int:
    """Return the selected currency index stored in the URL."""
    code = _get_query_value(name, "").strip().upper()
    if code in currencies:
        return currencies.index(code)
    return default_index


def _query_historical_date(default: datetime.date) -> datetime.date:
    """Return the historical date stored in the URL, or the default date."""
    today = datetime.date.today()
    max_date = today - datetime.timedelta(days=1)
    try:
        selected_date = datetime.date.fromisoformat(
            _get_query_value("historical_date", default.isoformat())
        )
    except ValueError:
        return default
    if MIN_HISTORICAL_DATE <= selected_date <= max_date:
        return selected_date
    return default


def _store_recent_inputs(
    amount: float,
    from_currency: str,
    to_currency: str,
    historical_date: datetime.date
) -> None:
    """Store the current form values in the browser URL for refresh recovery."""
    recent_inputs = {
        "amount": str(round(amount, 2)),
        "from_currency": from_currency,
        "to_currency": to_currency,
        "historical_date": historical_date.isoformat()
    }
    for key, value in recent_inputs.items():
        if _get_query_value(key, "") != value:
            st.query_params[key] = value


def _show_result(title: str, result: dict) -> None:
    """Render one saved conversion result using the required output text."""
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


def _show_trend(trend: dict, from_currency: str, to_currency: str) -> None:
    """Render the optional three-year quarterly trend when data is available."""
    if not trend:
        st.warning("The conversion was successful, but trend data is unavailable right now.")
        return
    st.subheader(f"Rate Trend Over the Last {TREND_YEARS} years")
    chart_data = [
        {"Date": rate_date, "Rate": rate}
        for rate_date, rate in sorted(trend.items())
    ]
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

# Use AUD and USD as the default selected currencies when available.
aud_index = currencies.index("AUD") if "AUD" in currencies else 0
usd_index = currencies.index("USD") if "USD" in currencies else min(1, len(currencies) - 1)
historical_default = _query_historical_date(DEFAULT_HISTORICAL_DATE)

amount = st.number_input(
    "Enter the amount to be converted:",
    min_value=0.0,
    value=_query_amount(50.0),
    step=1.0,
    format="%.2f"
)
from_currency = st.selectbox(
    "From Currency:",
    currencies,
    index=_query_currency_index("from_currency", currencies, aud_index)
)
to_currency = st.selectbox(
    "To Currency:",
    currencies,
    index=_query_currency_index("to_currency", currencies, usd_index)
)
latest_clicked = st.button("Get Latest Rate")
latest_result_area = st.container()

historical_date = st.date_input(
    "Select a date for historical rates:",
    value=historical_default,
    min_value=MIN_HISTORICAL_DATE,
    max_value=datetime.date.today() - datetime.timedelta(days=1)
)
historical_clicked = st.button("Conversion Rate")
historical_result_area = st.container()

if latest_clicked:
    st.session_state.pop("historical_result", None)
    st.session_state.pop("latest_result", None)
    st.session_state.pop("latest_trend", None)
    with latest_result_area:
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
            _show_result("Latest Conversion Rate", st.session_state["latest_result"])
            with st.spinner("Fetching the 3-year rate trend..."):
                st.session_state["latest_trend"] = get_rate_trend(
                    from_currency,
                    to_currency,
                    TREND_YEARS
                )
            _show_trend(
                st.session_state["latest_trend"],
                from_currency,
                to_currency
            )

if historical_clicked:
    st.session_state.pop("latest_result", None)
    st.session_state.pop("latest_trend", None)
    st.session_state.pop("historical_result", None)
    with historical_result_area:
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

if "latest_result" in st.session_state and not latest_clicked:
    latest_result = st.session_state["latest_result"]
    with latest_result_area:
        _show_result("Latest Conversion Rate", latest_result)
        _show_trend(
            st.session_state.get("latest_trend", {}),
            latest_result["from_currency"],
            latest_result["to_currency"]
        )

if "historical_result" in st.session_state:
    with historical_result_area:
        _show_result("Conversion Rate", st.session_state["historical_result"])

_store_recent_inputs(amount, from_currency, to_currency, historical_date)