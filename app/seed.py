"""Demo data: 44 hand-written issues across six fictional clinics.

Run manually with `python -m app.seed`. Seeding only ever happens on an empty
database, so running it twice, or on a database with real data, does nothing.
"""

import random
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import services
from app.config import load_settings
from app.db import init_db, make_engine, make_session_factory
from app.models import Category, Issue, Severity
from app.schemas import IssueCreate

# Invented clinic names. Any match with a real clinic is unintended.
PORTALBA = "Centro Medico Portalba - Milano"
LAGO = "Studio Dentistico Lago - Como"
COLLE_ALTO = "Poliambulatorio Colle Alto - Bergamo"
MERIDIANA = "Centro Radiologico Meridiana - Brescia"
TRE_PONTI = "Studio Cardiologico Tre Ponti - Pavia"
VILLA_GLICINE = "Ambulatorio Villa Glicine - Monza"

BOOKING = Category.BOOKING
INFORMATION = Category.INFORMATION
FORWARDING = Category.FORWARDING
IDENTIFICATION = Category.PATIENT_IDENTIFICATION
TECHNICAL = Category.TECHNICAL
OTHER = Category.OTHER

LOW = Severity.LOW
MEDIUM = Severity.MEDIUM
HIGH = Severity.HIGH
CRITICAL = Severity.CRITICAL


@dataclass(frozen=True)
class SeedIssue:
    clinic: str
    days_ago: int
    hour_utc: int
    category: Category
    severity: Severity
    resolved_after_hours: int | None
    description: str
    same_call_as_previous: bool = False


