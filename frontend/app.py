"""Register NiceGUI pages on the FastAPI app."""

from frontend.pages import (
    bins,
    dashboard,
    inventory,
    inventory_bom,
    inventory_operations,
    inventory_register,
    slots,
)  # noqa: F401


def register_pages() -> None:
    """Import side-effect: @ui.page decorators register routes."""
    _ = (
        dashboard,
        bins,
        inventory,
        inventory_bom,
        inventory_operations,
        inventory_register,
        slots,
    )
