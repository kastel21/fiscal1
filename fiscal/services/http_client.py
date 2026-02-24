"""
Secure HTTP client for FDMS with retry logic and strict TLS.
Retries on: 500/502, network failures (ConnectionError, Timeout).
Never uses verify=False.
"""

import logging
import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger("fiscal")

RETRY_STATUS_CODES = {500, 502}
NO_RETRY_STATUS_CODES = {400, 401, 422}
MAX_NETWORK_RETRIES = 3
NETWORK_RETRY_BACKOFF = 2.0


def requests_session_with_retry(
    retries: int = 3,
    backoff_factor: float = 2.0,
    status_forcelist: tuple = (500, 502),
) -> requests.Session:
    """Create session with retry on 500/502. Exponential backoff."""
    session = requests.Session()
    retry = Retry(
        total=retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
        allowed_methods=["GET", "POST"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def fdms_request(
    method: str,
    url: str,
    *,
    json: dict | None = None,
    data: str | bytes | None = None,
    headers: dict | None = None,
    cert: tuple[str, str] | None = None,
    timeout: int = 30,
) -> requests.Response:
    """
    Make FDMS request with retry on 500/502 and network failures.
    If data is provided, it is sent as body (e.g. custom JSON); otherwise json= is used.
    Never retries 400/401/422. Never disables SSL verification.
    """
    session = requests_session_with_retry(
        retries=3,
        backoff_factor=2.0,
        status_forcelist=(500, 502),
    )
    last_exc = None
    for attempt in range(MAX_NETWORK_RETRIES + 1):
        try:
            kwargs = {"method": method, "url": url, "headers": headers, "cert": cert, "timeout": timeout, "verify": True}
            if data is not None:
                kwargs["data"] = data
            else:
                kwargs["json"] = json
            return session.request(**kwargs)
        except (requests.ConnectionError, requests.Timeout) as e:
            last_exc = e
            if attempt < MAX_NETWORK_RETRIES:
                sleep_secs = NETWORK_RETRY_BACKOFF ** attempt
                logger.warning(
                    "FDMS request failed (attempt %d/%d): %s. Retrying in %.1fs.",
                    attempt + 1, MAX_NETWORK_RETRIES + 1, e, sleep_secs,
                )
                time.sleep(sleep_secs)
            else:
                raise
        except requests.RequestException:
            raise
    raise last_exc
