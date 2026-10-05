"""HTTP API and the single-page front end."""

import logging
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .analysis import DISCLAIMERS, check
from .explain import Explainer, Explanation, ExplanationUnavailable, retrieve
from .manual import ManualIndex
from .models import Application, Report
from .picklist import Picklist, load_classes
from .register import FixtureRegisterClient, IpAustraliaRegisterClient, RegisterClient

ROOT = Path(__file__).resolve().parents[1]
STATIC = Path(__file__).resolve().parent / "static"
log = logging.getLogger("uvicorn.error")  # shows in the server window


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


class ClassOut(BaseModel):
    class_number: int
    title: str
    kind: str


class PicklistItemOut(BaseModel):
    id: str
    description: str


class PicklistGroup(BaseModel):
    class_number: int
    title: str
    kind: str
    items: list[PicklistItemOut]


class FindResponse(BaseModel):
    query: str
    keywords: list[str]
    groups: list[PicklistGroup]
    sample_picklist: bool
    note: str | None = None


class DescribeRequest(BaseModel):
    text: str
    mode: str = "similar"
    kinds: list[str] = ["goods", "services"]


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
    classes = load_classes(ROOT / "data" / "classes.json")
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
        return check(Application(mark=request.mark, classes=request.classes, mark_kind=request.mark_kind),
                     register, picklist)

    @app.post("/api/explain")
    def run_explain(request: CheckRequest) -> ExplainResponse:
        report = run_check(request)
        excerpts = retrieve(report, manual) if manual is not None else []
        try:
            explanation, reason = explainer.explain(report, excerpts), None
        except ExplanationUnavailable as e:
            explanation, reason = None, str(e)
            log.warning("Explanation failed: %s", e, exc_info=e.__cause__)
        return ExplainResponse(report=report, explanation=explanation, unavailable_reason=reason,
                               manual_excerpts_used=len(excerpts))

    def group(found: list, query: str, keywords: list[str], note: str | None = None) -> FindResponse:
        return FindResponse(
            query=query, keywords=keywords, sample_picklist=picklist.is_sample, note=note,
            groups=[PicklistGroup(class_number=cls, title=classes[cls].title, kind=classes[cls].kind,
                                  items=[PicklistItemOut(id=i.id, description=i.description) for i in items])
                    for cls, items in found])

    @app.get("/api/classes")
    def list_classes() -> list[ClassOut]:
        return [ClassOut(class_number=c.class_number, title=c.title, kind=c.kind) for c in classes.values()]

    @app.get("/api/picklist/find")
    def picklist_find(q: str = Query(min_length=2), mode: str = Query("similar", pattern="^(similar|exact)$"),
                      kinds: str = "goods,services") -> FindResponse:
        return group(picklist.find(q, mode, set(kinds.split(",")), classes), q, [q])

    @app.post("/api/picklist/describe")
    def picklist_describe(request: DescribeRequest) -> FindResponse:
        """A sentence about the business -> search words (Claude, or plain words without it) -> grouped matches."""
        text = " ".join(request.text.split())[:1000]
        if len(text) < 2:
            raise HTTPException(422, "Tell us what your business does.")
        note = None
        try:
            keywords = explainer.keywords(text)
        except ExplanationUnavailable as e:
            log.warning("Keyword extraction failed: %s", e, exc_info=e.__cause__)
            keywords = _plain_keywords(text)
            note = "Searched for the main words in your description (smart matching isn't available right now)."
        merged: dict[int, dict[str, object]] = {}
        order: list[int] = []
        for keyword in keywords:
            for cls, items in picklist.find(keyword, request.mode, set(request.kinds), classes, per_class=25):
                if cls not in merged:
                    merged[cls] = {}
                    order.append(cls)
                for item in items:
                    merged[cls].setdefault(item.id, item)
        found = [(cls, list(merged[cls].values())) for cls in order]
        return group(found, text, keywords, note)

    @app.get("/api/picklist/search")
    def picklist_search(q: str = Query(min_length=2), class_number: int | None = Query(None, ge=1, le=45)) -> list[PicklistHit]:
        return [PicklistHit(class_number=i.class_number, description=i.description) for i in picklist.search(q, class_number)]

    return app


_STOP = {"i", "we", "our", "my", "and", "or", "the", "a", "an", "to", "of", "for", "in", "on", "with", "sell", "selling",
         "make", "making", "provide", "providing", "offer", "offering", "run", "running", "business", "company", "do",
         "is", "are", "that", "also", "like", "online", "people", "customers", "products", "services", "stuff"}


def _plain_keywords(text: str) -> list[str]:
    import re
    words = [w for w in re.findall(r"[a-z][a-z-]+", text.lower()) if w not in _STOP and len(w) > 2]
    return list(dict.fromkeys(words))[:12]


app = create_app()
