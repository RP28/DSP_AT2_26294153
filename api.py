"""Low-level HTTP utilities for the currency converter."""

import requests

REQUEST_TIMEOUT_SECONDS = 10
_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": "UTS-Currency-Converter/1.0"})


def get_url(url: str) -> (int, str):
    """
    Function that will call a provided GET API endpoint url and return its status code and either its content or error message as a string

    Parameters
    ----------
    url : str
        URL of the GET API endpoint to be called

    Returns
    -------
    int
        API call response status code. Network-level failures return 0.
    str
        Text from API call response, or a short diagnostic message on failure.
    """
    try:
        response = _SESSION.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
    except requests.Timeout:
        return 0, "The request to the exchange-rate service timed out."
    except requests.RequestException:
        return 0, "The exchange-rate service could not be reached."

    if not response.ok:
        return response.status_code, (
            f"The exchange-rate service returned HTTP {response.status_code}."
        )

    return response.status_code, response.text
