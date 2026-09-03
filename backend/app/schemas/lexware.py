from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from backend.app.schemas.utc_timestamp import UtcTimestamp


class ConnectionTest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    api_key: SecretStr


class ConnectionCreate(ConnectionTest):
    business_profile_id: int = Field(gt=0)
    organization_id: str = Field(min_length=36, max_length=36)


class ConnectionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool | None = None
    api_key: SecretStr | None = None


class ConnectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    business_profile_id: int
    organization_id: str
    company_name: str
    enabled: bool
    connected: bool
    version: int
    sync_status: str
    last_success_at: UtcTimestamp | None
    last_attempt_at: UtcTimestamp | None
    last_error: str | None


class LexwarePreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    resource_id: int = Field(gt=0)
    customer_id: int | None = Field(default=None, gt=0)
    article_id: int | None = Field(default=None, gt=0)


class LexwareImportRequest(LexwarePreviewRequest):
    version_hash: str = Field(min_length=64, max_length=64)
    local_version: int | None = Field(default=None, ge=1)
    fields: list[str] = Field(max_length=20)
    article_options: dict | None = None
    confirmed_unit_code: str | None = Field(default=None, min_length=1, max_length=16)


ResourceKind = Literal["contacts", "articles"]
