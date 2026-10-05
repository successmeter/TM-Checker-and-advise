"""HTTP API and the single-page front end."""

import logging
import os
from datetime import date
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


class PicklistStatus(BaseModel):
    sample: bool
    updated: str
    terms: int


class ManualStatus(BaseModel):
    updated: str
    pages: int
    passages: int


class DataStatus(BaseModel):
    picklist: PicklistStatus
    manual: ManualStatus | None


class DescribeRequest(BaseModel):
    text: str
    mode: str = "similar"
    kinds: list[str] = ["goods", "services"]


def _default_register() -> RegisterClient:
    if os.environ.get("TM_REGISTER", "fixture") == "ipaustralia":
        return IpAustraliaRegisterClient.from_env()
    return FixtureRegisterClient.load(os.environ.get("TM_REGISTER_FIXTURE", ROOT / "data" / "register_fixture.json"))


class _PicklistFiles:
    """The full picklist if it has been downloaded, else the sample; reloaded when a refresh replaces the file."""

    def __init__(self) -> None:
        self._loaded: tuple[Path, float] | None = None
        self._picklist: Picklist | None = None

    def _path(self) -> Path:
        if os.environ.get("TM_PICKLIST"):
            return Path(os.environ["TM_PICKLIST"])
        full = ROOT / "data" / "picklist.json"
        return full if full.exists() else ROOT / "data" / "picklist_sample.json"

    def get(self) -> Picklist:
        path = self._path()
        stamp = (path, path.stat().st_mtime)
        if stamp != self._loaded:
            self._picklist, self._loaded = Picklist.load(path), stamp
        return self._picklist


class _ManualFiles:
    """The Manual index once it exists (it may be built while the server runs)."""

    def __init__(self) -> None:
        self.path = Path(os.environ.get("TM_MANUAL_INDEX", ROOT / "data" / "manual" / "manual.sqlite"))
        self._index: ManualIndex | None = None

    def get(self) -> ManualIndex | None:
        if self._index is None and self.path.exists():
            self._index = ManualIndex(self.path)
        return self._index

    def updated(self) -> str:
        pages = self.path.parent / "pages.jsonl"
        source = pages if pages.exists() else self.path
        return date.fromtimestamp(source.stat().st_mtime).isoformat() if source.exists() else ""


def create_app(register: RegisterClient | None = None, picklist: Picklist | None = None,
               manual: ManualIndex | None = None, explainer: Explainer | None = None) -> FastAPI:
    register = register or _default_register()
    picklist_files = None if picklist is not None else _PicklistFiles()
    manual_files = None if manual is not None else _ManualFiles()

    def pl() -> Picklist:
        return picklist if picklist_files is None else picklist_files.get()

    def mi() -> ManualIndex | None:
        return manual if manual_files is None else manual_files.get()
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
                     register, pl())

    @app.post("/api/explain")
    def run_explain(request: CheckRequest) -> ExplainResponse:
        report = run_check(request)
        index = mi()
        excerpts = retrieve(report, index) if index is not None else []
        try:
            explanation, reason = explainer.explain(report, excerpts), None
        except ExplanationUnavailable as e:
            explanation, reason = None, str(e)
            log.warning("Explanation failed: %s", e, exc_info=e.__cause__)
        return ExplainResponse(report=report, explanation=explanation, unavailable_reason=reason,
                               manual_excerpts_used=len(excerpts))

    def group(found: list, query: str, keywords: list[str], note: str | None = None) -> FindResponse:
        return FindResponse(
            query=query, keywords=keywords, sample_picklist=pl().is_sample, note=note,
            groups=[PicklistGroup(class_number=cls, title=classes[cls].title, kind=classes[cls].kind,
                                  items=[PicklistItemOut(id=i.id, description=i.description) for i in items])
                    for cls, items in found])

    @app.get("/api/data-status")
    def data_status() -> DataStatus:
        current = pl()
        index = mi()
        manual_status = None
        if index is not None:
            manual_status = ManualStatus(updated=manual_files.updated() if manual_files else "",
                                         pages=index.page_count(), passages=index.count())
        return DataStatus(picklist=PicklistStatus(sample=current.is_sample, updated=current.updated,
                                                  terms=len(current.items)),
                          manual=manual_status)

    @app.get("/api/classes")
    def list_classes() -> list[ClassOut]:
        return [ClassOut(class_number=c.class_number, title=c.title, kind=c.kind) for c in classes.values()]

    @app.get("/api/picklist/find")
    def picklist_find(q: str = Query(min_length=2), mode: str = Query("similar", pattern="^(similar|exact)$"),
                      kinds: str = "goods,services") -> FindResponse:
        return group(pl().find(q, mode, set(kinds.split(",")), classes), q, [q])

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
            for cls, items in pl().find(keyword, request.mode, set(request.kinds), classes, per_class=25):
                if cls not in merged:
                    merged[cls] = {}
                    order.append(cls)
                for item in items:
                    merged[cls].setdefault(item.id, item)
        found = [(cls, list(merged[cls].values())) for cls in order]
        return group(found, text, keywords, note)

    @app.get("/api/picklist/search")
    def picklist_search(q: str = Query(min_length=2), class_number: int | None = Query(None, ge=1, le=45)) -> list[PicklistHit]:
        return [PicklistHit(class_number=i.class_number, description=i.description) for i in pl().search(q, class_number)]

    return app


_STOP = {"i", "we", "our", "my", "and", "or", "the", "a", "an", "to", "of", "for", "in", "on", "with", "sell", "selling",
         "make", "making", "provide", "providing", "offer", "offering", "run", "running", "business", "company", "do",
         "is", "are", "that", "also", "like", "online", "people", "customers", "products", "services", "stuff"}


def _plain_keywords(text: str) -> list[str]:
    import re
    words = [w for w in re.findall(r"[a-z][a-z-]+", text.lower()) if w not in _STOP and len(w) > 2]
    return list(dict.fromkeys(words))[:12]


app = create_app()
