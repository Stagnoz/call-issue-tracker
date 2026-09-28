"""JSON API under /api, plus the /health endpoint."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session

from app import services
from app.db import get_session
from app.models import Issue
from app.schemas import (
    IssueCreate,
    IssueListParams,
    IssueOut,
    IssuePage,
    ResolveRequest,
    Stats,
)

router = APIRouter()

SessionDep = Annotated[Session, Depends(get_session)]


def _get_or_404(session: Session, issue_id: int) -> Issue:
    issue = services.get_issue(session, issue_id)
    if issue is None:
        raise HTTPException(status_code=404, detail="Issue not found")
    return issue


@router.post(
    "/api/issues",
    status_code=201,
    response_model=IssueOut,
    tags=["issues"],
    summary="Create an issue",
    description="New issues are always open. status and created_at are set by the server; "
    "sending them is rejected with 422.",
)
def create_issue(data: IssueCreate, session: SessionDep) -> Issue:
    return services.create_issue(session, data)


@router.get(
    "/api/issues",
    response_model=IssuePage,
    tags=["issues"],
    summary="List issues, newest first",
    description="Filters combine with AND. Clinic matching ignores case and extra spaces. "
    "25 issues per page.",
)
def list_issues(params: Annotated[IssueListParams, Query()], session: SessionDep) -> services.Page:
    return services.list_issues(session, params, page=params.page)


@router.get(
    "/api/issues/{issue_id}",
    response_model=IssueOut,
    tags=["issues"],
    summary="Get one issue",
    responses={404: {"description": "Issue not found"}},
)
def get_issue(issue_id: int, session: SessionDep) -> Issue:
    return _get_or_404(session, issue_id)


@router.post(
    "/api/issues/{issue_id}/resolve",
    response_model=IssueOut,
    tags=["issues"],
    summary="Mark an issue as resolved",
    description="Sets status to resolved and records resolved_at. The body is optional: "
    '{"note": "what was fixed"}. Idempotent: resolving an already resolved issue returns it '
    "unchanged, keeping the first resolution time and note.",
    responses={404: {"description": "Issue not found"}},
)
def resolve_issue(issue_id: int, session: SessionDep, data: ResolveRequest | None = None) -> Issue:
    note = data.note if data else None
    issue = services.resolve_issue(session, issue_id, note=note)
    if issue is None:
        raise HTTPException(status_code=404, detail="Issue not found")
    return issue


@router.post(
    "/api/issues/{issue_id}/reopen",
    response_model=IssueOut,
    tags=["issues"],
    summary="Reopen a resolved issue",
    description="Sets status back to open and clears resolved_at and the resolution note. "
    "Reopening an open issue returns it unchanged.",
    responses={404: {"description": "Issue not found"}},
)
def reopen_issue(issue_id: int, session: SessionDep) -> Issue:
    issue = services.reopen_issue(session, issue_id)
    if issue is None:
        raise HTTPException(status_code=404, detail="Issue not found")
    return issue


@router.get(
    "/api/stats",
    response_model=Stats,
    tags=["stats"],
    summary="Dashboard statistics",
    description="Total, open and resolved issues, median time to resolution, issues by "
    "category (including zero counts) and by clinic, open issues by severity, and issues "
    "created per day over the last 30 days (days in APP_TIMEZONE).",
)
def get_stats(request: Request, session: SessionDep) -> Stats:
    return services.get_stats(session, tz=request.app.state.settings.timezone)


@router.get(
    "/health",
    tags=["health"],
    summary="Health check",
    description="Returns ok if the database answers a trivial query, 503 otherwise.",
    responses={503: {"description": "Database unreachable"}},
)
def health(session: SessionDep) -> JSONResponse:
    if services.database_is_reachable(session):
        return JSONResponse({"status": "ok"})
    return JSONResponse({"status": "unavailable"}, status_code=503)


@router.get("/docs", include_in_schema=False)
def api_docs() -> HTMLResponse:
    """Swagger UI from files shipped with the app, so it works without internet access."""
    return get_swagger_ui_html(
        openapi_url="/openapi.json",
        title="Call Issue Tracker - API docs",
        swagger_js_url="/static/swagger-ui/swagger-ui-bundle.js",
        swagger_css_url="/static/swagger-ui/swagger-ui.css",
        swagger_favicon_url="data:,",
    )
