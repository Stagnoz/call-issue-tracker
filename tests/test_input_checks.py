"""Server-side checks on the free-text fields: formats, invisible characters and
personal data. The same schema validates the API and the HTML form."""

import pytest

from app.seed import SEED_ISSUES
from tests.conftest import valid_payload


def post(client, **overrides):
    return client.post("/api/issues", json=valid_payload(**overrides))


def error_types(response) -> list[str]:
    return [error["type"] for error in response.json()["detail"]]


@pytest.mark.parametrize(
    "call_id", ["call-7f3a9c21", "CA1234abcd", "2026-09-28T14:05:00", "run_42.b", "20260928143005"]
)
def test_valid_call_ids_are_accepted(client, call_id):
    assert post(client, call_id=call_id).status_code == 201


@pytest.mark.parametrize("call_id", ["call 42", "call/42", "call#42", "<b>42</b>", "chiamata-è"])
def test_call_id_format_is_enforced(client, call_id):
    response = post(client, call_id=call_id)

    assert response.status_code == 422
    assert error_types(response) == ["call_id_format"]


@pytest.mark.parametrize(
    "clinic",
    [
        "Centro Medico Portalba - Milano",
        "Studio Dentistico D'Angelo",
        "Studio Dentistico D’Angelo",
        "Poliambulatorio S. Anna (Sede 2)",
        "Città della Salute & Benessere",
        "Centro Diagnostico Nord/Est",
    ],
)
def test_valid_clinic_names_are_accepted(client, clinic):
    assert post(client, clinic=clinic).status_code == 201


@pytest.mark.parametrize(
    "clinic", ["Clinic <Alpha>", "Clinic_Alpha", "Clinic @ Milano", "Clinic 😀"]
)
def test_clinic_format_is_enforced(client, clinic):
    response = post(client, clinic=clinic)

    assert response.status_code == 422
    assert error_types(response) == ["clinic_format"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("call_id", "call​42"),  # zero-width space
        ("clinic", "Clinic‮Alpha"),  # right-to-left override
        ("description", "Assistant misheard\x00 the caller"),  # control character
    ],
)
def test_invisible_characters_are_rejected(client, field, value):
    response = post(client, **{field: value})

    assert response.status_code == 422
    assert error_types(response) == ["invisible_characters"]


def test_line_breaks_are_allowed_in_the_description(client):
    response = post(client, description="First the slot was wrong.\nThen the call dropped.")

    assert response.status_code == 201


@pytest.mark.parametrize(
    ("description", "kind"),
    [
        ("Caller left the number 347 123 4567 for a callback.", "phone"),
        ("Caller left 3471234567 for a callback.", "phone"),
        ("Assistant read back +39 02 1234 5678 as the clinic line.", "phone"),
        ("Assistant read back 0039-347-1234567.", "phone"),
        ("Landline 0212345678 was repeated twice.", "phone"),
        ("Caller spelled mario.rossi@example.com during the call.", "email"),
        ("Assistant stored RSSMRA85T10A562S as the patient id.", "tax_code"),
        ("Assistant stored rssmra85t10a562s as the patient id.", "tax_code"),
    ],
)
def test_personal_data_in_description_is_rejected(client, description, kind):
    response = post(client, description=description)

    assert response.status_code == 422
    error = response.json()["detail"][0]
    assert error["type"] == "personal_data"
    assert error["ctx"]["kind"] == kind


@pytest.mark.parametrize(
    ("field", "value"),
    [("call_id", "3471234567"), ("clinic", "Studio 02 1234 5678")],
)
def test_personal_data_in_other_fields_is_rejected(client, field, value):
    response = post(client, **{field: value})

    assert error_types(response) == ["personal_data"]


@pytest.mark.parametrize(
    "description",
    [
        "Call on 2026-09-28 14:05 dropped after 40 seconds.",
        "Booked on 28/09/2026 at 14:05 instead of 03.10.2026 at 10:30.",
        "Assistant repeated 'one moment please' for 40 seconds.",
        "Quoted 120 euros instead of 95 for the ultrasound.",
        "Caller asked about the CT with contrast; creatinine test not mentioned.",
        "Integration returned error 500 three times in a row.",
        "Internationalization of the greeting is still missing.",
    ],
)
def test_ordinary_descriptions_are_not_flagged(client, description):
    assert post(client, description=description).status_code == 201


def test_all_seed_rows_pass_the_checks(session):
    # The seed goes through IssueCreate, so a rejected row would fail here.
    from app.seed import seed_if_empty
    from tests.conftest import FIXED_NOW

    assert seed_if_empty(session, now=FIXED_NOW) == len(SEED_ISSUES)


def test_form_shows_the_personal_data_error(client):
    form = {
        "call_id": "call-1",
        "clinic": "Clinic Alpha",
        "description": "Caller left 347 123 4567 for a callback.",
        "category": "other",
        "severity": "low",
    }
    response = client.post("/issues", data=form)

    assert response.status_code == 422
    assert "Remove personal data: this looks like a phone number." in response.text
