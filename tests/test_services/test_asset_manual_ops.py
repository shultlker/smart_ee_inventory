import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Asset
from backend.schemas.operation import ReturnConfirm, TakeOutConfirm
from backend.services.operation_service import (
    create_presence_pending_action,
    manual_asset_return,
    manual_asset_take_out,
)
from shared.constants import AssetStatus, InventoryEntityType


@pytest.mark.asyncio
async def test_watchdog_ignores_asset(db_session: AsyncSession) -> None:
    asset = Asset(
        asset_code="AST-WD",
        name="Tool",
        rfid_tag_epc="EPC-AST-WATCHDOG",
        status=AssetStatus.IN_STOCK,
    )
    db_session.add(asset)
    await db_session.commit()

    pending = await create_presence_pending_action(db_session, "EPC-AST-WATCHDOG", "disappear")
    assert pending is None
    await db_session.refresh(asset)
    assert asset.status == AssetStatus.IN_STOCK


@pytest.mark.asyncio
async def test_manual_asset_take_out_and_return(db_session: AsyncSession) -> None:
    asset = Asset(
        asset_code="AST-M",
        name="Multimeter",
        rfid_tag_epc="EPC-AST-MANUAL",
        status=AssetStatus.IN_STOCK,
    )
    db_session.add(asset)
    await db_session.commit()

    out_row = await manual_asset_take_out(
        db_session,
        "EPC-AST-MANUAL",
        TakeOutConfirm(user_name="王五", project_name="Lab-A"),
    )
    assert out_row["entity_type"] == InventoryEntityType.ASSET
    assert out_row["operation"] == "take_out"
    assert out_row["status"] == "confirmed"
    assert out_row["user_name"] == "王五"
    assert out_row["quantity_after"] == 0

    await db_session.refresh(asset)
    assert asset.status == AssetStatus.CHECKED_OUT

    with pytest.raises(ValueError, match="已借出"):
        await manual_asset_take_out(
            db_session,
            "EPC-AST-MANUAL",
            TakeOutConfirm(user_name="赵六", project_name="Lab-B"),
        )

    ret_row = await manual_asset_return(
        db_session,
        "EPC-AST-MANUAL",
        ReturnConfirm(note="完好归还"),
    )
    assert ret_row["operation"] == "return"
    assert ret_row["quantity_after"] == 1

    await db_session.refresh(asset)
    assert asset.status == AssetStatus.IN_STOCK

    with pytest.raises(ValueError, match="已在库"):
        await manual_asset_return(db_session, "EPC-AST-MANUAL", ReturnConfirm())
