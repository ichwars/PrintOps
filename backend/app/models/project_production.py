from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.database import Base


class ProjectProductionOutput(Base):
    """Destination for the confirmed pieces from a production project."""

    __tablename__ = "project_production_outputs"

    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("warehouse_articles.id", ondelete="RESTRICT"), index=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id", ondelete="RESTRICT"), index=True)


class ProjectProductionReceipt(Base):
    """One inventory receipt per print run, with a durable link to the booked run."""

    __tablename__ = "project_production_receipts"

    ledger_entry_id: Mapped[int] = mapped_column(
        ForeignKey("warehouse_article_ledger_entries.id", ondelete="RESTRICT"), primary_key=True
    )
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"), index=True)
    run_id: Mapped[int | None] = mapped_column(
        ForeignKey("print_log_entries.id", ondelete="RESTRICT"), unique=True, index=True
    )
