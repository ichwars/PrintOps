"""Relabel shipped Silk+ colours and repair unnamed RFID spools."""

from sqlalchemy import String, func, literal, or_, select, update
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from backend.app.core.catalog_defaults import DEFAULT_COLOR_CATALOG
from backend.app.models.color_catalog import ColorCatalogEntry
from backend.app.models.settings import Settings
from backend.app.models.spool import Spool


async def migrate_silk_plus_colors(conn) -> None:
    insert = postgres_insert if conn.dialect.name == "postgresql" else sqlite_insert
    claim = (
        insert(Settings)
        .values(key="_migrate_silk_plus_colors", value="true")
        .on_conflict_do_nothing(index_elements=[Settings.key])
        .returning(Settings.key)
    )
    if await conn.scalar(claim) is None:
        return

    for manufacturer, name, hex_color, line in DEFAULT_COLOR_CATALOG:
        if manufacturer == "Bambu Lab" and line == "PLA Silk+":
            await conn.execute(
                update(ColorCatalogEntry)
                .where(
                    ColorCatalogEntry.is_default.is_(True),
                    ColorCatalogEntry.manufacturer == manufacturer,
                    ColorCatalogEntry.material == "PLA Silk",
                    ColorCatalogEntry.color_name == name,
                    ColorCatalogEntry.extra_colors.is_(None),
                    ColorCatalogEntry.effect_type.is_(None),
                    func.upper(ColorCatalogEntry.hex_color) == hex_color,
                )
                .values(material=line)
            )

    color_name = (
        select(ColorCatalogEntry.color_name)
        .where(
            ColorCatalogEntry.manufacturer == "Bambu Lab",
            ColorCatalogEntry.material == "PLA Silk+",
            func.upper(ColorCatalogEntry.hex_color)
            == literal("#") + func.upper(func.substr(Spool.rgba, 1, 6), type_=String()),
        )
        .order_by(ColorCatalogEntry.id)
        .limit(1)
        .scalar_subquery()
    )
    await conn.execute(
        update(Spool)
        .where(
            Spool.data_origin == "rfid_auto",
            Spool.brand == "Bambu Lab",
            Spool.material == "PLA",
            Spool.subtype == "Silk+",
            or_(Spool.color_name.is_(None), Spool.color_name == ""),
            func.length(Spool.rgba) >= 6,
            func.substr(Spool.rgba, 7, 2) != "00",
            color_name.is_not(None),
        )
        .values(color_name=color_name)
    )
