"""Turn a release-notes Word document (.docx) into a release.

A .docx is a zip of XML parts, so this uses only the standard library.

Required: a version number and at least one change. Everything else is optional.

    iCRM Release 11.1                      <- title/heading with a version number      (required)
    Status: Coming soon                    <- or "Released"; default Released
    Planned release: October 2026          <- for upcoming releases
    Released on September 28, 2026         <- any line with a date; default today
    Short summary paragraph...             <- first plain paragraph = release summary

    Highlights                             <- short list shown at the top
    What's New / New Features              <- category headings                        (one change required)
      • CS-1234: Title - optional detail   <- one change per paragraph / bullet
        ◦ nested bullet                    <- appended to the previous change's description
        [picture]                          <- a picture under a change = that change's screenshot
    Improvements / Changed
    Bug Fixes / Fixed
    Security
    Jira list                              <- a table with Jira / Category / Title / Description columns
    Known issues                           <- plain list
    Upgrade notes                          <- plain list
    Screenshots                            <- pictures here go in the release's gallery

    About this template / Instructions     <- everything under this heading is ignored

A line can also carry its own label ("Fixed: ...", "[New] ..."), a bold lead
("**Title** description"), or sit in a table. Lines outside any category heading are
classified by keyword. A picture's caption is the text in the same paragraph, or the
next paragraph when it starts with "Screenshot:", "Figure:" or "Caption:".
"""
import posixpath
import re
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime
from io import BytesIO
from xml.etree import ElementTree

from . import image_store
from .release_categorizer import categorize

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
V = "{urn:schemas-microsoft-com:vml}"
PKG_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"

JIRA_RE = re.compile(r"\b([A-Z][A-Z0-9]{1,9}-\d+)\b")
VERSION_RE = re.compile(r"(?:\bversion|\brelease|\bv)\s*[:\-]?\s*(\d+(?:\.\d+){1,3})\b", re.I)
BARE_VERSION_RE = re.compile(r"^\s*v?(\d+\.\d+(?:\.\d+){0,2})\s*$", re.I)
STATUS_RE = re.compile(r"^\s*status\s*[:\-–]\s*(.+)$", re.I)
PLANNED_RE = re.compile(r"^\s*(?:planned(?:\s+release)?|expected(?:\s+release)?|target(?:\s+release)?|release\s+window|coming)\s*(?:in|on|date)?\s*[:\-–]?\s*(.+)$", re.I)
CAPTION_RE = re.compile(r"^\s*(?:screenshot|figure|fig\.|caption|image)\s*\d*\s*[:\-–]\s*(.+)$", re.I)
UPCOMING_WORDS = re.compile(r"coming soon|upcoming|planned|not yet released|next month|in progress|scheduled", re.I)

CATEGORY_HEADINGS = [
    ("SECURITY", r"security"),
    ("BUG_FIX", r"bug|fix|fixed|defect|issue"),
    ("IMPROVEMENT", r"improve|enhance|change|changed|update|optimi[sz]"),
    ("NEW_FEATURE", r"what'?s\s*new|what’s\s*new|new|feature|added|addition"),
]
# Checked before the categories ("Known issues" must not become Bug fixes).
SECTION_HEADINGS = [
    ("SKIP", r"about this (template|document|sample)|instructions?|how to use|notes? for (authors?|editors?)|template guide"),
    ("KNOWN_ISSUES", r"known (issues?|problems?|limitations?)|limitations"),
    ("UPGRADE_NOTES", r"upgrade|deployment|before you (upgrade|install)|installation notes|migration notes|action required"),
    ("HIGHLIGHTS", r"highlights?|at a glance|key changes|summary of changes"),
    ("SCREENSHOTS", r"screenshots?|images?|gallery|preview"),
    ("JIRA_LIST", r"jira (list|tickets?|issues?)|ticket list|tickets included"),
]
LABEL_RE = re.compile(
    r"^\s*[\[(]?(new|added|feature|fixed|fix|bug ?fix|bug|improved|improvement|changed|enhancement|security)[\])]?\s*[:\-–]\s*|"
    r"^\s*[\[(](new|added|feature|fixed|fix|bug ?fix|bug|improved|improvement|changed|enhancement|security)[\])]\s*",
    re.I,
)
LABEL_TO_CATEGORY = {
    "new": "NEW_FEATURE", "added": "NEW_FEATURE", "feature": "NEW_FEATURE",
    "fixed": "BUG_FIX", "fix": "BUG_FIX", "bug fix": "BUG_FIX", "bugfix": "BUG_FIX", "bug": "BUG_FIX",
    "improved": "IMPROVEMENT", "improvement": "IMPROVEMENT", "changed": "IMPROVEMENT", "enhancement": "IMPROVEMENT",
    "security": "SECURITY",
}
MONTHS = "jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec"
DATE_FORMATS = ["%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%m/%d/%Y"]
DATE_RE = re.compile(
    r"(\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]\d{4}|"
    rf"(?:{MONTHS})[a-z]*\.?\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s+\d{{4}}|"
    rf"\d{{1,2}}(?:st|nd|rd|th)?\s+(?:{MONTHS})[a-z]*\.?,?\s+\d{{4}})",
    re.I,
)
MONTH_YEAR_RE = re.compile(rf"\b((?:{MONTHS})[a-z]*)\.?\s+(\d{{4}})\b", re.I)
MAX_BYTES = 10 * 1024 * 1024
MAX_IMAGES = 40


