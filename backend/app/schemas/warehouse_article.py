from decimal import Decimal
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.app.schemas.utc_timestamp import UtcTimestamp

Quantity = Annotated[Decimal, Field(max_digits=18, decimal_places=6)]
NonNegative = Annotated[Quantity, Field(ge=0)]
ArticleKind = Literal["finished", "trade", "service"]
StockSource = Literal["own", "material", "none"]


class WarehouseSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True, str_strip_whitespace=True)


class WarehouseArticleCreate(WarehouseSchema):
    sku: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=20000)
    kind: ArticleKind
    unit_code: str = Field(min_length=1, max_length=16)
    sale_price: NonNegative = Decimal("0")
    tax_rate: NonNegative = Field(default=Decimal("0"), le=100)
    unit_cost: NonNegative = Decimal("0")
    minimum_stock: NonNegative = Decimal("0")
    stock_source: StockSource = "own"
    small_part_id: int | None = Field(default=None, gt=0)
    project_id: int | None = Field(default=None, gt=0)
    calculation_revision_id: int | None = Field(default=None, gt=0)
    is_active: bool = True

    @field_validator("unit_code")
    @classmethod
    def normalize_unit(cls, value):
        return value.upper()


class WarehouseArticleUpdate(WarehouseSchema):
    sku: str | None = Field(default=None, min_length=1, max_length=120)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=20000)
    kind: ArticleKind | None = None
    unit_code: str | None = Field(default=None, min_length=1, max_length=16)
    sale_price: NonNegative | None = None
    tax_rate: NonNegative | None = Field(default=None, le=100)
    unit_cost: NonNegative | None = None
    minimum_stock: NonNegative | None = None
    stock_source: StockSource | None = None
    small_part_id: int | None = Field(default=None, gt=0)
    project_id: int | None = Field(default=None, gt=0)
    calculation_revision_id: int | None = Field(default=None, gt=0)
    is_active: bool | None = None
    version: int = Field(gt=0)

    @field_validator("unit_code")
    @classmethod
    def normalize_unit(cls, value):
        return value.upper() if value else value

    @model_validator(mode="after")
    def reject_null_required(self) -> Self:
        nullable = {"description", "small_part_id", "project_id", "calculation_revision_id"}
        for key in self.model_fields_set - nullable:
            if getattr(self, key) is None:
                raise ValueError(f"{key} cannot be null")
        return self


class WarehouseBalance(WarehouseSchema):
    physical: Decimal = Decimal("0")
    reserved: Decimal = Decimal("0")
    available: Decimal = Decimal("0")
    is_low_stock: bool = False


class WarehouseLocationBalance(WarehouseBalance):
    location_id: int | None
    location_name: str


class WarehouseArticleRead(WarehouseArticleCreate):
    id: int
    version: int
    created_at: UtcTimestamp
    updated_at: UtcTimestamp
    has_history: bool
    balance: WarehouseBalance
    locations: list[WarehouseLocationBalance]


class WarehouseArticlePage(WarehouseSchema):
    items: list[WarehouseArticleRead]
    total: int
    limit: int
    offset: int


class WarehouseMovementCreate(WarehouseSchema):
    entry_kind: Literal[
        "opening", "receipt", "issue", "transfer", "correction", "reservation", "release", "reserved_issue", "counter"
    ]
    location_id: int | None = Field(default=None, gt=0)
    target_location_id: int | None = Field(default=None, gt=0)
    quantity: Quantity | None = None
    reason: str = Field(min_length=1, max_length=2000)
    order_id: int | None = Field(default=None, gt=0)
    reservation_id: int | None = Field(default=None, gt=0)
    reverses_id: int | None = Field(default=None, gt=0)
    idempotency_key: str = Field(min_length=8, max_length=128)

    @model_validator(mode="after")
    def validate_command(self) -> Self:
        if self.entry_kind == "counter":
            if self.reverses_id is None or any(
                value is not None
                for value in (
                    self.quantity,
                    self.location_id,
                    self.target_location_id,
                    self.order_id,
                    self.reservation_id,
                )
            ):
                raise ValueError("counter requires only reverses_id, reason and idempotency_key")
            return self
        if self.reverses_id is not None or self.location_id is None or self.quantity is None:
            raise ValueError("movement requires location_id and quantity")
        if self.quantity == 0 or (self.entry_kind != "correction" and self.quantity < 0):
            raise ValueError("quantity must be positive (correction may be negative)")
        if (self.entry_kind == "transfer") != (self.target_location_id is not None):
            raise ValueError("only transfers require target_location_id")
        if self.target_location_id == self.location_id:
            raise ValueError("transfer requires two different locations")
        if (self.entry_kind in {"release", "reserved_issue"}) != (self.reservation_id is not None):
            raise ValueError("release and reserved_issue require a reservation_id")
        return self


class WarehouseMovementRead(WarehouseSchema):
    id: int
    article_id: int
    entry_kind: str
    location_id: int
    target_location_id: int | None
    quantity: Decimal
    physical_delta: Decimal
    reserved_delta: Decimal
    unit_code: str
    reason: str
    order_id: int | None
    reservation_id: int | None
    reverses_id: int | None
    actor_id: int | None
    idempotency_key: str
    created_at: UtcTimestamp


class WarehouseReservationRead(WarehouseSchema):
    id: int
    location_id: int
    order_id: int | None
    remaining: Decimal
