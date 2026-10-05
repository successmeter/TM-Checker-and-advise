"""HTTP API and the single-page front end."""

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .analysis import DISCLAIMERS, check
from .explain import Explainer, Explanation, ExplanationUnavailable, retrieve
from .manual import ManualIndex
from .models import Application, Report
from .picklist import Picklist
from .register import FixtureRegisterClient, IpAustraliaRegisterClient, RegisterClient

ROOT = Path(__file__).resolve().parents[1]
STATIC = Path(__file__).resolve().parent / "static"


class CheckRequest(Application):
    consent: bool = False


class ExplainResponse(BaseModel):
    report: Report
    explanation: Explanation | None
    unavailable_reason: str | None
    manual_excerpts_used: int


class PicklistHit(BaseModel):
    class_number: int
    description: str


def _default_register() -> RegisterClient:
    if os.environ.get("TM_REGISTER", "fixture") == "ipaustralia":
        return IpAustraliaRegisterClient.from_env()
    return FixtureRegisterClient.load(os.environ.get("TM_REGISTER_FIXTURE", ROOT / "data" / "register_fixture.json"))


def _default_picklist() -> Picklist:
    full = ROOT / "data" / "picklist.json"
    return Picklist.load(os.environ.get("TM_PICKLIST", full if full.exists() else ROOT / "data" / "picklist_sample.json"))


def _default_manual() -> ManualIndex | None:
    path = Path(os.environ.get("TM_MANUAL_INDEX", ROOT / "data" / "manual" / "manual.sqlite"))
    return ManualIndex(path) if path.exists() else None


def create_app(register: RegisterClient | None = None, picklist: Picklist | None = None,
               manual: ManualIndex | None = None, explainer: Explainer | None = None) -> FastAPI:
    register = register or _default_register()
    picklist = picklist or _default_picklist()
    manual = manual if manual is not None else _default_manual()
    explainer = explainer or Explainer()
    app = FastAPI(title="TM Advisor", description="Brand filing check for Australian trade mark applicants. Not legal advice.")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC / "index.html")

    @app.get("/api/disclaimers")
    def disclaimers() -> list[str]:
        return DISCLAIMERS

    @app.post("/api/check")
    def run_check(request: CheckRequest) -> Report:
        if not request.consent:
            raise HTTPException(422, "Please confirm you understand this is not legal advice before running a check.")
        return check(Application(mark=request.mark, classes=request.classes), register, picklist)

    @app.post("/api/explain")
    def run_explain(request: CheckRequest) -> ExplainResponse:
        report = run_check(request)
        excerpts = retrieve(report, manual) if manual is not None else []
        try:
            explanation, reason = explainer.explain(report, excerpts), None
        except ExplanationUnavailable as e:
            explanation, reason = None, str(e)
        return ExplainResponse(report=report, explanation=explanation, unavailable_reason=reason,
                               manual_excerpts_used=len(excerpts))

    @app.get("/api/picklist/search")
    def picklist_search(q: str = Query(min_length=2), class_number: int | None = Query(None, ge=1, le=45)) -> list[PicklistHit]:
        return [PicklistHit(class_number=i.class_number, description=i.description) for i in picklist.search(q, class_number)]

    return app


app = create_app()
