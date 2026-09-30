"""Streamlit interface for the Frankfurter currency converter."""

import datetime

import streamlit as st

from frankfurter import (
    get_currencies_list,
    get_historical_rate,
    get_latest_rates,
    get_rate_trend
)
from currency import format_output, reverse_rate, round_rate

TREND_YEARS = 3


def _show_result(title: str, result: dict) -> None:
    """Render one saved conversion result using metrics and the required text."""
    st.subheader(title)
    metric_columns = st.columns(3)
    metric_columns[0].metric(
        "Unit rate",
        f"1 {result['from_currency']} = {round_rate(result['rate'])} {result['to_currency']}"
    )
    metric_columns[1].metric(
        "Converted amount",
        f"{round(result['amount'] * result['rate'], 2)} {result['to_currency']}"
    )
    metric_columns[2].metric("Inverse rate", reverse_rate(result["rate"]))
    st.info(
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
    st.subheader(f"Rate Trend Over the Last {TREND_YEARS} Years")
    chart_data = [
        {"Date": rate_date, "Rate": rate}
        for rate_date, rate in sorted(trend.items())
    ]
    st.line_chart(chart_data, x="Date", y="Rate")
    st.caption(f"Quarterly observations for 1 {from_currency} in {to_currency}.")


st.set_page_config(page_title="FX Converter", page_icon="💱", layout="centered")
st.title("FX Converter")
st.caption("Latest and historical currency conversion powered by Frankfurter.")

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

with st.container(border=True):
    amount = st.number_input(
        "Enter the amount to be converted:",
        min_value=0.0,
        value=50.0,
        step=1.0,
        format="%.2f"
    )
    currency_columns = st.columns(2)
    from_currency = currency_columns[0].selectbox(
        "From Currency:",
        currencies,
        index=aud_index
    )
    to_currency = currency_columns[1].selectbox(
        "To Currency:",
        currencies,
        index=usd_index
    )
    latest_clicked = st.button("Get Latest Rate", type="primary")

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

st.divider()
st.subheader("Historical Conversion")
st.caption("Select a past date to retrieve the exchange rate for that day.")

historical_date = st.date_input(
    "Select a date for historical rates:",
    value=datetime.date.today() - datetime.timedelta(days=365),
    min_value=datetime.date(1999, 1, 4),
    max_value=datetime.date.today() - datetime.timedelta(days=1)
)
historical_clicked = st.button("Conversion Rate")

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