"""HTML dashboard routes. Deliberately separate from app/api/routes.py (the JSON
API): these return rendered pages, not API responses, and the pages themselves
call the JSON API via client-side fetch() rather than the server pre-fetching
data into the template — keeping the two concerns (API vs. presentation) apart.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))


@router.get("/")
def investigate_page(request: Request):
    return templates.TemplateResponse(request, "index.html", {"active": "investigate"})


@router.get("/history")
def history_page(request: Request):
    return templates.TemplateResponse(request, "history.html", {"active": "history"})


@router.get("/metrics")
def metrics_page(request: Request):
    return templates.TemplateResponse(request, "metrics.html", {"active": "metrics"})
