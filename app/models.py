"""SQLAlchemy models: clinics and the issues recorded against them."""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, UTCDateTime


class LabeledEnum(StrEnum):
    @property
    def label(self) -> str:
        """Human label for the UI, e.g. 'patient_identification' -> 'Patient identification'."""
        return self.value.replace("_", " ").capitalize()


class Category(LabeledEnum):
    BOOKING = "booking"
    INFORMATION = "information"
    FORWARDING = "forwarding"
    PATIENT_IDENTIFICATION = "patient_identification"
    TECHNICAL = "technical"
    OTHER = "other"


class Severity(LabeledEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Status(LabeledEnum):
    OPEN = "open"
    RESOLVED = "resolved"


def _enum_type(enum_class: type[StrEnum]) -> Enum:
    # Stored as VARCHAR with a CHECK constraint on the enum values, so the
    # database itself rejects anything outside the allowed set.
    return Enum(
        enum_class,
        name=f"{enum_class.__name__.lower()}_values",
        native_enum=False,
        create_constraint=True,
        length=32,
        values_callable=lambda members: [member.value for member in members],
    )


class Clinic(Base):
    __tablename__ = "clinics"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    # Comparison key: trimmed, inner spaces collapsed, casefolded. The unique
    # constraint makes "Centro X" and " centro  x" the same clinic.
    name_key: Mapped[str] = mapped_column(String(100), unique=True)

    issues: Mapped[list["Issue"]] = relationship(back_populates="clinic")


class Issue(Base):
    __tablename__ = "issues"

    id: Mapped[int] = mapped_column(primary_key=True)
    call_id: Mapped[str] = mapped_column(String(100))
    clinic_id: Mapped[int] = mapped_column(ForeignKey("clinics.id"), index=True)
    description: Mapped[str] = mapped_column(String(2000))
    category: Mapped[Category] = mapped_column(_enum_type(Category))
    severity: Mapped[Severity] = mapped_column(_enum_type(Severity))
    status: Mapped[Status] = mapped_column(_enum_type(Status), default=Status.OPEN)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime())
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    # Optional "what was fixed" note, set when resolving and cleared on reopen.
    resolution_note: Mapped[str | None] = mapped_column(String(500))

    # Every view of an issue shows its clinic, so load it in the same query.
    clinic: Mapped[Clinic] = relationship(back_populates="issues", lazy="joined")

    @property
    def clinic_name(self) -> str:
        return self.clinic.name
