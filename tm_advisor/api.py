"""HTTP API and the single-page front end."""

import base64
import logging
import os
import re
import secrets
from typing import Literal
from contextlib import asynccontextmanager
from datetime import date, datetime
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field, field_validator

from . import autorefresh
from .analysis import DISCLAIMERS, check, with_ai_distinctiveness
from .explain import Explainer, Explanation, ExplanationUnavailable, retrieve
from .manual import ManualIndex
from .mailer import Mailer
from .models import Application, Report, Risk
from .payments import Payments
from .report.build import build_report
from .report.pages import status_page
from .report.render import render_html
from .report.sample import sample_report
from .report.schema import ReportDoc
from .report.worker import ReportWorker, local_now, nice_date, nice_time
from .store import Store
from .picklist import Picklist, load_classes
from .text import stems
from .register import FixtureRegisterClient, IpAustraliaRegisterClient, RegisterClient
from .register.wording import WordingIndex

ROOT = Path(__file__).resolve().parents[1]
STATIC = Path(__file__).resolve().parent / "static"
log = logging.getLogger("uvicorn.error")  # shows in the server window


class CheckRequest(Application):
    consent: bool = False


class Concerns(BaseModel):
    distinctiveness: Literal["none", "possible", "likely"]
    similar_marks: int        # live similar marks rated Medium or High
    wording: int              # terms not on the picklist


class FreeCheck(BaseModel):
    """What the free check shows: the overall risk and where the concerns are. The rest is the paid report."""
    mark: str
    mark_kind: str
    overall_risk: Risk
    concerns: Concerns
    report_covers: list[str]
    own_marks: list[str] = []
    register_warning: str | None = None
    price_cents: int
    currency: str
    payments_enabled: bool


def _valid_email(value: str) -> str:
    value = value.strip()
    if len(value) > 254 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
        raise ValueError("Please enter a valid email address.")
    return value


class OrderRequest(BaseModel):
    email: str
    _email = field_validator("email")(_valid_email)
    terms: bool = False
    application: Application
    industry: str = Field("", max_length=300)
    logo: str | None = Field(None, max_length=8_000_000)  # data: URL of the customer's logo


class OrderResponse(BaseModel):
    order_id: str
    url: str                  # Stripe Checkout, or the report page when payments are bypassed for testing


class LinksRequest(BaseModel):
    email: str
    _email = field_validator("email")(_valid_email)


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


LOGO_TYPES = {b"\x89PNG\r\n\x1a\n": "image/png", b"\xff\xd8\xff": "image/jpeg"}
MAX_LOGO_BYTES = 5 * 1024 * 1024
_hits: dict[tuple[str, str], list[float]] = {}


def _read_logo(data_url: str | None) -> tuple[bytes | None, str | None]:
    """The customer's logo from a data: URL: PNG, JPEG or SVG, at most 5 MB."""
    if not data_url:
        return None, None
    try:
        header, encoded = data_url.split(",", 1)
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, base64.binascii.Error):
        raise HTTPException(422, "The logo couldn't be read. Please upload a PNG, JPG or SVG file.")
    if len(raw) > MAX_LOGO_BYTES:
        raise HTTPException(422, "The logo is larger than 5 MB.")
    for magic, kind in LOGO_TYPES.items():
        if raw.startswith(magic):
            return raw, kind
    head = raw[:2000].decode("utf-8", "ignore").lower()
    if "<svg" in head and "<script" not in raw.decode("utf-8", "ignore").lower():
        return raw, "image/svg+xml"
    raise HTTPException(422, "Please upload the logo as a PNG, JPG or SVG file.")


def _rate_limit(request: Request, action: str, per_hour: int) -> None:
    """A simple per-visitor limit, so the free check and orders can't be run in bulk."""
    import time
    ip = (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "?")).split(",")[0]
    now = time.time()
    recent = [t for t in _hits.get((ip, action), []) if now - t < 3600]
    if len(recent) >= per_hour:
        raise HTTPException(429, "Too many requests. Please try again later.")
    _hits[(ip, action)] = recent + [now]


def _secret() -> bytes:
    """The server secret for report links: TM_SECRET, or a random one kept in data/secret.key."""
    if os.environ.get("TM_SECRET"):
        return os.environ["TM_SECRET"].encode()
    path = ROOT / "data" / "secret.key"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(secrets.token_hex(32), encoding="utf-8")
    return path.read_text(encoding="utf-8").strip().encode()