class DocxParseError(ValueError):
    pass


@dataclass
class Paragraph:
    text: str
    style: str = ""
    list_level: int | None = None
    bold_lead: str = ""
    all_bold: bool = False
    image_ids: list[str] = field(default_factory=list)


@dataclass
class ParsedDoc:
    version: str | None = None
    release_date: date | None = None
    status: str = "RELEASED"
    planned_label: str | None = None
    summary: str | None = None
    highlights: list[str] = field(default_factory=list)
    known_issues: list[str] = field(default_factory=list)
    upgrade_notes: list[str] = field(default_factory=list)
    images: list[dict] = field(default_factory=list)
    items: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ---- XML reading ----

def _paragraph(p) -> Paragraph:
    style_el = p.find(f"{W}pPr/{W}pStyle")
    style = style_el.get(f"{W}val", "") if style_el is not None else ""
    num = p.find(f"{W}pPr/{W}numPr")
    level = None
    if num is not None:
        ilvl = num.find(f"{W}ilvl")
        level = int(ilvl.get(f"{W}val", "0")) if ilvl is not None else 0
    elif style.lower().startswith("list"):
        level = 1 if style.lower().rstrip().endswith("2") else 0

    parts, bold_lead, lead_open, bold_chars, total_chars = [], [], True, 0, 0
    for run in p.iter(f"{W}r"):
        text = "".join(
            (t.text or "") if t.tag == f"{W}t" else ("\t" if t.tag == f"{W}tab" else " " if t.tag in (f"{W}br", f"{W}cr") else "")
            for t in run
        )
        if not text:
            continue
        b = run.find(f"{W}rPr/{W}b")
        bold = b is not None and b.get(f"{W}val", "true") not in ("0", "false")
        parts.append(text)
        total_chars += len(text.strip())
        if bold:
            bold_chars += len(text.strip())
        if lead_open and bold:
            bold_lead.append(text)
        elif text.strip():
            lead_open = False

    image_ids = [blip.get(f"{R}embed") for blip in p.iter(f"{A}blip") if blip.get(f"{R}embed")]
    image_ids += [img.get(f"{R}id") for img in p.iter(f"{V}imagedata") if img.get(f"{R}id")]
    text = re.sub(r"\s+", " ", "".join(parts)).strip()
    return Paragraph(
        text=text,
        style=style,
        list_level=level,
        bold_lead=re.sub(r"\s+", " ", "".join(bold_lead)).strip(),
        all_bold=total_chars > 0 and bold_chars == total_chars,
        image_ids=image_ids,
    )


