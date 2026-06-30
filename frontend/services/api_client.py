"""HTTP client for calling FastAPI from NiceGUI pages."""

from __future__ import annotations

from typing import Any

import httpx

from config import get_settings


def resolve_api_base_url() -> str:
    """Use the browser's host when inside a NiceGUI page (avoids port mismatch)."""
    try:
        from nicegui import ui

        client = ui.context.client
        request = getattr(client, "request", None)
        if request is not None:
            host = request.headers.get("host")
            if host:
                scheme = request.url.scheme
                return f"{scheme}://{host}"
    except Exception:
        pass
    settings = get_settings()
    return f"http://{settings.app_host}:{settings.app_port}"


class ApiClient:
    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = base_url or resolve_api_base_url()
        self._client: httpx.AsyncClient | None = None

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        if self._client is None:
            self._client = httpx.AsyncClient(base_url=self.base_url, timeout=10.0)
        resp = await getattr(self._client, method)(path, **kwargs)
        resp.raise_for_status()
        if resp.status_code == 204:
            return None
        return resp.json()

    async def get_bins(self) -> list[dict[str, Any]]:
        return await self._request("get", "/api/v1/bins")

    async def get_bin(self, bin_id: int) -> dict[str, Any]:
        return await self._request("get", f"/api/v1/bins/{bin_id}")

    async def create_bin(self, data: dict[str, Any]) -> dict[str, Any]:
        return await self._request("post", "/api/v1/bins", json=data)

    async def update_bin(self, bin_id: int, data: dict[str, Any]) -> dict[str, Any]:
        return await self._request("patch", f"/api/v1/bins/{bin_id}", json=data)

    async def delete_bin(self, bin_id: int) -> None:
        await self._request("delete", f"/api/v1/bins/{bin_id}")

    async def get_components(self) -> list[dict[str, Any]]:
        return await self._request("get", "/api/v1/components")

    async def get_categories(self) -> list[dict[str, Any]]:
        return await self._request("get", "/api/v1/categories")

    async def create_component(self, data: dict[str, Any]) -> dict[str, Any]:
        return await self._request("post", "/api/v1/components", json=data)

    async def get_slots(self, *, cabinet_id: int | None = None) -> list[dict[str, Any]]:
        params: dict[str, Any] = {}
        if cabinet_id is not None:
            params["cabinet_id"] = cabinet_id
        return await self._request("get", "/api/v1/slots", params=params)

    async def update_slot(self, slot_id: int, data: dict[str, Any]) -> dict[str, Any]:
        return await self._request("patch", f"/api/v1/slots/{slot_id}", json=data)

    async def get_inventory(
        self,
        *,
        cabinet_id: int | None = None,
        slot_id: int | None = None,
        low_stock_only: bool = False,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"low_stock_only": low_stock_only}
        if cabinet_id is not None:
            params["cabinet_id"] = cabinet_id
        if slot_id is not None:
            params["slot_id"] = slot_id
        return await self._request("get", "/api/v1/inventory", params=params)

    async def get_assets(self) -> list[dict[str, Any]]:
        return await self._request("get", "/api/v1/assets")

    async def asset_take_out(self, data: dict[str, Any]) -> dict[str, Any]:
        return await self._request("post", "/api/v1/assets/take-out", json=data)

    async def asset_return(self, data: dict[str, Any]) -> dict[str, Any]:
        return await self._request("post", "/api/v1/assets/return", json=data)

    async def register_inventory(self, data: dict[str, Any]) -> dict[str, Any]:
        return await self._request("post", "/api/v1/inventory/register", json=data)

    async def get_inventory_operations(
        self, *, limit: int = 50, after_id: int = 0, status: str | None = None, operation: str | None = None
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"limit": limit, "after_id": after_id}
        if status is not None:
            params["status"] = status
        if operation is not None:
            params["operation"] = operation
        return await self._request(
            "get",
            "/api/v1/inventory/operations",
            params=params,
        )

    async def confirm_inventory_operation(
        self, operation_id: int, data: dict[str, Any]
    ) -> dict[str, Any]:
        return await self._request(
            "post",
            f"/api/v1/inventory/operations/{operation_id}/confirm",
            json=data,
        )

    async def cancel_inventory_operation(self, operation_id: int) -> dict[str, Any]:
        return await self._request(
            "post",
            f"/api/v1/inventory/operations/{operation_id}/cancel",
        )

    async def clear_inventory_operations(self) -> dict[str, Any]:
        return await self._request("delete", "/api/v1/inventory/operations")

    async def bind_inventory_tag(self, data: dict[str, Any]) -> dict[str, Any]:
        return await self._request("post", "/api/v1/inventory/manage/bind-tag", json=data)

    async def rebind_inventory_tag(self, data: dict[str, Any]) -> dict[str, Any]:
        return await self._request("post", "/api/v1/inventory/manage/rebind-tag", json=data)

    async def unbind_inventory_tag(self, data: dict[str, Any]) -> dict[str, Any]:
        return await self._request("post", "/api/v1/inventory/manage/unbind-tag", json=data)

    async def delete_inventory_record(self, entity_type: str, record_id: int) -> dict[str, Any]:
        return await self._request(
            "delete",
            f"/api/v1/inventory/manage/{entity_type}/{record_id}",
        )

    async def update_inventory_item(self, item_id: int, data: dict[str, Any]) -> dict[str, Any]:
        return await self._request("patch", f"/api/v1/inventory/items/{item_id}", json=data)

    async def update_asset_record(self, asset_id: int, data: dict[str, Any]) -> dict[str, Any]:
        return await self._request("patch", f"/api/v1/assets/{asset_id}", json=data)

    async def list_boms(self) -> list[dict[str, Any]]:
        return await self._request("get", "/api/v1/boms")

    async def get_bom(self, bom_id: int) -> dict[str, Any]:
        return await self._request("get", f"/api/v1/boms/{bom_id}")

    async def import_bom(self, data: dict[str, Any]) -> dict[str, Any]:
        return await self._request("post", "/api/v1/boms/import", json=data)

    async def preview_bom(self, data: dict[str, Any]) -> dict[str, Any]:
        return await self._request("post", "/api/v1/boms/preview", json=data)

    async def analyze_bom(self, bom_id: int, *, kit_qty: int = 1) -> dict[str, Any]:
        return await self._request(
            "get",
            f"/api/v1/boms/{bom_id}/analysis",
            params={"kit_qty": kit_qty},
        )

    async def get_rfid_status(self) -> dict[str, Any]:
        return await self._request("get", "/api/v1/rfid/status")

    async def get_rfid_events(
        self, *, limit: int = 50, after_id: int = 0
    ) -> list[dict[str, Any]]:
        return await self._request(
            "get",
            "/api/v1/rfid/events",
            params={"limit": limit, "after_id": after_id},
        )
