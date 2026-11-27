from pydantic import BaseModel, Field, PositiveInt

from backend.app.schemas.utc_timestamp import UtcTimestamp


class StockCheckRequest(BaseModel):
    ids: list[PositiveInt] = Field(min_length=1, max_length=10000)


class StockCheckRead(BaseModel):
    stock_checked_at: UtcTimestamp
