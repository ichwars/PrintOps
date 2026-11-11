"""Reusable slicer and calibration settings for an inventory product."""

from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.database import Base


class FilamentProfileDefault(Base):
    __tablename__ = "filament_profile_defaults"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_key: Mapped[str] = mapped_column(String(64), unique=True)
    brand: Mapped[str] = mapped_column(String(100), default="")
    material: Mapped[str] = mapped_column(String(50))
    subtype: Mapped[str] = mapped_column(String(50), default="")
    color_name: Mapped[str] = mapped_column(String(100), default="")
    slicer_filament: Mapped[str | None] = mapped_column(String(128))
    slicer_filament_name: Mapped[str | None] = mapped_column(String(255))
    presets: Mapped[list[dict]] = mapped_column(JSON, default=list)
    k_profiles: Mapped[list[dict]] = mapped_column(JSON, default=list)