class _Package:
    def __init__(self, data: bytes):
        if len(data) > MAX_BYTES:
            raise DocxParseError("The file is larger than 10 MB.")
        try:
            self.zip = zipfile.ZipFile(BytesIO(data))
            self.document = self.zip.read("word/document.xml")
        except (zipfile.BadZipFile, KeyError):
            raise DocxParseError("This is not a valid Word (.docx) document. Save older .doc files as .docx first.")
        self.targets: dict[str, str] = {}
        try:
            rels = ElementTree.fromstring(self.zip.read("word/_rels/document.xml.rels"))
            for rel in rels.iter(f"{PKG_REL}Relationship"):
                if rel.get("TargetMode") != "External":
                    self.targets[rel.get("Id")] = posixpath.normpath(posixpath.join("word", rel.get("Target", "")))
        except KeyError:
            pass

    def image(self, rel_id: str) -> bytes | None:
        target = self.targets.get(rel_id)
        if not target:
            return None
        try:
            info = self.zip.getinfo(target)
        except KeyError:
            return None
        if info.file_size > image_store.MAX_IMAGE_BYTES:
            return None
        return self.zip.read(info)

    def blocks(self):
        """Yield ("p", Paragraph) and ("table", rows) in document order."""
        body = ElementTree.fromstring(self.document).find(f"{W}body")
        if body is None:
            raise DocxParseError("The document has no content.")
        for child in body:
            if child.tag == f"{W}p":
                yield "p", _paragraph(child)
            elif child.tag == f"{W}tbl":
                rows = []
                for tr in child.iter(f"{W}tr"):
                    cells = [" ".join(_paragraph(p).text for p in tc.iter(f"{W}p")).strip() for tc in tr.iter(f"{W}tc")]
                    rows.append(cells)
                yield "table", rows


# ---- Interpretation ----

def _heading_kind(text: str) -> tuple[str, str] | None:
    """("section", name) or ("category", CATEGORY) for a heading's text."""
    lowered = text.lower().strip(" :")
    if len(lowered) > 50:
        return None
    for name, pattern in SECTION_HEADINGS:
        if re.search(pattern, lowered):
            return "section", name
    for category, pattern in CATEGORY_HEADINGS:
        if re.search(pattern, lowered):
            return "category", category
    return None


def _category_of(text: str) -> str | None:
    kind = _heading_kind(text)
    return kind[1] if kind and kind[0] == "category" else None


def _is_heading(p: Paragraph) -> bool:
    style = p.style.lower()
    if style.startswith(("heading", "title", "subtitle")):
        return True
    return p.list_level is None and p.all_bold and len(p.text) <= 60 and not JIRA_RE.search(p.text)


def _parse_date(text: str) -> date | None:
    match = DATE_RE.search(text)
    if not match:
        return None
    raw = re.sub(r"(\d)(st|nd|rd|th)", r"\1", match.group(1)).replace(".", "").replace(" ,", ",")
    raw = re.sub(r"(\w{3})\w*\s+(\d{1,2}),?\s+(\d{4})", r"\1 \2, \3", raw) if raw[0].isalpha() else raw
    for fmt in DATE_FORMATS + ["%b %d, %Y"]:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _parse_month_year(text: str) -> tuple[date, str] | None:
    match = MONTH_YEAR_RE.search(text)
    if not match:
        return None
    try:
        first = datetime.strptime(f"{match.group(1)[:3]} 1 {match.group(2)}", "%b %d %Y").date()
    except ValueError:
        return None
    return first, first.strftime("%B %Y")