# fmt: off
SEED_ISSUES = [
    # Centro Medico Portalba - Milano: multi-specialty, the noisiest clinic.
    SeedIssue(PORTALBA, 2, 8, BOOKING, HIGH, None,
              "Assistant booked a dermatology visit on a Sunday; the clinic is closed on "
              "weekends."),
    SeedIssue(PORTALBA, 41, 7, INFORMATION, MEDIUM, 20,
              "Caller asked for fasting instructions before a blood test; assistant said no "
              "preparation was needed."),
    SeedIssue(PORTALBA, 5, 9, BOOKING, CRITICAL, None,
              "Assistant confirmed an orthopedic visit in a slot that was already taken; the "
              "management software now shows a double booking."),
    SeedIssue(PORTALBA, 9, 14, FORWARDING, MEDIUM, None,
              "Assistant did not transfer to an operator after the caller asked twice to speak "
              "to a human."),
    SeedIssue(PORTALBA, 33, 10, BOOKING, MEDIUM, 30,
              "Caller asked to move an ultrasound to the afternoon; assistant cancelled the "
              "original slot without booking a new one."),
    SeedIssue(PORTALBA, 1, 11, TECHNICAL, MEDIUM, None,
              "About four seconds of silence before each answer during the morning peak; the "
              "caller asked twice whether anyone was there."),
    SeedIssue(PORTALBA, 47, 15, INFORMATION, MEDIUM, 72,
              "Assistant gave the old Saturday opening hours (8-13); the clinic now closes at 12 "
              "on Saturdays."),
    SeedIssue(PORTALBA, 12, 8, IDENTIFICATION, CRITICAL, None,
              "Caller identified as another patient with the same surname; phone number shared "
              "by family. The other patient's upcoming appointment was read out."),
    SeedIssue(PORTALBA, 55, 13, BOOKING, LOW, 48,
              "Booking confirmation read the date as 'the third of the tenth' instead of the "
              "weekday and month name."),
    SeedIssue(PORTALBA, 3, 10, BOOKING, HIGH, None,
              "Management software integration timed out; assistant told the caller the visit "
              "was booked but no appointment was created."),
    SeedIssue(PORTALBA, 26, 16, FORWARDING, CRITICAL, 4,
              "Caller described chest pain; assistant kept offering booking slots instead of "
              "advising emergency services and transferring to staff."),
    SeedIssue(PORTALBA, 18, 12, INFORMATION, LOW, None,
              "Assistant mispronounced the clinic's street name; the caller understood it anyway."),
    SeedIssue(PORTALBA, 7, 9, TECHNICAL, HIGH, None,
              "Call dropped right after the caller gave their date of birth; they had to call "
              "back and start over."),
    SeedIssue(PORTALBA, 38, 14, OTHER, MEDIUM, 120,
              "Caller asked for a copy of an invoice for a past visit; assistant said it was "
              "impossible instead of explaining the email request process."),
    # Studio Dentistico Lago - Como: dentistry.
    SeedIssue(LAGO, 4, 7, BOOKING, MEDIUM, None,
              "Assistant booked a dental cleaning with the orthodontist instead of the hygienist."),
    SeedIssue(LAGO, 29, 8, BOOKING, HIGH, 6,
              "Caller needed an urgent appointment for a broken crown; assistant offered the "
              "first slot in three weeks without checking the same-day emergency slots."),
    SeedIssue(LAGO, 11, 15, INFORMATION, HIGH, None,
              "Caller asked whether blood thinners must be stopped before an extraction; "
              "assistant answered yes instead of referring the question to the dentist."),
    SeedIssue(LAGO, 44, 9, IDENTIFICATION, MEDIUM, 50,
              "Assistant did not recognize a returning patient calling from a new mobile number "
              "and started a new-patient registration."),
    SeedIssue(LAGO, 15, 13, FORWARDING, LOW, None,
              "Transfer to the front desk worked, but the assistant did not tell the caller they "
              "were being transferred."),
    SeedIssue(LAGO, 6, 10, TECHNICAL, MEDIUM, None,
              "Speech-to-text heard 'impianto' as 'in pianto'; assistant asked the caller to "
              "repeat three times."),
    SeedIssue(LAGO, 36, 11, BOOKING, LOW, 24,
              "Assistant offered a slot during the lunch break (13-14); staff moved it manually."),
    SeedIssue(LAGO, 52, 14, INFORMATION, MEDIUM, 96,
              "Assistant quoted a price for teeth whitening that is no longer on the clinic's "
              "price list."),
    SeedIssue(LAGO, 2, 16, BOOKING, MEDIUM, None,
              "Assistant accepted a request for a six-month check-up reminder, but the reminder "
              "was never saved."),
    # Poliambulatorio Colle Alto - Bergamo: pediatrics, physiotherapy, gynecology.
    SeedIssue(COLLE_ALTO, 8, 9, BOOKING, HIGH, None,
              "Assistant booked a pediatric visit under the parent's record instead of the "
              "child's."),
    SeedIssue(COLLE_ALTO, 8, 9, IDENTIFICATION, HIGH, None,
              "Same call: assistant matched the caller to a patient with the same name but a "
              "different date of birth, and did not ask for confirmation.",
              same_call_as_previous=True),
    SeedIssue(COLLE_ALTO, 40, 12, INFORMATION, HIGH, 26,
              "Caller asked whether physiotherapy needs a doctor's referral; assistant said no, "
              "but the clinic requires one for the reduced fee."),
    SeedIssue(COLLE_ALTO, 13, 7, FORWARDING, MEDIUM, None,
              "Caller asked for the gynecology nurse; assistant said the service did not exist "
              "instead of transferring the call."),
    SeedIssue(COLLE_ALTO, 58, 15, TECHNICAL, LOW, 200,
              "Hold music restarted from the beginning every time the caller spoke."),
    SeedIssue(COLLE_ALTO, 3, 13, BOOKING, MEDIUM, None,
              "Caller asked for two physiotherapy sessions in consecutive weeks; assistant booked "
              "both on the same day."),
    SeedIssue(COLLE_ALTO, 22, 10, INFORMATION, LOW, 30,
              "Assistant said parking is free; it is free only for the first hour."),
    # Centro Radiologico Meridiana - Brescia: imaging.
    SeedIssue(MERIDIANA, 10, 8, INFORMATION, CRITICAL, None,
              "Caller asked how to prepare for an abdominal CT with contrast; assistant did not "
              "mention fasting or the required creatinine test."),
    SeedIssue(MERIDIANA, 34, 11, BOOKING, CRITICAL, 3,
              "Assistant booked an MRI after the caller mentioned a pacemaker, without flagging "
              "it to staff."),
    SeedIssue(MERIDIANA, 5, 14, FORWARDING, HIGH, None,
              "Caller asked to speak with the radiologist about a report; assistant ended the "
              "call instead of transferring to the front desk."),
    SeedIssue(MERIDIANA, 19, 9, IDENTIFICATION, LOW, None,
              "Caller gave their tax code, but the assistant still asked for surname and date of "
              "birth twice."),
    SeedIssue(MERIDIANA, 49, 16, TECHNICAL, MEDIUM, 72,
              "Assistant answered in English for the first two turns although the caller spoke "
              "Italian."),
    SeedIssue(MERIDIANA, 14, 12, INFORMATION, MEDIUM, None,
              "Assistant said mammography results are sent by email; the clinic only releases "
              "them at the desk or on the patient portal."),
    # Studio Cardiologico Tre Ponti - Pavia: cardiology.
    SeedIssue(TRE_PONTI, 27, 8, BOOKING, MEDIUM, 52,
              "Assistant booked a Holter ECG fitting on a Friday; the device must be returned "
              "after 24 hours and the clinic is closed on Saturdays."),
    SeedIssue(TRE_PONTI, 1, 9, FORWARDING, CRITICAL, None,
              "Caller mentioned fainting that morning after starting a new medication; assistant "
              "did not transfer to staff or suggest calling emergency services."),
    SeedIssue(TRE_PONTI, 16, 13, INFORMATION, HIGH, None,
              "Assistant told the caller to stop beta blockers before a stress test; the clinic's "
              "instruction is to ask the cardiologist first."),
    SeedIssue(TRE_PONTI, 45, 10, IDENTIFICATION, LOW, 12,
              "Assistant greeted the caller with the account holder's name; the caller was the "
              "spouse sharing the same number."),
    SeedIssue(TRE_PONTI, 4, 15, TECHNICAL, HIGH, None,
              "Integration error during booking; assistant repeated 'one moment please' for 40 "
              "seconds before the call dropped."),
    # Ambulatorio Villa Glicine - Monza: general medicine.
    SeedIssue(VILLA_GLICINE, 31, 7, FORWARDING, MEDIUM, 18,
              "Caller asked twice to cancel with a person; assistant looped back to the "
              "cancellation menu."),
    SeedIssue(VILLA_GLICINE, 6, 11, IDENTIFICATION, HIGH, None,
              "Assistant failed to recognize a registered patient and asked for details already "
              "on file; the caller hung up."),
    SeedIssue(VILLA_GLICINE, 20, 14, OTHER, LOW, None,
              "Caller wanted to leave a compliment for a nurse; assistant had no way to record "
              "feedback but said it would pass it on."),
]
# fmt: on


