from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import requests


def retry_on_exceptions():
    return retry(
        reraise=True,
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=1, max=20),
        retry=retry_if_exception_type((requests.exceptions.RequestException,)),
    )
