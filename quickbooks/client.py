"""
Centralized QuickBooks API client.
- Injects Authorization header and refreshes token if expired.
- Captures intuit_tid from response headers and returns it with JSON.
- Logs requests/responses safely and creates QuickBooksAPILog entries.
"""

import json
import logging
from typing import Any

import requests

from quickbooks.models import QuickBooksToken, QuickBooksAPILog
from quickbooks.utils import get_valid_token
from quickbooks.utils import QuickBooksAPIException, QuickBooksTokenError

logger = logging.getLogger(__name__)


def _safe_json_serializable(obj: Any, max_length: int = 10000) -> Any:
    """Return a JSON-serializable copy of obj, truncating long strings for logging."""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return {k: _safe_json_serializable(v, max_length) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_safe_json_serializable(i, max_length) for i in obj]
    if isinstance(obj, str) and len(obj) > max_length:
        return obj[:max_length] + "...[truncated]"
    try:
        json.dumps(obj)
        return obj
    except (TypeError, ValueError):
        return str(obj)[:max_length]


class QuickBooksClient:
    """
    QuickBooks API client using QuickBooksToken for auth.
    All requests capture intuit_tid and are logged to QuickBooksAPILog.
    """

    def __init__(self, realm_id: str, user=None):
        self.realm_id = realm_id
        self._user = user
        self._token: QuickBooksToken | None = None
        self._base_url = self._get_base_url()

    def _get_base_url(self) -> str:
        from django.conf import settings
        return (getattr(settings, "QUICKBOOKS_API_BASE_URL", "") or "").rstrip("/")

    def _ensure_token(self) -> QuickBooksToken:
        if self._token is None:
            self._token = get_valid_token(self.realm_id, user=self._user)
        return self._token

    def _headers(self) -> dict:
        token = self._ensure_token()
        return {
            "Authorization": f"Bearer {token.access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _url(self, path: str) -> str:
        path = path.lstrip("/")
        return f"{self._base_url}/v3/company/{self.realm_id}/{path}"

    def _handle_response(
        self,
        response: requests.Response,
        endpoint: str,
        method: str,
        request_body: Any = None,
        qb_invoice_id: str | None = None,
    ) -> tuple[Any, str | None]:
        """
        Parse response, capture intuit_tid, log and create QuickBooksAPILog.
        Returns (json_data, intuit_tid). Raises QuickBooksAPIException on HTTP >= 400.
        """
        intuit_tid = response.headers.get("intuit_tid") if response.headers else None
        status_code = response.status_code

        try:
            if response.text and response.status_code != 204:
                response_body = response.json()
            else:
                response_body = {"_raw": response.text[:5000]} if response.text else None
        except (ValueError, json.JSONDecodeError):
            response_body = {"_raw": (response.text[:5000] if response.text else None)}

        # Structured logging
        logger.info(
            "QuickBooks API Call",
            extra={
                "realm_id": self.realm_id,
                "endpoint": endpoint,
                "method": method,
                "status_code": status_code,
                "intuit_tid": intuit_tid,
            },
        )

        # Persist to QuickBooksAPILog (never crash if save fails)
        try:
            QuickBooksAPILog.objects.create(
                realm_id=self.realm_id,
                endpoint=endpoint,
                method=method,
                status_code=status_code,
                intuit_tid=intuit_tid,
                request_body=_safe_json_serializable(request_body) if request_body is not None else None,
                response_body=_safe_json_serializable(response_body),
                qb_invoice_id=qb_invoice_id,
            )
        except Exception as e:
            logger.warning("QuickBooksAPILog create failed: %s", e)

        if status_code >= 400:
            err_msg = None
            if isinstance(response_body, dict):
                fault = response_body.get("Fault", {})
                errors = fault.get("Error", [])
                if errors and isinstance(errors, list):
                    err_msg = errors[0].get("Message", response.text[:500])
            if not err_msg and response.text:
                err_msg = response.text[:500]
            if not err_msg:
                err_msg = f"HTTP {status_code}"
            logger.error(
                "QuickBooks API error: %s",
                err_msg,
                extra={
                    "realm_id": self.realm_id,
                    "endpoint": endpoint,
                    "status_code": status_code,
                    "intuit_tid": intuit_tid,
                },
            )
            raise QuickBooksAPIException(
                err_msg,
                status_code=status_code,
                response_body=response_body,
                intuit_tid=intuit_tid,
            )

        return response_body, intuit_tid

    def get(
        self,
        path: str,
        params: dict | None = None,
        endpoint_label: str | None = None,
        qb_invoice_id: str | None = None,
    ) -> tuple[Any, str | None]:
        """
        GET request. Returns (json_data, intuit_tid).
        path is the path after /v3/company/{realm_id}/, e.g. "invoice/123" or "query".
        """
        if not self._base_url:
            raise QuickBooksTokenError("QUICKBOOKS_API_BASE_URL is not configured")
        url = self._url(path)
        endpoint = endpoint_label or path
        try:
            response = requests.get(
                url,
                headers=self._headers(),
                params=params,
                timeout=30,
            )
        except requests.RequestException as e:
            logger.exception("QuickBooks API GET request failed: %s", e)
            raise QuickBooksAPIException(str(e)) from e
        return self._handle_response(
            response,
            endpoint=endpoint,
            method="GET",
            request_body=params,
            qb_invoice_id=qb_invoice_id,
        )

    def post(
        self,
        path: str,
        json_payload: dict | None = None,
        endpoint_label: str | None = None,
        qb_invoice_id: str | None = None,
    ) -> tuple[Any, str | None]:
        """
        POST request. Returns (json_data, intuit_tid).
        """
        if not self._base_url:
            raise QuickBooksTokenError("QUICKBOOKS_API_BASE_URL is not configured")
        url = self._url(path)
        endpoint = endpoint_label or path
        try:
            response = requests.post(
                url,
                headers=self._headers(),
                json=json_payload,
                timeout=30,
            )
        except requests.RequestException as e:
            logger.exception("QuickBooks API POST request failed: %s", e)
            raise QuickBooksAPIException(str(e)) from e
        return self._handle_response(
            response,
            endpoint=endpoint,
            method="POST",
            request_body=json_payload,
            qb_invoice_id=qb_invoice_id,
        )

    def patch(
        self,
        path: str,
        json_payload: dict | None = None,
        endpoint_label: str | None = None,
        qb_invoice_id: str | None = None,
    ) -> tuple[Any, str | None]:
        """
        PATCH request. Returns (json_data, intuit_tid).
        """
        if not self._base_url:
            raise QuickBooksTokenError("QUICKBOOKS_API_BASE_URL is not configured")
        url = self._url(path)
        endpoint = endpoint_label or path
        try:
            response = requests.patch(
                url,
                headers=self._headers(),
                json=json_payload,
                timeout=30,
            )
        except requests.RequestException as e:
            logger.exception("QuickBooks API PATCH request failed: %s", e)
            raise QuickBooksAPIException(str(e)) from e
        return self._handle_response(
            response,
            endpoint=endpoint,
            method="PATCH",
            request_body=json_payload,
            qb_invoice_id=qb_invoice_id,
        )