def _split_item(text: str, bold_lead: str) -> tuple[str | None, str, str | None, str | None]:
    """Return (label category, title, description, jira id) for one line."""
    label_category = None
    label = LABEL_RE.match(text)
    if label:
        word = (label.group(1) or label.group(2)).lower()
        label_category = LABEL_TO_CATEGORY.get(word) or LABEL_TO_CATEGORY.get(word.replace(" ", ""))
        text = text[label.end():]
        if bold_lead and LABEL_RE.match(bold_lead):
            bold_lead = ""

    jira_match = JIRA_RE.search(text)
    jira_id = jira_match.group(1) if jira_match and jira_match.start() <= 12 else None
    if jira_id:
        text = (text[: jira_match.start()] + text[jira_match.end():]).strip()
        text = re.sub(r"^[\s:\-–|#\[\]()]+", "", text)
        bold_lead = bold_lead.replace(jira_id, "").strip(" :-–|#[]()")

    text = text.strip()
    description = None
    if bold_lead and text.startswith(bold_lead) and len(text) > len(bold_lead) + 2:
        title, description = bold_lead, text[len(bold_lead):].strip(" :-–")
    elif re.search(r" [—–] ", text) and len(re.split(r" [—–] ", text, maxsplit=1)[0].split()) >= 3:
        # "Faster grid – loads 3x quicker" splits; "Citi – Custom Field API" (a client prefix) does not.
        title, description = re.split(r" [—–] ", text, maxsplit=1)
    else:
        title = text
    return label_category, title.strip(" :-–"), (description or None), jira_id


def _table_items(rows: list[list[str]], current: str | None) -> list[dict] | None:
    if len(rows) < 2:
        return None
    header = [c.lower() for c in rows[0]]

    def col(*names):
        for i, h in enumerate(header):
            if any(n in h for n in names):
                return i
        return None

    jira_i, cat_i = col("jira", "ticket", "key", "id"), col("category", "type", "section")
    title_i, desc_i = col("title", "summary", "subject", "change", "feature"), col("description", "detail", "notes")
    if title_i is None and desc_i is None:
        return None
    items = []
    for cells in rows[1:]:
        get = lambda i: cells[i].strip() if i is not None and i < len(cells) else ""  # noqa: E731
        title = get(title_i) or get(desc_i)
        if not title:
            continue
        description = get(desc_i) if title_i is not None and get(desc_i) != title else ""
        category = _category_of(get(cat_i)) if get(cat_i) else None
        jira = JIRA_RE.search(get(jira_i)) if get(jira_i) else JIRA_RE.search(title)
        items.append({
            "category": category or current or categorize(f"{title} {description}"),
            "title": title[:500],
            "description": description[:1000] or None,
            "jiraId": jira.group(1) if jira else None,
            "images": [],
        })
    return items