def seed_if_empty(session: Session, now: datetime | None = None) -> int:
    """Insert the demo issues if the database has none. Returns how many were inserted."""
    if session.scalar(select(func.count(Issue.id))):
        return 0

    now = now or services.utc_now()
    rng = random.Random(42)
    call_id = ""
    for row in SEED_ISSUES:
        if not row.same_call_as_previous:
            call_id = f"call-{rng.getrandbits(32):08x}"
        created_at = (now - timedelta(days=row.days_ago)).replace(
            hour=row.hour_utc, minute=rng.randrange(60), second=0, microsecond=0
        )
        data = IssueCreate(
            call_id=call_id,
            clinic=row.clinic,
            description=row.description,
            category=row.category,
            severity=row.severity,
        )
        issue = services.create_issue(session, data, now=created_at)
        if row.resolved_after_hours is not None:
            resolved_at = created_at + timedelta(hours=row.resolved_after_hours)
            services.resolve_issue(session, issue.id, now=resolved_at)
    return len(SEED_ISSUES)


def main() -> None:
    settings = load_settings()
    engine = make_engine(settings.database_url)
    init_db(engine)
    with make_session_factory(engine)() as session:
        inserted = seed_if_empty(session)
        total = session.scalar(select(func.count(Issue.id)))
    engine.dispose()
    if inserted:
        clinics = len({row.clinic for row in SEED_ISSUES})
        print(f"Seeded {inserted} demo issues across {clinics} clinics.")
    else:
        print(f"Database already has {total} issues; nothing seeded.")


if __name__ == "__main__":
    main()
