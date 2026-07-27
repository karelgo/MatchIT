from fastapi import APIRouter, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.models import DevicePlatform, DeviceToken
from app.schemas.api import DeviceRegisterRequest

router = APIRouter(tags=["devices"])


@router.post("/users/me/devices", status_code=status.HTTP_204_NO_CONTENT)
async def register_device(body: DeviceRegisterRequest, user: CurrentUser, db: DbSession):
    """Register this device for push.

    A token is unique platform-wide and follows the device: when a handset is
    handed to another user the same token re-registers, and it must stop
    delivering to the previous account rather than notifying both.
    """
    existing = await db.scalar(select(DeviceToken).where(DeviceToken.token == body.token))
    if existing is None:
        db.add(
            DeviceToken(user_id=user.id, token=body.token, platform=DevicePlatform.IOS)
        )
    else:
        existing.user_id = user.id
    await db.commit()
