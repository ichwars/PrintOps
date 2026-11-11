"""Keep links to a merged archive pointing to its surviving file."""

from sqlalchemy import JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.database import Base


class ArchiveAlias(Base):
    __tablename__ = "archive_aliases"

    # The original row is removed. Its identifier stays reserved for this link.
    merged_archive_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    archive_id: Mapped[int] = mapped_column(ForeignKey("print_archives.id", ondelete="CASCADE"), index=True)
    source_printer_ids: Mapped[list[int]] = mapped_column(JSON)
    source_unassigned: Mapped[bool] = mapped_column()
