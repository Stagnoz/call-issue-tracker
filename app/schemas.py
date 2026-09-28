"""Pydantic models: input validation and the shape of API responses."""

import re
import unicodedata
from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_core import PydanticCustomError

from app.models import Category, Severity, Status

# Format rules for the free-text fields.
CALL_ID_PATTERN = re.compile(r"[A-Za-z0-9._:-]+")
# Letters (accented ones too), digits, spaces and a little punctuation,
# including the typographic apostrophe used by phones and word processors.
CLINIC_PATTERN = re.compile(r"(?:[^\W_]|[ .,'’()&/-])+")

# Personal data that must never be stored in an issue (GDPR: health context).
EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# Italian tax code (codice fiscale), including the letters that replace digits
# in "omocodia" cases. A match must also contain a digit, so words never match.
TAX_CODE_PATTERN = re.compile(
    r"\b[A-Z]{6}[0-9LMNP-V]{2}[A-EHLMPR-T][0-9LMNP-V]{2}[A-Z][0-9LMNP-V]{3}[A-Z]\b",
    re.IGNORECASE,
)
# Phone numbers: 9 or more digits starting with a country code (+ or 00), 0
# (landline) or 3 (mobile), optionally separated by single spaces or dashes.
# Dates such as 2026-09-28 14:05, 28/09/2026 or 03.10.2026 do not match.
PHONE_PATTERN = re.compile(r"(?<![\w+])(?:(?:\+|00)\d{1,3}[ -]?)?[03]\d(?:[ -]?\d){7,}(?!\w)")

# Unicode categories of control, invisible formatting (zero-width, bidi
# overrides), private-use, surrogate and unassigned characters.
INVISIBLE_CATEGORIES = {"Cc", "Cf", "Co", "Cs", "Cn"}


def reject_invisible_characters(value: str, allow_line_breaks: bool = False) -> str:
    allowed = {"\n", "\r", "\t"} if allow_line_breaks else set()
    for char in value:
        if char not in allowed and unicodedata.category(char) in INVISIBLE_CATEGORIES:
            raise PydanticCustomError(
                "invisible_characters", "Remove control or invisible characters."
            )
    return value


PERSONAL_DATA_KINDS = {
    "email": "an email address",
    "tax_code": "an Italian tax code",
    "phone": "a phone number",
}


def reject_personal_data(value: str) -> str:
    """Reject values that look like an email address, a tax code or a phone number."""
    if EMAIL_PATTERN.search(value):
        kind = "email"
    elif any(re.search(r"\d", match) for match in TAX_CODE_PATTERN.findall(value)):
        kind = "tax_code"
    elif PHONE_PATTERN.search(value):
        kind = "phone"
    else:
        return value
    raise PydanticCustomError(
        "personal_data",
        "Remove personal data: this looks like {what}. Reference the call by call_id.",
        {"kind": kind, "what": PERSONAL_DATA_KINDS[kind]},
    )


class IssueCreate(BaseModel):
    """Fields a client may send. status and created_at are set by the server,
    so sending them (or any unknown field) is rejected with 422."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    call_id: str = Field(min_length=1, max_length=100)
    clinic: str = Field(min_length=2, max_length=100)
    description: str = Field(min_length=5, max_length=2000)
    category: Category
    severity: Severity

    # These run after trimming and the length checks.
    @field_validator("call_id")
    @classmethod
    def check_call_id(cls, value: str) -> str:
        reject_invisible_characters(value)
        if not CALL_ID_PATTERN.fullmatch(value):
            raise PydanticCustomError(
                "call_id_format", "Use only letters, digits and - _ . : (no spaces)."
            )
        return reject_personal_data(value)

    @field_validator("clinic")
    @classmethod
    def check_clinic(cls, value: str) -> str:
        reject_invisible_characters(value)
        if not CLINIC_PATTERN.fullmatch(value):
            raise PydanticCustomError(
                "clinic_format", "Use letters, digits, spaces and . , ' - ( ) & / only."
            )
        return reject_personal_data(value)

    @field_validator("description")
    @classmethod
    def check_description(cls, value: str) -> str:
        reject_invisible_characters(value, allow_line_breaks=True)
        return reject_personal_data(value)


class ResolveRequest(BaseModel):
    """Optional body when resolving: a short note on what was fixed."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    note: str | None = Field(default=None, max_length=500)

    @field_validator("note")
    @classmethod
    def check_note(cls, value: str | None) -> str | None:
        if not value:
            return None
        reject_invisible_characters(value)
        return reject_personal_data(value)


class DeleteRequest(BaseModel):
    """Body when deleting: why the issue should not exist (required)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    reason: str = Field(min_length=3, max_length=500)

    @field_validator("reason")
    @classmethod
    def check_reason(cls, value: str) -> str:
        reject_invisible_characters(value)
        return reject_personal_data(value)


class IssueFilters(BaseModel):
    """Optional list filters. They combine with AND; an empty value means no filter."""

    clinic: str | None = None
    category: Category | None = None
    status: Status | None = None
    severity: Severity | None = None
    # Free-text search in the description and the call_id.
    q: str | None = Field(default=None, max_length=100)

    @field_validator("clinic", "category", "status", "severity", "q", mode="before")
    @classmethod
    def empty_means_no_filter(cls, value: object) -> object:
        # A form submitted with "All" selected sends ?category= ; treat it as unset.
        if isinstance(value, str):
            return value.strip() or None
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
    resolution_note: str | None


class IssuePage(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[IssueOut]
    total: int
    page: int
    per_page: int
    pages: int


class Period(StrEnum):
    """Dashboard time window: the last 7, 30 or 90 local calendar days, or all time."""

    DAYS_7 = "7"
    DAYS_30 = "30"
    DAYS_90 = "90"
    ALL = "all"

    @property
    def days(self) -> int | None:
        return None if self is Period.ALL else int(self.value)


class CategoryCount(BaseModel):
    category: Category
    label: str
    count: int
    # How many of those issues are still open.
    open: int


class ClinicCount(BaseModel):
    clinic: str
    count: int
    open: int


class AgeCount(BaseModel):
    # under_1_day, 1_to_7_days, 7_to_30_days or over_30_days
    bucket: str
    count: int


class SeverityCount(BaseModel):
    severity: Severity
    label: str
    count: int


class DayCount(BaseModel):
    day: date
    count: int


class Stats(BaseModel):
    period: Period

    # Backlog: the open issues right now, whatever the period.
    open: int
    open_critical_or_high: int
    # Critical first.
    open_by_severity: list[SeverityCount]
    # How long the open issues have been waiting, youngest bucket first.
    open_by_age: list[AgeCount]
    # The oldest open critical issues, then the oldest open high ones (at most 5).
    needs_attention: list[IssueOut]

    # Flow: what happened in the period (all time when period is "all").
    # Issues created in the period.
    total: int
    # Issues resolved in the period (by resolved_at).
    resolved: int
    # The same two counts for the period just before; None for "all".
    previous_total: int | None
    previous_resolved: int | None
    # Median of (resolved_at - created_at) over issues resolved in the period.
    median_resolution_hours: float | None
    # Issues created in the period, with how many of them are still open.
    by_category: list[CategoryCount]
    by_clinic: list[ClinicCount]
    # One entry per local calendar day of the period (last 30 days for "all"),
    # oldest first, today last.
    created_per_day: list[DayCount]
