"""API client for ServiceM8."""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
import logging
from typing import Any

from aiohttp import ClientError, ClientResponse, ClientSession

_LOGGER = logging.getLogger(__name__)


class ServiceM8ApiError(Exception):
    """Base API error."""


class ServiceM8AuthError(ServiceM8ApiError):
    """Authentication error."""


@dataclass(slots=True)
class ServiceM8ApiClient:
    """Thin async wrapper around the ServiceM8 REST API."""

    session: ClientSession
    api_key: str
    base_url: str

    async def async_get_account_probe(self) -> dict[str, Any]:
        """Probe the API using a lightweight request."""
        companies = await self.async_get_resource("company", limit_pages=1)
        return {"company_count_sample": len(companies)}

    async def async_get_resource(
        self,
        resource: str,
        *,
        filter_query: str | None = None,
        limit_pages: int | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch a full resource list using cursor pagination when available."""
        results: list[dict[str, Any]] = []
        cursor: str | None = "-1"
        page_count = 0

        while cursor is not None:
            params: dict[str, str] = {"cursor": cursor}
            if filter_query:
                params["$filter"] = filter_query
            response = await self._request("GET", f"/{resource}.json", params=params)
            payload = await self._decode_json(response)
            items = self._normalise_list_payload(payload)
            results.extend(items)
            page_count += 1
            cursor = response.headers.get("x-next-cursor")
            if limit_pages is not None and page_count >= limit_pages:
                break
        return results

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
    ) -> ClientResponse:
        headers = {
            "X-API-Key": self.api_key,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        url = f"{self.base_url.rstrip('/')}{path}"
        try:
            response = await self.session.request(method, url, headers=headers, params=params)
        except ClientError as err:
            raise ServiceM8ApiError(f"Network error calling {url}: {err}") from err

        if response.status in (401, 403):
            text = await response.text()
            raise ServiceM8AuthError(f"Authentication failed ({response.status}): {text[:500]}")
        if response.status >= 400:
            text = await response.text()
            raise ServiceM8ApiError(f"API error for {url} ({response.status}): {text[:500]}")
        return response

    async def _decode_json(self, response: ClientResponse) -> Any:
        try:
            return await response.json(content_type=None)
        except Exception as err:  # noqa: BLE001
            text = await response.text()
            raise ServiceM8ApiError(f"Could not decode JSON response: {text[:500]}") from err

    def _normalise_list_payload(self, payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            for value in payload.values():
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
        return []
