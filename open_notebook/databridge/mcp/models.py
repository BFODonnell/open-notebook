from typing import Any, ClassVar, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from open_notebook.databridge.mcp.policy import IDENTIFIER
from open_notebook.domain.base import ObjectModel


class ConnectionSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=80)
    backend: Literal["dbhub", "toolbox", "duckdb"]
    endpoint_ref: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    dialect: Literal["postgres", "sqlite", "duckdb"]
    notebooks: list[str] = Field(min_length=1, max_length=100)
    tables: dict[str, list[str]] = Field(default_factory=dict)
    curated_tools: list[str] = Field(default_factory=list, max_length=10)
    schema_tool: str | None = None
    version_id: str | None = None
    max_rows: int = Field(default=100, ge=1, le=1000)
    max_bytes: int = Field(default=65536, ge=1024, le=262144)
    timeout_seconds: int = Field(default=10, ge=1, le=30)
    enabled: bool = True

    @field_validator("version_id")
    @classmethod
    def safe_version(cls, value):
        return str(UUID(value)) if value is not None else None

    @field_validator("tables")
    @classmethod
    def safe_tables(cls, value):
        if len(value) > 30:
            raise ValueError("Too many approved tables")
        for table, columns in value.items():
            if not IDENTIFIER.fullmatch(table) or not 1 <= len(columns) <= 100:
                raise ValueError("Invalid table allowlist")
            if any(not IDENTIFIER.fullmatch(c) for c in columns):
                raise ValueError("Invalid column allowlist")
        return value


class ConnectionWrite(ConnectionSpec):
    token: SecretStr | None = Field(default=None, max_length=4096)


class MCPConnection(ObjectModel):
    table_name: ClassVar[str] = "db_connection"
    nullable_fields: ClassVar[set[str]] = {
        "encrypted_token",
        "approved_fingerprint",
        "last_test",
    }
    spec: dict[str, Any]
    encrypted_token: str | None = None
    revision: str
    approved_fingerprint: str | None = None
    approved_tools: list[dict] = Field(default_factory=list)
    health: str = "untested"
    last_test: str | None = None

    def public(self) -> dict:
        return {
            "id": self.id,
            **self.spec,
            "revision": self.revision,
            "approved_fingerprint": self.approved_fingerprint,
            "tools": self.approved_tools,
            "health": self.health,
            "last_test": self.last_test,
            "has_token": bool(self.encrypted_token),
        }


class DatasetVersion(ObjectModel):
    table_name: ClassVar[str] = "db_dataset_version"
    manifest: dict[str, Any]


class QueryPlan(ObjectModel):
    table_name: ClassVar[str] = "db_query_plan"
    payload: dict[str, Any]
    approval_hash: str
    expires_at: str
    state: str = "pending"


class QueryRun(ObjectModel):
    table_name: ClassVar[str] = "db_query_run"
    payload: dict[str, Any]
