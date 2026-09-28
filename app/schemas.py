"""Pydantic models: input validation and the shape of API responses."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import Category, Severity, Status


class IssueCreate(BaseModel):
    """Fields a client may send. status and created_at are set by the server,
    so sending them (or any unknown field) is rejected with 422."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    call_id: str = Field(min_length=1, max_length=100)
    clinic: str = Field(min_length=2, max_length=100)
    description: str = Field(min_length=5, max_length=2000)
    category: Category
    severity: Severity


class IssueFilters(BaseModel):
    """Optional list filters. They combine with AND; an empty value means no filter."""

    clinic: str | None = None
    category: Category | None = None
    status: Status | None = None
    severity: Severity | None = None

    @field_validator("clinic", "category", "status", "severity", mode="before")
    @classmethod
    def empty_means_no_filter(cls, value: object) -> object:
        # A form submitted with "All" selected sends ?category= ; treat it as unset.
        if isinstance(value, str) and not value.strip():
            return None
        return value


class IssueListParams(IssueFilters):
    """Query string of the issue list: the filters plus the page number.

    FastAPI reads a query-parameter model only when it is the sole query
    parameter, so the page number lives here rather than as a separate argument.
    """

    page: int = Field(default=1, ge=1)


class IssueOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    call_id: str
    clinic: str = Field(validation_alias="clinic_name")
    description: str
    category: Category
    severity: Severity
    status: Status
    created_at: datetime
    resolved_at: datetime | None


class IssuePage(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[IssueOut]
    total: int
    page: int
    per_page: int
    pages: int


class CategoryCount(BaseModel):
    category: Category
    label: str
    count: int


class ClinicCount(BaseModel):
    clinic: str
    count: int


class Stats(BaseModel):
    total: int
    open: int
    resolved: int
    by_category: list[CategoryCount]
    by_clinic: list[ClinicCount]
