"""Application-owned model overrides; a NULL preset explicitly means generic."""

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.core.database import Base


class PresetFields:
    id: Mapped[int] = mapped_column(primary_key=True)
    printer_model: Mapped[str] = mapped_column(String(30))
    slicer_filament: Mapped[str | None] = mapped_column(String(128))
    slicer_filament_name: Mapped[str | None] = mapped_column(String(255))


class SpoolFilamentPreset(PresetFields, Base):
    __tablename__ = "spool_filament_preset"
    __table_args__ = (UniqueConstraint("spool_id", "printer_model"),)

    spool_id: Mapped[int] = mapped_column(ForeignKey("spool.id", ondelete="CASCADE"))
    spool: Mapped["Spool"] = relationship(back_populates="filament_presets")


class SpoolmanFilamentPreset(PresetFields, Base):
    __tablename__ = "spoolman_filament_preset"
    __table_args__ = (UniqueConstraint("spoolman_spool_id", "printer_model"),)

    # The remote ID is deliberately not a foreign key to the local inventory.
    spoolman_spool_id: Mapped[int] = mapped_column(Integer)


from backend.app.models.spool import Spool  # noqa: E402, F401
