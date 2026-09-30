"""Low-level HTTP helper used by the currency converter."""

import requests

REQUEST_TIMEOUT_SECONDS = 10


def get_url(url: str) -> (int, str):
    """
    Call a GET API endpoint and return its status code and response text.

    Parameters
    ----------
    url : str
        URL of the GET API endpoint to be called.

    Returns
    -------
    int
        API response status code. Network-level failures return 0.
    str
        Response text, or a short user-friendly error message on failure.
    """
    try:
        response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
    except requests.Timeout:
        return 0, "The request to the exchange-rate service timed out."
    except requests.RequestException:
        return 0, "The exchange-rate service could not be reached."
    if not response.ok:
        return (
            response.status_code,
            f"The exchange-rate service returned HTTP {response.status_code}."
        )
    return response.status_code, response.text