from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.database import Base


class FilamentSkuSettings(Base):
    """User-configured reorder settings for a filament SKU (material/subtype/brand group)."""

    __tablename__ = "filament_sku_settings"
    __table_args__ = (
        # Historical nullable duplicates retain IDs referenced by procurement.
        # The expression index below permits only one numbered group identity.
        # color_name is part of the key so forecasts distinguish e.g. White vs Black
        # PLA Matte (#forecast-color-grouping).
        UniqueConstraint("material", "subtype", "brand", "color_name", name="uq_filament_sku"),
        Index(
            "uq_numbered_filament_group",
            func.trim(text("material")),
            func.trim(func.coalesce(text("subtype"), "")),
            func.trim(func.coalesce(text("brand"), "")),
            func.trim(func.coalesce(text("color_name"), "")),
            unique=True,
            sqlite_where=text("material_number IS NOT NULL"),
            postgresql_where=text("material_number IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    material: Mapped[str] = mapped_column(String(50))
    material_number: Mapped[str | None] = mapped_column(String(120), unique=True)
    subtype: Mapped[str | None] = mapped_column(String(50))
    brand: Mapped[str | None] = mapped_column(String(100))
    color_name: Mapped[str | None] = mapped_column(String(100))
    default_supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id", ondelete="SET NULL"), index=True)
    lead_time_days: Mapped[int] = mapped_column(Integer, default=0)
    safety_margin_value: Mapped[int] = mapped_column(Integer, default=14)
    safety_margin_unit: Mapped[str] = mapped_column(String(10), default="days")
    alerts_snoozed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
