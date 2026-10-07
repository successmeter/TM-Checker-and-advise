"""HTTP API and the single-page front end."""

import logging
import os
from contextlib import asynccontextmanager
from datetime import date, datetime
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import autorefresh
from .analysis import DISCLAIMERS, check, with_ai_distinctiveness
from .explain import Explainer, Explanation, ExplanationUnavailable, retrieve
from .manual import ManualIndex
from .models import Application, Report
from .picklist import Picklist, load_classes
from .text import stems
from .register import FixtureRegisterClient, IpAustraliaRegisterClient, RegisterClient
from .register.wording import WordingIndex

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
    heading: str = ""                              # IP Australia's class heading, from the picklist pages
    notes: list[str] = []                          # IP Australia's explanatory notes for the class


class PicklistItemOut(BaseModel):
    id: str
    description: str
    source: str = "picklist"  # "picklist", or "register": accepted wording from registered marks
    uses: int = 0             # for register wording: how many registered marks use it


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


class WordingStatus(BaseModel):
    updated: str
    terms: int
    marks: int


class DataStatus(BaseModel):
    picklist: PicklistStatus
    manual: ManualStatus | None
    wording: WordingStatus | None = None
    auto_update_days: int = 0
    next_auto_update: str | None = None


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


class _WordingFiles:
    """The saved register wording list (data/register_wording.json) once built; reloaded when a refresh replaces it."""

    def __init__(self) -> None:
        self.path = Path(os.environ.get("TM_WORDING", ROOT / "data" / "register_wording.json"))
        self._loaded: float | None = None
        self._index: WordingIndex | None = None

    def get(self) -> WordingIndex | None:
        if not self.path.exists():
            return None
        stamp = self.path.stat().st_mtime
        if stamp != self._loaded:
            self._index, self._loaded = WordingIndex.load(self.path), stamp
        return self._index


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
               manual: ManualIndex | None = None, explainer: Explainer | None = None,
               auto_refresh: bool = False, wording: WordingIndex | None = None,
               ai_checks: bool | None = None) -> FastAPI:
    """ai_checks: run Claude's section 41 check with every check (default: when an API key is set)."""
    register = register or _default_register()
    wording_files = None if wording is not None else _WordingFiles()

    def wi() -> WordingIndex | None:
        return wording if wording_files is None else wording_files.get()
    picklist_files = None if picklist is not None else _PicklistFiles()
    manual_files = None if manual is not None else _ManualFiles()

    def pl() -> Picklist:
        return picklist if picklist_files is None else picklist_files.get()

    def mi() -> ManualIndex | None:
        return manual if manual_files is None else manual_files.get()
    explainer = explainer or Explainer()
    classes = load_classes(ROOT / "data" / "classes.json")
    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if auto_refresh:
            autorefresh.start()  # keeps the picklist and Manual current; see autorefresh.py
        yield

    app = FastAPI(title="TM Advisor", description="Brand filing check for Australian trade mark applicants. Not legal advice.",
                  lifespan=lifespan)

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
        application = Application(mark=request.mark, classes=request.classes, mark_kind=request.mark_kind)
        try:
            report = check(application, register, pl())
        except httpx.HTTPStatusError as e:
            log.warning("Register search failed: %s %s", e, e.response.text[:500])
            raise HTTPException(502, f"IP Australia's register search returned an error ({e.response.status_code}). "
                                     "Please try again; if it keeps happening, check your IP Australia API access.")
        except httpx.HTTPError as e:
            log.warning("Register search failed: %s", e)
            raise HTTPException(502, "Couldn't reach IP Australia's register search. Please try again.")
        if not (ai_checks if ai_checks is not None else Explainer.configured()):
            return report.model_copy(update={"ai_distinctiveness_unavailable": "Not set up: add an Anthropic API key "
                                                                               "to check what the mark means as a whole."})
        try:
            ai = explainer.assess_distinctiveness(application.mark, application.mark_kind, application.classes)
        except ExplanationUnavailable as e:
            log.warning("AI distinctiveness check failed: %s", e, exc_info=e.__cause__)
            return report.model_copy(update={"ai_distinctiveness_unavailable": str(e)})
        return with_ai_distinctiveness(report, ai)

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

    def group(found: list, query: str, keywords: list[str], note: str | None = None,
              kinds: set[str] | None = None) -> FindResponse:
        """Picklist matches, plus accepted wording from registered marks for the same search words."""
        groups: dict[int, list[PicklistItemOut]] = {}
        for cls, items in found:
            groups[cls] = [PicklistItemOut(id=i.id, description=i.description) for i in items]
        order = list(groups)
        extra: dict[int, int] = {}
        for word in keywords[:5]:
            for term in _register_terms(word):
                if term.class_number not in classes:
                    continue
                if kinds and classes[term.class_number].kind not in kinds:
                    continue
                items = groups.setdefault(term.class_number, [])
                if any(i.description.lower() == term.description.lower() for i in items):
                    continue
                items.append(PicklistItemOut(id=f"reg-{term.class_number}-{term.description.lower()}",
                                             description=term.description, source="register", uses=term.uses))
                extra[term.class_number] = extra.get(term.class_number, 0) + term.uses
        wanted = [stems(k) - _MATCH_FILLER for k in keywords]

        def complete(cls: int) -> bool:  # some item in the class contains every word of a search
            return any(w and w <= stems(i.description) for i in groups[cls] for w in wanted)

        full = [c for c in order if complete(c)]
        partial = [c for c in order if not complete(c)]
        from_register = sorted((c for c in groups if c not in order), key=lambda c: -extra.get(c, 0))
        order = full + from_register + partial
        return FindResponse(
            query=query, keywords=keywords, sample_picklist=pl().is_sample, note=note,
            groups=[PicklistGroup(class_number=cls, title=classes[cls].title, kind=classes[cls].kind,
                                  items=groups[cls][:80])
                    for cls in order if groups[cls]])

    def _register_terms(word: str) -> list:
        saved = wi()
        if saved is not None and saved.terms:  # all 45 classes, instantly
            return saved.search(word)
        lookup = getattr(register, "goods_terms", None)
        return lookup(word) if lookup else []

    @app.get("/api/data-status")
    def data_status() -> DataStatus:
        current = pl()
        index = mi()
        manual_status = None
        if index is not None:
            manual_status = ManualStatus(updated=manual_files.updated() if manual_files else "",
                                         pages=index.page_count(), passages=index.count())
        days = autorefresh.interval_days() if auto_refresh else 0
        upcoming = autorefresh.next_due(datetime.now(), days, autorefresh.data_dates()) if days else None
        return DataStatus(picklist=PicklistStatus(sample=current.is_sample, updated=current.updated,
                                                  terms=len(current.items)),
                          manual=manual_status, auto_update_days=days,
                          wording=WordingStatus(updated=saved.updated, terms=len(saved.terms), marks=saved.marks_read)
                          if (saved := wi()) is not None else None,
                          next_auto_update=upcoming.date().isoformat() if upcoming else None)

    @app.get("/api/classes")
    def list_classes() -> list[ClassOut]:
        notes = pl().class_notes
        return [ClassOut(class_number=c.class_number, title=c.title, kind=c.kind,
                         heading=notes.get(c.class_number, {}).get("heading", ""),
                         notes=notes.get(c.class_number, {}).get("notes", []))
                for c in classes.values()]

    @app.get("/api/picklist/find")
    def picklist_find(q: str = Query(min_length=2), mode: str = Query("similar", pattern="^(similar|exact)$"),
                      kinds: str = "goods,services") -> FindResponse:
        kind_set = set(kinds.split(","))
        return group(pl().find(q, mode, kind_set, classes), q, [q], kinds=kind_set)

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
        return group(found, text, keywords, note, kinds=set(request.kinds))

    @app.get("/api/picklist/search")
    def picklist_search(q: str = Query(min_length=2), class_number: int | None = Query(None, ge=1, le=45)) -> list[PicklistHit]:
        return [PicklistHit(class_number=i.class_number, description=i.description) for i in pl().search(q, class_number)]

    return app


_MATCH_FILLER = {"and", "of", "for", "in", "the", "to", "a", "relation", "services", "service"}

_STOP = {"i", "we", "our", "my", "and", "or", "the", "a", "an", "to", "of", "for", "in", "on", "with", "sell", "selling",
         "make", "making", "provide", "providing", "offer", "offering", "run", "running", "business", "company", "do",
         "is", "are", "that", "also", "like", "online", "people", "customers", "products", "services", "stuff"}


def _plain_keywords(text: str) -> list[str]:
    import re
    words = [w for w in re.findall(r"[a-z][a-z-]+", text.lower()) if w not in _STOP and len(w) > 2]
    return list(dict.fromkeys(words))[:12]


app = create_app(auto_refresh=True)
