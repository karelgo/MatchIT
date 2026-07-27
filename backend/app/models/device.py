import enum
import uuid

from sqlalchemy import Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import TimestampedBase


class DevicePlatform(enum.StrEnum):
    IOS = "ios"


class DeviceToken(TimestampedBase):
    """A push destination for one user's device.

    Tokens are unique platform-wide: when a device is handed to a new user the
    same token re-registers, and it must follow the device, not accumulate
    against the old account.
    """

    __tablename__ = "device_tokens"
    __table_args__ = (UniqueConstraint("token"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    token: Mapped[str] = mapped_column(String(200), index=True)
    platform: Mapped[DevicePlatform] = mapped_column(
        Enum(DevicePlatform, native_enum=False, length=10), default=DevicePlatform.IOS
    )
