"""Saved geometry for a reusable label sheet."""

from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.database import Base


class LabelTemplate(Base):
    __tablename__ = "label_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    name_key: Mapped[str] = mapped_column(String(300), unique=True)
    layout: Mapped[dict] = mapped_column(JSON)
