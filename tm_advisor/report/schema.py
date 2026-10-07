"""What a paid report contains (design: docs/paid-report-design.md §4).

The report is built once, when the order is paid, and frozen: everything the customer sees comes from this
object, dated with the time the register was searched.
"""

from typing import Literal

from pydantic import BaseModel

from ..models import MarkKind, Risk, Route


class Citation(BaseModel):
    title: str
    heading: str = ""
    url: str
    published: str = ""


class DistinctivenessSection(BaseModel):
    likelihood: Literal["likely", "possible", "unlikely"]
    meaning: str = ""
    reasoning: str
    affected_terms: list[str] = []
    word_flags: list[str] = []          # individual words that describe or praise, with why
    options: list[str] = []
    citations: list[Citation] = []


class SimilarMark(BaseModel):
    number: str
    words: str
    logo: bool = False
    image: str | None = None
    status: str
    owner: str | None = None
    classes: list[int]
    live: bool = True
    risk: Risk
    why_similar: list[str]
    goods_overlap: str                 # plain-English summary of the overlapping goods/services
    what_to_do: str


class SpecTerm(BaseModel):
    text: str
    on_picklist: bool = True
    note: str = ""


class SpecClass(BaseModel):
    class_number: int
    title: str
    terms: list[SpecTerm]
    removed: list[SpecTerm] = []       # terms we suggest leaving out or narrowing, with why in `note`


class Filing(BaseModel):
    classes: int
    headstart_part1: int               # A$, total for all classes
    headstart_part2: int
    standard: int
    all_picklist: bool
    steps: list[str]
    adverse_headstart: list[str]       # what to do if the Headstart assessment is adverse


class ReportDoc(BaseModel):
    brand: str = "Trademark Advisor"
    seller: str = "Success Meter Pty Ltd"
    reference: str
    prepared_for: str = ""
    created: str                       # date the report was produced, e.g. "7 October 2026"
    register_searched: str             # date and time of the register search
    sources: list[str]                 # data sources with their dates
    sample: bool = False

    mark: str
    mark_kind: MarkKind
    logo_image: str | None = None      # data: URI of the customer's uploaded logo
    classes: list[int]

    overall_risk: Risk
    summary: str
    top_actions: list[str]
    route: Route
    route_detail: list[str] = []       # extra paragraphs explaining the route for this mark

    distinctiveness: DistinctivenessSection
    similar_marks: list[SimilarMark]
    marks_reviewed: int                # how many register results were screened
    specification: list[SpecClass]
    specification_notes: list[str] = []
    design_guidance: list[str] = []    # for composite and logo marks
    filing: Filing
    attorney_reasons: list[str] = []
    limitations: list[str]