TEST_REGISTER_WARNING = (
    "These results come from IP Australia's TEST environment, a copy of the register that is not kept up to date. "
    "Statuses can be wrong (a mark shown as awaiting examination may be registered, an expired one may have been "
    "removed) and recent marks are missing. Click a mark number to see its live record. Use Production access for "
    "real checks.")


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
               ai_checks: bool | None = None, store: Store | None = None, payments: Payments | None = None,
               mailer: Mailer | None = None, pdf=None, review: bool | None = None,
               full_check_results: bool | None = None) -> FastAPI:
    """ai_checks: run Claude's section 41 check with every check (default: when an API key is set).
    full_check_results: /api/check returns everything (local testing) instead of the free summary
    (default: TM_FREE_FULL=1)."""
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
    full_results = full_check_results if full_check_results is not None else os.environ.get("TM_FREE_FULL") == "1"
    store = store or Store(Path(os.environ.get("TM_DB", ROOT / "data" / "orders.sqlite")), secret=_secret())
    payments = payments if payments is not None else Payments.from_env()
    mailer = mailer or Mailer.from_env()
    public_url = os.environ.get("TM_PUBLIC_URL", "http://127.0.0.1:8000").rstrip("/")
    bypass_payment = os.environ.get("TM_DEV_FREE_REPORTS") == "1"  # local testing only: reports without paying
    price = payments.amount if payments else int(os.environ.get("TM_REPORT_PRICE_CENTS", "29900"))

    def report_link(order_id: str) -> str:
        return f"{public_url}/report/{order_id}?t={store.token_for(order_id)}"

    worker = ReportWorker(store, lambda app_, oid, logo, industry: make_report(app_, oid, logo, industry),
                          Path(os.environ.get("TM_REPORTS_DIR", ROOT / "data" / "reports")), mailer, report_link,
                          pdf=pdf, review=review)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if auto_refresh:
            autorefresh.start()  # keeps the picklist and Manual current; see autorefresh.py
        worker.resume()  # reports paid for before a restart
        yield

    app = FastAPI(title="Trademark Advisor", description="Brand filing check for Australian trade mark applicants. Not legal advice.",
                  lifespan=lifespan)

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC / "index.html")

    @app.get("/terms", include_in_schema=False)
    def terms() -> FileResponse:
        return FileResponse(STATIC / "terms.html")

    @app.get("/api/disclaimers")
    def disclaimers() -> list[str]:
        return DISCLAIMERS

    @app.post("/api/check", response_model=None)
    def run_check(request: CheckRequest) -> Report | FreeCheck:
        if not request.consent:
            raise HTTPException(422, "Please confirm you understand this is not legal advice before running a check.")
        application = Application(mark=request.mark, classes=request.classes, mark_kind=request.mark_kind,
                                  applicant=request.applicant)
        report = full_check(application)
        return report if full_results else free_summary(report)

    def full_check(application: Application) -> Report:
        try:
            report = check(application, register, pl())
        except httpx.HTTPStatusError as e:
            log.warning("Register search failed: %s %s", e, e.response.text[:500])
            raise HTTPException(502, f"IP Australia's register search returned an error ({e.response.status_code}). "
                                     "Please try again; if it keeps happening, check your IP Australia API access.")
        except httpx.HTTPError as e:
            log.warning("Register search failed: %s", e)
            raise HTTPException(502, "Couldn't reach IP Australia's register search. Please try again.")
        if "://test." in str(getattr(register, "base_url", "")):
            report = report.model_copy(update={"register_warning": TEST_REGISTER_WARNING})
        if not (ai_checks if ai_checks is not None else Explainer.configured()):
            return report.model_copy(update={"ai_distinctiveness_unavailable": "Not set up: add an Anthropic API key "
                                                                               "to check what the mark means as a whole."})
        try:
            ai = explainer.assess_distinctiveness(application.mark, application.mark_kind, application.classes)
        except ExplanationUnavailable as e:
            log.warning("AI distinctiveness check failed: %s", e, exc_info=e.__cause__)
            return report.model_copy(update={"ai_distinctiveness_unavailable": str(e)})
        return with_ai_distinctiveness(report, ai)

    def free_summary(report: Report) -> FreeCheck:
        ai = report.ai_distinctiveness
        distinct = (ai.likelihood if ai and ai.likelihood != "unlikely" else "none" if ai else
                    "likely" if report.wholly_descriptive else "possible" if report.distinctiveness else "none")
        similar = sum(1 for c in report.conflicts if c.live and c.risk != Risk.LOW)
        wording = sum(1 for p in report.picklist if not p.on_picklist)
        covers = ["Your recommended route: word mark, composite mark, logo mark, a different name or narrower goods, "
                  "and why",
                  "What your mark means as a whole for your goods and services, and your options" if distinct != "none"
                  else "Confirmation that your mark is distinctive, and what it protects",
                  f"The {similar} similar mark{'s' if similar != 1 else ''} that need attention: why each matters and "
                  "what to do" if similar else "Every similar mark we screened, and why none needs action",
                  "Your goods and services wording, ready to paste, with what to drop or narrow",
                  "Step-by-step filing through TM Headstart, with fees for your classes",
                  "A dated PDF to keep"]
        return FreeCheck(mark=report.mark, mark_kind=report.mark_kind, overall_risk=report.overall_risk,
                         concerns=Concerns(distinctiveness=distinct, similar_marks=similar, wording=wording),
                         report_covers=covers, own_marks=report.own_marks, register_warning=report.register_warning,
                         price_cents=price, currency="aud", payments_enabled=payments is not None or bypass_payment)

    def make_report(application: Application, order_id: str, logo: str | None, industry: str) -> ReportDoc:
        when = local_now()
        current = pl()
        live = "TEST copy of the register" if "://test." in str(getattr(register, "base_url", "")) else "register"
        sources = [f"Australian Trade Mark Search API (IP Australia), {live}, searched {nice_time(when)}.",
                   "IP Australia goods and services picklist"
                   + (f", updated {current.updated}." if current.updated else ".")]
        if manual_files and mi() is not None:
            sources.append(f"IP Australia Trade Marks Manual of Practice and Procedure, downloaded {manual_files.updated()}.")
        report = full_check(application)
        return build_report(application, report, classes=classes, reference=order_id, created=nice_date(when),
                            register_searched=nice_time(when), sources=sources,
                            explainer=explainer if (ai_checks if ai_checks is not None else Explainer.configured()) else None,
                            manual=mi(), logo_image=logo, industry=industry)

    # paid report ----------------------------------------------------------------------------------------------------
    @app.post("/api/orders")
    def create_order(request: OrderRequest, http_request: Request) -> OrderResponse:
        if not request.terms:
            raise HTTPException(422, "Please accept the terms and refund policy to continue.")
        if payments is None and not bypass_payment:
            raise HTTPException(503, "Payments aren't set up yet.")
        _rate_limit(http_request, "order", 10)
        logo, logo_type = _read_logo(request.logo)
        application = request.application.model_dump(mode="json")
        order, token = store.create_order(request.email, application, price, "aud", industry=request.industry,
                                          logo=logo, logo_type=logo_type)
        if payments is None:  # TM_DEV_FREE_REPORTS=1: straight to the report, no payment
            store.mark_paid(order.id, None)
            worker.submit(order.id)
            return OrderResponse(order_id=order.id, url=report_link(order.id))
        try:
            session_id, url = payments.checkout_url(order.id, token, order.email, request.application.mark)
        except Exception as e:
            log.exception("Stripe Checkout failed for %s", order.id)
            raise HTTPException(502, "Couldn't start the payment. Please try again.") from e
        store.set_session(order.id, session_id)
        return OrderResponse(order_id=order.id, url=url)

    @app.post("/api/stripe/webhook", include_in_schema=False)
    async def stripe_webhook(request: Request) -> dict:
        if payments is None:
            raise HTTPException(404)
        payload = await request.body()
        try:
            order_id = payments.handle_webhook(payload, request.headers.get("stripe-signature"), store)
        except Exception as e:  # bad signature or payload: tell Stripe it was rejected
            log.warning("Rejected Stripe webhook: %s", e)
            raise HTTPException(400, "Invalid webhook")
        if order_id:
            worker.submit(order_id)
        return {"received": True}

    @app.get("/report/sample", response_class=HTMLResponse, include_in_schema=False)
    def sample_page() -> str:
        return render_html(sample_report())

    @app.get("/report/{order_id}", response_class=HTMLResponse, include_in_schema=False)
    def report_page(order_id: str, t: str = "") -> str:
        order = _authorised(order_id, t)
        if order.status in ("ready", "refunded") and (saved := store.report(order_id)):
            return render_html(ReportDoc.model_validate(saved[0]), download_url=f"/report/{order_id}/pdf?t={t}")
        return status_page(order_id, order.status, order.email)

    @app.get("/report/{order_id}/pdf", include_in_schema=False)
    def report_pdf(order_id: str, t: str = "") -> FileResponse:
        order = _authorised(order_id, t)
        saved = store.report(order_id) if order.status in ("ready", "refunded") else None
        if not saved or not saved[1] or not Path(saved[1]).exists():
            raise HTTPException(404, "The PDF isn't ready yet.")
        return FileResponse(saved[1], media_type="application/pdf",
                            filename=f"Trademark-Advisor-report-{order_id}.pdf")

    @app.post("/api/orders/links")
    def resend_links(request: LinksRequest, http_request: Request) -> dict:
        """Lost your link: email the links for every report on this address (same answer either way)."""
        _rate_limit(http_request, "links", 5)
        orders = [o for o in store.orders_for_email(request.email) if o.status != "pending"]
        if orders:
            mailer.report_ready(orders[0].email, orders[0].application.get("mark", ""),
                                [(f"Report {o.id}: {o.application.get('mark', '')}", report_link(o.id)) for o in orders])
        return {"message": "If there are reports for that email address, we've sent the links."}

    def _authorised(order_id: str, token: str):
        if not store.check_token(order_id, token):
            raise HTTPException(404, "Report not found. Check the link in your email.")
        return store.get(order_id)

    @app.post("/api/explain")
    def run_explain(request: CheckRequest) -> ExplainResponse:
        if not full_results:
            raise HTTPException(404, "Explanations are part of the paid report.")
        if not request.consent:
            raise HTTPException(422, "Please confirm you understand this is not legal advice before running a check.")
        report = full_check(Application(mark=request.mark, classes=request.classes, mark_kind=request.mark_kind,
                                        applicant=request.applicant))
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
