"""Persistent Telegram reaction grants and per-bot polling ownership.

New tables are installed on existing and fresh databases by metadata.create_all.
"""

import secrets
from datetime import datetime

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.database import Base


class TelegramQualityConfig(Base):
    __tablename__ = "telegram_quality_configs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: secrets.token_hex(16))
    provider_id: Mapped[int] = mapped_column(ForeignKey("notification_providers.id", ondelete="CASCADE"), unique=True)
    bot_id: Mapped[str] = mapped_column(String(32), unique=True)
    revision: Mapped[str] = mapped_column(String(32), default=lambda: secrets.token_hex(16))
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    actors: Mapped[list] = mapped_column(JSON, default=list)


class TelegramQualityMessage(Base):
    __tablename__ = "telegram_quality_messages"
    __table_args__ = (UniqueConstraint("bot_id", "chat_id", "message_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    config_id: Mapped[str] = mapped_column(ForeignKey("telegram_quality_configs.id", ondelete="CASCADE"))
    bot_id: Mapped[str] = mapped_column(String(32))
    chat_id: Mapped[int] = mapped_column(BigInteger)
    message_id: Mapped[int] = mapped_column(BigInteger)
    archive_id: Mapped[int] = mapped_column(ForeignKey("print_archives.id", ondelete="CASCADE"))
    run_id: Mapped[int] = mapped_column(ForeignKey("print_log_entries.id", ondelete="CASCADE"))
    config_revision: Mapped[str] = mapped_column(String(32))
    quantity: Mapped[int]
    token_hash: Mapped[str] = mapped_column(String(64))
    owner_id: Mapped[int | None]
    owner_identity: Mapped[str | None] = mapped_column(String(32))
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class TelegramPollState(Base):
    __tablename__ = "telegram_poll_states"
    bot_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    cursor: Mapped[int | None] = mapped_column(BigInteger)
    last_update_at: Mapped[datetime | None] = mapped_column(DateTime)
    lease_owner: Mapped[str | None] = mapped_column(String(32))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(32), default="idle")
