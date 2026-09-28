"""User-interface translations (English and Italian) and language-aware formatting.

Only the HTML interface is translated. Stored data (descriptions, clinic
names, notes) is shown as written, and the JSON API stays in English so its
contract does not depend on the caller's language.
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi import Request

LANGUAGES = ("en", "it")
DEFAULT_LANGUAGE = "en"
COOKIE_NAME = "lang"

# Written out instead of using the OS locale, which differs between machines
# and containers.
MONTHS = {
    "en": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
    "it": ["gen", "feb", "mar", "apr", "mag", "giu", "lug", "ago", "set", "ott", "nov", "dic"],
}

TRANSLATIONS: dict[str, dict[str, str]] = {
    "en": {
        # Layout
        "app.name": "Call Issue Tracker",
        "nav.main": "Main",
        "nav.issues": "Issues",
        "nav.new": "New issue",
        "nav.dashboard": "Dashboard",
        "lang.label": "Language",
        "lang.en": "English",
        "lang.it": "Italian",
        # Enum labels
        "category.booking": "Booking",
        "category.information": "Information",
        "category.forwarding": "Forwarding",
        "category.patient_identification": "Patient identification",
        "category.technical": "Technical",
        "category.other": "Other",
        "severity.low": "Low",
        "severity.medium": "Medium",
        "severity.high": "High",
        "severity.critical": "Critical",
        "status.open": "Open",
        "status.resolved": "Resolved",
        # Field names
        "field.id": "ID",
        "field.created": "Created",
        "field.call_id": "Call ID",
        "field.clinic": "Clinic",
        "field.category": "Category",
        "field.severity": "Severity",
        "field.status": "Status",
        "field.description": "Description",
        # Issue list
        "list.title": "Issues",
        "list.summary_one": "1 issue, newest first",
        "list.summary_many": "{count} issues, newest first",
        "list.summary_filtered_one": "1 issue matching these filters, newest first",
        "list.summary_filtered_many": "{count} issues matching these filters, newest first",
        "list.export": "Export CSV",
        "notice.created": "Issue #{id} created.",
        "notice.resolved": "Issue #{id} resolved.",
        "notice.reopened": "Issue #{id} reopened.",
        "notice.filters_invalid": (
            "Some filter values in this link are not valid, so no filters are applied."
        ),
        "notice.note_invalid": "Issue #{id} was not resolved. Please fix the note.",
        "filters.label": "Filter issues",
        "filters.search": "Search",
        "filters.search_placeholder": "Description or call ID",
        "filters.all_clinics": "All clinics",
        "filters.all_categories": "All categories",
        "filters.all_statuses": "All statuses",
        "filters.all_severities": "All severities",
        "filters.apply": "Apply filters",
        "filters.clear": "Clear filters",
        "resolve.open": "Mark as resolved",
        "resolve.note_label": "What was fixed? (optional)",
        "resolve.submit": "Resolve",
        "reopen.submit": "Reopen",
        "pagination.label": "Pagination",
        "pagination.previous": "Previous",
        "pagination.next": "Next",
        "pagination.page": "Page {page} of {pages}",
        "empty.filtered": "No issues match these filters.",
        "empty.none": "No issues yet.",
        "empty.create_first": "Record the first one",
        # New issue form
        "form.title": "New issue",
        "form.subtitle": (
            "Record a problem found while reviewing an assistant call. New issues start as open."
        ),
        "form.not_saved": "The issue was not saved. Please fix the highlighted fields.",
        "form.clinic_hint": "Pick an existing clinic or type a new name.",
        "form.privacy_hint": (
            "Do not include patient names, phone numbers or health details. "
            "Reference the call by call_id."
        ),
        "form.choose": "Choose...",
        "form.submit": "Create issue",
        "form.cancel": "Cancel",
        # Dashboard
        "dashboard.title": "Dashboard",
        "dashboard.subtitle": "Where the assistant goes wrong, across all recorded issues.",
        "dashboard.total": "Total issues",
        "dashboard.open": "Open issues",
        "dashboard.critical_or_high": "Open critical or high",
        "dashboard.resolved": "Resolved",
        "dashboard.median": "Median time to resolution",
        "dashboard.by_severity": "Open issues by severity",
        "dashboard.per_day": "Issues created per day",
        "dashboard.last_days": "Last {days} days",
        "dashboard.by_category": "Issues by category",
        "dashboard.by_clinic": "Issues by clinic",
        "dashboard.no_issues": "No issues recorded yet.",
        # Not found
        "not_found.title": "Not found",
        "not_found.issue": "Issue #{id} does not exist.",
        "not_found.back": "Back to the issue list",
        # Validation errors, by Pydantic error type
        "error.required": "This field is required.",
        "error.too_short": "Must be at least {min} characters.",
        "error.too_long": "Must be at most {max} characters.",
        "error.choose": "Choose one of the options.",
        "error.call_id_format": "Use only letters, digits and - _ . : (no spaces).",
        "error.clinic_format": "Use letters, digits, spaces and . , ' - ( ) & / only.",
        "error.invisible_characters": "Remove control or invisible characters.",
        "error.personal_data.phone": (
            "Remove personal data: this looks like a phone number. Reference the call by call_id."
        ),
        "error.personal_data.email": (
            "Remove personal data: this looks like an email address. Reference the call by call_id."
        ),
        "error.personal_data.tax_code": (
            "Remove personal data: this looks like an Italian tax code. "
            "Reference the call by call_id."
        ),
        "error.invalid": "This value is not valid.",
        # Durations
        "unit.minutes": "min",
        "unit.hours": "h",
        "unit.days": "d",
    },
    "it": {
        # Layout
        "app.name": "Call Issue Tracker",
        "nav.main": "Principale",
        "nav.issues": "Segnalazioni",
        "nav.new": "Nuova segnalazione",
        "nav.dashboard": "Dashboard",
        "lang.label": "Lingua",
        "lang.en": "Inglese",
        "lang.it": "Italiano",
        # Enum labels
        "category.booking": "Prenotazione",
        "category.information": "Informazioni",
        "category.forwarding": "Trasferimento",
        "category.patient_identification": "Identificazione paziente",
        "category.technical": "Tecnico",
        "category.other": "Altro",
        "severity.low": "Bassa",
        "severity.medium": "Media",
        "severity.high": "Alta",
        "severity.critical": "Critica",
        "status.open": "Aperta",
        "status.resolved": "Risolta",
        # Field names
        "field.id": "ID",
        "field.created": "Creata",
        "field.call_id": "ID chiamata",
        "field.clinic": "Clinica",
        "field.category": "Categoria",
        "field.severity": "Gravità",
        "field.status": "Stato",
        "field.description": "Descrizione",
        # Issue list
        "list.title": "Segnalazioni",
        "list.summary_one": "1 segnalazione, dalla più recente",
        "list.summary_many": "{count} segnalazioni, dalla più recente",
        "list.summary_filtered_one": "1 segnalazione corrispondente ai filtri, dalla più recente",
        "list.summary_filtered_many": (
            "{count} segnalazioni corrispondenti ai filtri, dalla più recente"
        ),
        "list.export": "Esporta CSV",
        "notice.created": "Segnalazione #{id} creata.",
        "notice.resolved": "Segnalazione #{id} risolta.",
        "notice.reopened": "Segnalazione #{id} riaperta.",
        "notice.filters_invalid": (
            "Alcuni filtri in questo link non sono validi, quindi non è applicato nessun filtro."
        ),
        "notice.note_invalid": "La segnalazione #{id} non è stata risolta. Correggi la nota.",
        "filters.label": "Filtra le segnalazioni",
        "filters.search": "Cerca",
        "filters.search_placeholder": "Descrizione o ID chiamata",
        "filters.all_clinics": "Tutte le cliniche",
        "filters.all_categories": "Tutte le categorie",
        "filters.all_statuses": "Tutti gli stati",
        "filters.all_severities": "Tutte le gravità",
        "filters.apply": "Applica filtri",
        "filters.clear": "Rimuovi filtri",
        "resolve.open": "Segna come risolta",
        "resolve.note_label": "Cosa è stato corretto? (facoltativo)",
        "resolve.submit": "Risolvi",
        "reopen.submit": "Riapri",
        "pagination.label": "Paginazione",
        "pagination.previous": "Precedente",
        "pagination.next": "Successiva",
        "pagination.page": "Pagina {page} di {pages}",
        "empty.filtered": "Nessuna segnalazione corrisponde ai filtri.",
        "empty.none": "Nessuna segnalazione per ora.",
        "empty.create_first": "Registra la prima",
        # New issue form
        "form.title": "Nuova segnalazione",
        "form.subtitle": (
            "Registra un problema trovato riascoltando una chiamata dell'assistente. "
            "Le nuove segnalazioni partono aperte."
        ),
        "form.not_saved": "La segnalazione non è stata salvata. Correggi i campi evidenziati.",
        "form.clinic_hint": "Scegli una clinica esistente o scrivi un nuovo nome.",
        "form.privacy_hint": (
            "Non inserire nomi di pazienti, numeri di telefono o dati sanitari. "
            "Fai riferimento alla chiamata tramite il call_id."
        ),
        "form.choose": "Scegli...",
        "form.submit": "Crea segnalazione",
        "form.cancel": "Annulla",
        # Dashboard
        "dashboard.title": "Dashboard",
        "dashboard.subtitle": "Dove sbaglia l'assistente, su tutte le segnalazioni registrate.",
        "dashboard.total": "Segnalazioni totali",
        "dashboard.open": "Aperte",
        "dashboard.critical_or_high": "Aperte critiche o alte",
        "dashboard.resolved": "Risolte",
        "dashboard.median": "Tempo mediano di risoluzione",
        "dashboard.by_severity": "Segnalazioni aperte per gravità",
        "dashboard.per_day": "Segnalazioni create al giorno",
        "dashboard.last_days": "Ultimi {days} giorni",
        "dashboard.by_category": "Segnalazioni per categoria",
        "dashboard.by_clinic": "Segnalazioni per clinica",
        "dashboard.no_issues": "Nessuna segnalazione registrata.",
        # Not found
        "not_found.title": "Non trovata",
        "not_found.issue": "La segnalazione #{id} non esiste.",
        "not_found.back": "Torna all'elenco delle segnalazioni",
        # Validation errors, by Pydantic error type
        "error.required": "Campo obbligatorio.",
        "error.too_short": "Servono almeno {min} caratteri.",
        "error.too_long": "Al massimo {max} caratteri.",
        "error.choose": "Scegli una delle opzioni.",
        "error.call_id_format": "Usa solo lettere, cifre e - _ . : (senza spazi).",
        "error.clinic_format": "Usa solo lettere, cifre, spazi e . , ' - ( ) & /.",
        "error.invisible_characters": "Rimuovi i caratteri di controllo o invisibili.",
        "error.personal_data.phone": (
            "Rimuovi i dati personali: sembra un numero di telefono. "
            "Fai riferimento alla chiamata tramite il call_id."
        ),
        "error.personal_data.email": (
            "Rimuovi i dati personali: sembra un indirizzo email. "
            "Fai riferimento alla chiamata tramite il call_id."
        ),
        "error.personal_data.tax_code": (
            "Rimuovi i dati personali: sembra un codice fiscale. "
            "Fai riferimento alla chiamata tramite il call_id."
        ),
        "error.invalid": "Valore non valido.",
        # Durations
        "unit.minutes": "min",
        "unit.hours": "h",
        "unit.days": "g",
    },
}


def get_language(request: Request) -> str:
    """The language chosen with the EN/IT switch (a cookie), English by default."""
    language = request.cookies.get(COOKIE_NAME)
    return language if language in LANGUAGES else DEFAULT_LANGUAGE


def translate(language: str, key: str, **values: object) -> str:
    return TRANSLATIONS[language][key].format(**values)


def format_datetime(value: datetime, tz: ZoneInfo, language: str) -> str:
    """A UTC datetime in the display timezone: '28 Sep 2026, 14:05' / '28 set 2026, 14:05'."""
    local = value.astimezone(tz)
    month = MONTHS[language][local.month - 1]
    return f"{local.day} {month} {local.year}, {local:%H:%M}"


def format_short_date(value: date, language: str) -> str:
    """'28 Sep' / '28 set'."""
    return f"{value.day} {MONTHS[language][value.month - 1]}"


def format_duration(hours: float, language: str) -> str:
    """Readable duration: '45 min', '20 h', '2 d 4 h' ('2 g 4 h' in Italian)."""
    minutes = round(hours * 60)
    if minutes < 60:
        return f"{minutes} {translate(language, 'unit.minutes')}"
    hours_unit = translate(language, "unit.hours")
    whole_hours = round(hours)
    if whole_hours < 48:
        return f"{whole_hours} {hours_unit}"
    days, rest = divmod(whole_hours, 24)
    days_text = f"{days} {translate(language, 'unit.days')}"
    return f"{days_text} {rest} {hours_unit}" if rest else days_text


def error_message(error: dict, language: str) -> str:
    """Short, translated message for one Pydantic validation error."""
    kind = error["type"]
    context = error.get("ctx", {})
    if kind == "string_too_short":
        if not str(error.get("input", "")).strip():
            return translate(language, "error.required")
        return translate(language, "error.too_short", min=context["min_length"])
    if kind == "string_too_long":
        return translate(language, "error.too_long", max=context["max_length"])
    if kind == "enum":
        return translate(language, "error.choose")
    if kind == "personal_data":
        return translate(language, f"error.personal_data.{context['kind']}")
    if kind in ("call_id_format", "clinic_format", "invisible_characters"):
        return translate(language, f"error.{kind}")
    return translate(language, "error.invalid")
