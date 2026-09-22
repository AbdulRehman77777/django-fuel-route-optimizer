import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


def resilient_session():
    session = requests.Session()
    retry = Retry(
        total=2,
        connect=2,
        read=2,
        status=2,
        backoff_factor=0.25,
        status_forcelist=(500, 502, 503, 504),
        allowed_methods=("GET", "POST"),
        raise_on_status=False,
        respect_retry_after_header=False,
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.headers.update({"User-Agent": "fuel-route-optimizer-assessment/1.0"})
    return session
