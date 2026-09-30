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

amount = st.number_input(
    "Enter the amount to be converted:",
    min_value=0.0,
    value=50.0,
    step=1.0,
    format="%.2f"
)
from_currency = st.selectbox(
    "From Currency:",
    currencies,
    index=aud_index
)
to_currency = st.selectbox(
    "To Currency:",
    currencies,
    index=usd_index
)
latest_clicked = st.button("Get Latest Rate")

historical_date = st.date_input(
    "Select a date for historical rates:",
    value=DEFAULT_HISTORICAL_DATE,
    min_value=datetime.date(1999, 1, 4),
    max_value=datetime.date.today() - datetime.timedelta(days=1)
)
historical_clicked = st.button("Conversion Rate")

if latest_clicked:
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
            st.session_state["latest_trend"] = get_rate_trend(
                from_currency,
                to_currency,
                TREND_YEARS
            )

if "latest_result" in st.session_state:
    latest_result = st.session_state["latest_result"]
    _show_result("Latest Conversion Rate", latest_result)
    _show_trend(
        st.session_state.get("latest_trend", {}),
        latest_result["from_currency"],
        latest_result["to_currency"]
    )

if historical_clicked:
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

if "historical_result" in st.session_state:
    _show_result("Conversion Rate", st.session_state["historical_result"])