def parse_docx(data: bytes) -> ParsedDoc:
    package = _Package(data)
    doc = ParsedDoc()
    current: str | None = None      # category for change lines
    section: str | None = None      # SKIP / HIGHLIGHTS / KNOWN_ISSUES / UPGRADE_NOTES / SCREENSHOTS / JIRA_LIST
    seen_section = False
    image_count = 0
    last_image: dict | None = None  # for a caption in the following paragraph
    status_text = ""

    def add_images(p: Paragraph, caption: str | None) -> None:
        nonlocal image_count, last_image
        for rel_id in p.image_ids:
            if image_count >= MAX_IMAGES:
                doc.warnings.append(f"Only the first {MAX_IMAGES} pictures were kept.")
                return
            raw = package.image(rel_id)
            try:
                data_url = image_store.to_data_url(raw) if raw else None
            except image_store.ImageError:
                data_url = None
            if not data_url:
                doc.warnings.append("Skipped a picture that isn't PNG, JPEG, GIF or WebP (or is over 5 MB).")
                continue
            image = {"dataUrl": data_url, "caption": (caption or None) and caption[:255]}
            attach_to_item = section is None and seen_section and doc.items
            (doc.items[-1]["images"] if attach_to_item else doc.images).append(image)
            image_count += 1
            last_image = image

    for kind, block in package.blocks():
        if kind == "table":
            last_image = None
            if section == "SKIP":
                continue
            items = _table_items(block, current)
            if items is None:
                doc.warnings.append("Skipped a table without Title or Description columns.")
            else:
                doc.items.extend(items)
            continue

        p: Paragraph = block
        if not p.text and not p.image_ids:
            continue

        # Headings switch the current section / category.
        if p.text and not p.image_ids and _is_heading(p):
            heading = _heading_kind(p.text)
            is_title = not doc.version and (VERSION_RE.search(p.text) or BARE_VERSION_RE.match(p.text))
            if is_title:
                match = VERSION_RE.search(p.text) or BARE_VERSION_RE.match(p.text)
                doc.version = match.group(1)
                if section == "SKIP":
                    section = None  # the title ends an instructions section placed above it
                if UPCOMING_WORDS.search(p.text):
                    status_text = status_text or p.text
                doc.release_date = doc.release_date or _parse_date(p.text)
                continue
            if heading:
                if heading[0] == "section":
                    section = heading[1]
                    if section == "JIRA_LIST":
                        current, section = None, None  # table/lines here are changes, typed by their own column
                    if section != "SKIP":
                        seen_section = True  # instructions can sit above the title without hiding it
                else:
                    section, current, seen_section = None, heading[1], True
                last_image = None
                continue
            if seen_section:
                section, current = None, None  # a component heading ("Ticket Portal"): classify by keyword
                last_image = None
                continue

        if section == "SKIP":
            continue

        # Picture caption written in the paragraph after the picture.
        caption_match = CAPTION_RE.match(p.text) if p.text else None
        if caption_match and last_image is not None and not p.image_ids:
            last_image["caption"] = caption_match.group(1).strip()[:255]
            last_image = None
            continue
        last_image = None

        if p.image_ids:
            add_images(p, CAPTION_RE.match(p.text).group(1).strip() if caption_match else p.text or None)
            continue

        # Release details before the first section.
        if not seen_section:
            if not doc.version:
                match = VERSION_RE.search(p.text)
                if match and len(p.text) < 80:
                    doc.version = match.group(1)
                    doc.release_date = doc.release_date or _parse_date(p.text)
                    if UPCOMING_WORDS.search(p.text):
                        status_text = status_text or p.text
                    continue
            status = STATUS_RE.match(p.text)
            if status:
                status_text = status.group(1)
                continue
            planned = PLANNED_RE.match(p.text) if len(p.text) < 80 else None
            if planned:
                target = planned.group(1)
                exact = _parse_date(target)
                month = _parse_month_year(target)
                if exact:
                    doc.release_date, doc.planned_label = exact, exact.strftime("%B %d, %Y").replace(" 0", " ")
                elif month:
                    doc.release_date, doc.planned_label = month
                else:
                    doc.planned_label = target.strip()[:100]
                status_text = status_text or "planned"
                continue
            if not doc.release_date and len(p.text) < 80:
                parsed = _parse_date(p.text)
                if parsed:
                    doc.release_date = parsed
                    continue

        # Plain-list sections.
        if section in ("HIGHLIGHTS", "KNOWN_ISSUES", "UPGRADE_NOTES"):
            target = {"HIGHLIGHTS": doc.highlights, "KNOWN_ISSUES": doc.known_issues, "UPGRADE_NOTES": doc.upgrade_notes}[section]
            if p.list_level and p.list_level > 0 and target:
                target[-1] = f"{target[-1]} {p.text}"[:1000]
            else:
                target.append(p.text[:1000])
            continue
        if section == "SCREENSHOTS":
            continue  # text in the gallery section without a picture is ignored

        # Nested bullets add detail to the change above them.
        if p.list_level and p.list_level > 0 and doc.items:
            last = doc.items[-1]
            last["description"] = (f"{last['description']} {p.text}" if last["description"] else p.text)[:1000]
            continue

        if not seen_section and p.list_level is None and not doc.summary and not JIRA_RE.search(p.text[:15]):
            doc.summary = p.text[:1000]
            continue

        label_category, title, description, jira_id = _split_item(p.text, p.bold_lead)
        if not title:
            continue
        doc.items.append({
            "category": label_category or current or categorize(f"{title} {description or ''}"),
            "title": title[:500],
            "description": description[:1000] if description else None,
            "jiraId": jira_id,
            "images": [],
        })

    if status_text and UPCOMING_WORDS.search(status_text):
        doc.status = "UPCOMING"
    if not doc.items:
        doc.warnings.append(
            "No changes were found, and at least one is required. Put each change on its own line or bullet "
            "under a heading such as 'What's New' or 'Bug Fixes'."
        )
    if not doc.version:
        doc.warnings.append("No version number was found, and it is required. Enter it below.")
    if not doc.release_date:
        doc.warnings.append("No date was found; today's date is used unless you change it below.")
    return doc
