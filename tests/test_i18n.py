"""The Italian version of the interface and the EN/IT switch."""

import string

import pytest

from app import i18n
from app.models import Category, Severity, Status
from tests.conftest import FIXED_NOW, make_issue


def placeholders(text: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


def test_both_languages_have_the_same_keys_and_placeholders():
    english, italian = i18n.TRANSLATIONS["en"], i18n.TRANSLATIONS["it"]

    assert english.keys() == italian.keys()
    for key in english:
        assert english[key].strip() and italian[key].strip(), key
        assert placeholders(english[key]) == placeholders(italian[key]), key


def test_every_enum_value_has_a_label():
    for prefix, enum in (("category", Category), ("severity", Severity), ("status", Status)):
        for member in enum:
            assert f"{prefix}.{member.value}" in i18n.TRANSLATIONS["en"]


@pytest.fixture
def italian(client):
    client.cookies.set(i18n.COOKIE_NAME, "it")
    return client


def test_english_is_the_default(client, sample_issues):
    text = client.get("/issues").text

    assert '<html lang="en">' in text
    assert ">Issues</h1>" in text


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        (
            "/issues",
            ["<h1>Segnalazioni</h1>", "Applica filtri", "Segna come risolta", "Prenotazione"],
        ),
        (
            "/issues/new",
            ["Nuova segnalazione", "Non inserire nomi di pazienti", "Crea segnalazione"],
        ),
        ("/dashboard", ["Segnalazioni totali", "Identificazione paziente", "Ultimi 30 giorni"]),
    ],
)
def test_pages_in_italian(italian, sample_issues, path, expected):
    text = italian.get(path).text

    assert '<html lang="it">' in text
    for fragment in expected:
        assert fragment in text


def test_dates_in_italian(italian, session):
    make_issue(session, now=FIXED_NOW)

    assert "1 set 2026, 14:00" in italian.get("/issues").text


def test_stored_data_is_not_translated(italian, sample_issues):
    text = italian.get("/issues").text

    assert "Clinic Alpha" in text
    assert "Assistant booked a visit on a Sunday; the clinic is closed." in text


def test_form_errors_in_italian(italian):
    form = {
        "call_id": "  ",
        "clinic": "Clinic Alpha",
        "description": "Il chiamante ha lasciato il 347 123 4567.",
        "category": "",
        "severity": "low",
    }
    text = italian.post("/issues", data=form).text

    assert "La segnalazione non è stata salvata." in text
    assert "Campo obbligatorio." in text
    assert "Scegli una delle opzioni." in text
    assert "Rimuovi i dati personali: sembra un numero di telefono." in text


def test_notices_and_not_found_in_italian(italian, sample_issues):
    location = italian.post(
        f"/issues/{sample_issues[0].id}/resolve", follow_redirects=False
    ).headers["location"]

    assert f"Segnalazione #{sample_issues[0].id} risolta." in italian.get(location).text
    assert "La segnalazione #999 non esiste." in italian.post("/issues/999/resolve").text


def test_api_stays_in_english(italian, sample_issues):
    stats = italian.get("/api/stats").json()

    assert stats["by_category"][0]["label"] == "Booking"


def test_switch_sets_cookie_and_returns_to_the_page(client):
    response = client.post(
        "/language", data={"lang": "it", "next": "/issues?status=open"}, follow_redirects=False
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/issues?status=open"
    assert "lang=it" in response.headers["set-cookie"]
    assert "HttpOnly" in response.headers["set-cookie"]
    assert '<html lang="it">' in client.get("/issues").text


@pytest.mark.parametrize("next_url", ["https://example.com", "//example.com", "/\\example.com"])
def test_switch_never_redirects_off_site(client, next_url):
    response = client.post(
        "/language", data={"lang": "it", "next": next_url}, follow_redirects=False
    )

    assert response.headers["location"] == "/issues"


def test_unknown_language_is_ignored(client):
    response = client.post("/language", data={"lang": "de", "next": "/"}, follow_redirects=False)

    assert "set-cookie" not in response.headers
    client.cookies.set(i18n.COOKIE_NAME, "de")
    assert '<html lang="en">' in client.get("/issues").text


def test_switch_after_a_rejected_form_goes_back_to_the_empty_form(client):
    text = client.post("/issues", data={"call_id": ""}).text

    assert '<input type="hidden" name="next" value="/issues/new">' in text


def test_switch_keeps_the_current_filters(client, sample_issues):
    text = client.get("/issues?status=open&category=booking").text

    assert (
        '<input type="hidden" name="next" value="/issues?status=open&amp;category=booking">' in text
    )


@pytest.mark.parametrize(
    ("hours", "english", "italian"),
    [(0.5, "30 min", "30 min"), (5, "5 h", "5 h"), (50, "2 d 2 h", "2 g 2 h")],
)
def test_durations_in_both_languages(hours, english, italian):
    assert i18n.format_duration(hours, "en") == english
    assert i18n.format_duration(hours, "it") == italian
