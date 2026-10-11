from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.database import Base


class PrintLogEntry(Base):
    """Independent print log entry. Written when print events occur.

    This is a separate table from archives/queue — clearing the log
    never touches archives or queue items.

    archive_id is a nullable FK so log entries survive archive deletion (ON
    DELETE SET NULL). Aggregating runs per archive — for the per-archive
    "Print Log" view and for statistics that should not double-count
    overwritten archives (#1378) — is done via WHERE archive_id = X.
    """

    __tablename__ = "print_log_entries"
    __table_args__ = (
        CheckConstraint(
            "quantity >= 1 AND ((good_quantity IS NULL AND reject_quantity IS NULL) OR "
            "(good_quantity IS NOT NULL AND reject_quantity IS NOT NULL AND "
            "good_quantity >= 0 AND reject_quantity >= 0 AND good_quantity + reject_quantity = quantity))",
            name="ck_print_log_quality_quantities",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    archive_id: Mapped[int | None] = mapped_column(
        ForeignKey("print_archives.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Which queue item produced this run, when one did. Printer-initiated
    # prints have none. Batch cost/energy roll-up joins on this (#342): the
    # archive alone can't attribute a run to an order because several orders
    # — and plain reprints — share one archive.
    queue_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("print_queue.id", ondelete="SET NULL"), nullable=True, index=True
    )
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"), index=True)
    quantity: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    # Quality belongs to this run, separate from the machine-reported status.
    confirm_requested: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    user_verdict: Mapped[str | None] = mapped_column(String(10))
    good_quantity: Mapped[int | None] = mapped_column(Integer)
    reject_quantity: Mapped[int | None] = mapped_column(Integer)
    user_verdict_source: Mapped[str | None] = mapped_column(String(16))
    user_verdict_at: Mapped[datetime | None] = mapped_column(DateTime)
    # Store only the digest of a single-run, expiring notification capability.
    confirm_token_hash: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    confirm_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    confirm_token_used_at: Mapped[datetime | None] = mapped_column(DateTime)
    # Independent external-prompt claim; UI hints and public tokens are separate.
    confirm_prompted_at: Mapped[datetime | None] = mapped_column(DateTime)
    print_name: Mapped[str | None] = mapped_column(String(255))
    printer_name: Mapped[str | None] = mapped_column(String(255))
    printer_id: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20))  # completed, failed, stopped, cancelled, skipped
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    filament_type: Mapped[str | None] = mapped_column(String(50))
    filament_color: Mapped[str | None] = mapped_column(String(50))
    filament_used_grams: Mapped[float | None] = mapped_column(Float)
    cost: Mapped[float | None] = mapped_column(Float)
    energy_kwh: Mapped[float | None] = mapped_column(Float)
    energy_cost: Mapped[float | None] = mapped_column(Float)
    failure_reason: Mapped[str | None] = mapped_column(String(100))
    thumbnail_path: Mapped[str | None] = mapped_column(String(500))
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_by_username: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
