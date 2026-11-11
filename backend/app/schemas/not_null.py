"""Preserve non-nullable columns when an update supplies null."""

from typing import Any, ClassVar

from pydantic import BaseModel, model_validator


class IgnoresNullForRequiredColumns(BaseModel):
    __orm_table__: ClassVar[str]

    @model_validator(mode="before")
    @classmethod
    def _preserve_required_columns(cls, data: Any) -> Any:
        if not isinstance(data, dict) or None not in data.values():
            return data
        from backend.app.core.database import Base, load_all_models

        if cls.__orm_table__ not in Base.metadata.tables:
            load_all_models()
        columns = Base.metadata.tables[cls.__orm_table__].c
        protected = {
            key
            for name, field in cls.model_fields.items()
            if name in columns and not columns[name].nullable
            for key in (name, field.alias, field.validation_alias)
            if isinstance(key, str)
        }
        return {key: value for key, value in data.items() if value is not None or key not in protected}
