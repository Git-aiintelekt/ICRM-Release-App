"""Read release notes from a CSV file (one change per row) into the same shape as the Word upload.

Columns are matched by header name, in any order and case; only Title is required:

    Version | Release date | Status | Planned release | Category | Jira ID | Title | Description

The Import / Export page's "Release changes (CSV)" export uses these headers, so an exported file can be edited
and uploaded again. Release-level values (version, date, status) come from the first row that has them. A CSV has
no screenshots: they are added in the review before publishing, or on the Release Notes page afterwards.
"""
import csv
import io
import re

from .docx_parser import JIRA_RE, LABEL_TO_CATEGORY, MAX_BYTES, ParsedDoc, _parse_date, _parse_month_year
from .release_categorizer import categorize

MAX_ROWS = 1000

COLUMNS = {
    "version": ("version", "release", "release version"),
    "release_date": ("release date", "date", "released on", "expected date"),
    "status": ("status",),
    "planned": ("planned release", "planned", "planned for"),
    "category": ("category", "type", "section"),
    "jira_id": ("jira id", "jira", "jira key", "ticket", "issue"),
    "title": ("title", "change", "summary", "name"),
    "description": ("description", "details", "notes"),
}

CATEGORY_NAMES = {
    **LABEL_TO_CATEGORY,
    "new_feature": "NEW_FEATURE", "new feature": "NEW_FEATURE", "what's new": "NEW_FEATURE", "whats new": "NEW_FEATURE",
    "improvements": "IMPROVEMENT", "bug_fix": "BUG_FIX", "bug fixes": "BUG_FIX", "bugfixes": "BUG_FIX",
    "fixes": "BUG_FIX",
}
UPCOMING_WORDS = re.compile(r"upcoming|coming soon|planned|not yet released|scheduled", re.I)
LIMITS = {"title": 500, "description": 1000, "jira_id": 20}


class CsvParseError(ValueError):
    """A message safe to show the person who uploaded the file."""


def _decode(data: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1252"):  # Excel's "CSV UTF-8", then its plain "CSV" on Windows
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise CsvParseError("The CSV file's text encoding isn't supported. Save it as \"CSV UTF-8\" and try again.")


def _cell(value) -> str:
    text = (value or "").strip()
    # The export prefixes = + - @ with ' so spreadsheets don't run them as formulas; undo that.
    return text[1:] if re.match(r"^'[=+\-@]", text) else text


def _category(raw: str, text: str, row_number: int, warnings: list[str]) -> str:
    key = raw.strip().lower()
    if key in CATEGORY_NAMES:
        return CATEGORY_NAMES[key]
    if key.upper() in CATEGORY_NAMES.values():
        return key.upper()
    if key:
        warnings.append(f"Row {row_number}: category \"{raw}\" isn't New, Improved, Fixed or Security; it was guessed from the title.")
    return categorize(text)


def parse_csv(data: bytes) -> ParsedDoc:
    if len(data) > MAX_BYTES:
        raise CsvParseError("The CSV file is larger than 10 MB.")
    text = _decode(data)
    if not text.strip():
        raise CsvParseError("The CSV file is empty.")
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(io.StringIO(text), dialect)
    header = next(reader, [])
    names = [_cell(name).lower().replace("_", " ") for name in header]
    columns = {}
    for key, aliases in COLUMNS.items():
        for index, name in enumerate(names):
            if name in aliases and key not in columns:
                columns[key] = index
    if "title" not in columns:
        raise CsvParseError("The CSV file needs a header row with at least a Title column "
                            "(and optionally Version, Release date, Status, Category, Jira ID, Description).")

    doc = ParsedDoc()
    doc.summary = ""
    status_seen = False
    for row_number, row in enumerate(reader, start=2):
        get = lambda key: _cell(row[columns[key]]) if key in columns and columns[key] < len(row) else ""
        if not any(_cell(value) for value in row):
            continue
        if len(doc.items) >= MAX_ROWS:
            doc.warnings.append(f"Only the first {MAX_ROWS} changes were read.")
            break
        if doc.version is None and get("version"):
            doc.version = get("version").removeprefix("v").removeprefix("V").strip()
        if doc.release_date is None and get("release_date"):
            doc.release_date = _parse_date(get("release_date"))
        if not status_seen and get("status"):
            status_seen = True
            doc.status = "UPCOMING" if UPCOMING_WORDS.search(get("status")) else "RELEASED"
        if doc.planned_label is None and get("planned"):
            month_year = _parse_month_year(get("planned"))
            doc.planned_label = month_year[1] if month_year else get("planned")[:100]

        title, description, jira_id = get("title"), get("description") or None, get("jira_id") or None
        if not title:
            doc.warnings.append(f"Row {row_number} has no title and was skipped.")
            continue
        if jira_id is None:  # "CT-363: Custom Field API" in the title, as in the Word format
            match = JIRA_RE.match(title)
            if match:
                jira_id = match.group(1)
                title = title[match.end():].lstrip(" :-–|").strip() or title
        item = {"category": _category(get("category"), f"{title} {description or ''}", row_number, doc.warnings),
                "title": title, "description": description, "jira_id": jira_id, "images": [],
                "version": get("version").removeprefix("v").removeprefix("V").strip() or None}
        for key, limit in LIMITS.items():
            if item[key] and len(item[key]) > limit:
                item[key] = item[key][:limit]
                doc.warnings.append(f"Row {row_number}: {key.replace('_', ' ')} was cut to {limit} characters.")
        doc.items.append(item)

    other_versions = sorted({i["version"] for i in doc.items if i["version"] and i["version"] != doc.version})
    if other_versions:
        doc.warnings.append(f"Only version {doc.version} was read; rows for {', '.join(other_versions)} were left out. "
                            "Upload one version per file.")
        doc.items = [i for i in doc.items if i["version"] in (None, doc.version)]
    for item in doc.items:
        del item["version"]
    if not doc.items:
        doc.warnings.append("No changes were found in the CSV file.")
    if doc.version is None:
        doc.warnings.append("No version number was found: add a Version column or type it below.")
    return doc
