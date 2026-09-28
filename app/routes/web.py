"""HTML pages. They call the same service functions as the JSON API."""

from datetime import datetime
from pathlib import Path
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db import get_session

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

templates = Jinja2Templates(directory=TEMPLATES_DIR)


def local_time(value: datetime, tz: ZoneInfo) -> str:
    """Format a UTC datetime in the display timezone, e.g. '28 Sep 2026, 14:05'."""
    local = value.astimezone(tz)
    return f"{local.day} {local:%b %Y, %H:%M}"


templates.env.filters["local_time"] = local_time

# HTML pages are not part of the API, so they stay out of /docs.
router = APIRouter(include_in_schema=False)

SessionDep = Annotated[Session, Depends(get_session)]


def render(request: Request, template: str, context: dict, status_code: int = 200) -> HTMLResponse:
    context = {"tz": request.app.state.settings.timezone, **context}
    return templates.TemplateResponse(request, template, context, status_code=status_code)


@router.get("/")
def home() -> RedirectResponse:
    return RedirectResponse("/issues", status_code=303)
