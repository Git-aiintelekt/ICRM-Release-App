"""One release's notes as a standalone HTML file, and the email that carries it as an attachment.

Built from release_json (the same data the site shows), so the attachment matches the release page. Screenshots
are left out: they would make the email large, and the page link in the email shows them.
"""
import re
from datetime import date
from html import escape

from django.conf import settings
from django.core.mail import EmailMultiAlternatives

from integrations import credentials

from ..models import CATEGORY_ORDER, Category

HEADINGS = {"NEW_FEATURE": "What's new", "IMPROVEMENT": "Improvements", "BUG_FIX": "Bug fixes", "SECURITY": "Security"}
LABELS = dict(Category.choices)


def file_name(release: dict) -> str:
    return "iCRM-release-notes-" + re.sub(r"[^0-9A-Za-z._-]", "_", release["version"]) + ".html"


def page_url(release: dict) -> str:
    return f"{settings.APP_BASE_URL}/#icrm-v" + re.sub(r"[^0-9A-Za-z]", "", release["version"])


def _when(release: dict) -> str:
    if release["status"] == "UPCOMING":
        return "Coming " + (release.get("plannedLabel") or "soon")
    d = date.fromisoformat(release["releaseDate"])
    return f"Released on {d:%B} {d.day}, {d.year}"


def _grouped(release: dict):
    for category in CATEGORY_ORDER:
        items = [i for i in release["items"] if i["category"] == category]
        if items:
            yield category, items


def _jira_link(key: str) -> str:
    base = credentials.get("JIRA_BASE_URL")
    return f'<a href="{escape(base)}/browse/{escape(key)}">{escape(key)}</a>' if base else escape(key)


def _list_html(title: str, lines: list[str]) -> str:
    if not lines:
        return ""
    return f"<h2>{escape(title)}</h2><ul>" + "".join(f"<li>{escape(line)}</li>" for line in lines) + "</ul>"


def notes_html(release: dict) -> str:
    """The attachment: a complete page that opens in any browser, styled inline."""
    parts = [f"<h1>iCRM Release {escape(release['version'])}</h1>", f'<p class="when">{escape(_when(release))} · '
             f"{len(release['items'])} changes</p>"]
    if release.get("description"):
        parts.append(f"<p>{escape(release['description'])}</p>")
    parts.append(_list_html("Highlights", release["highlights"]))
    for category, items in _grouped(release):
        rows = []
        for item in items:
            key = f'<span class="key">{_jira_link(item["jiraId"])}</span> ' if item.get("jiraId") else ""
            desc = f'<div class="desc">{escape(item["description"])}</div>' if item.get("description") else ""
            rows.append(f"<li>{key}<strong>{escape(item['title'])}</strong>{desc}</li>")
        parts.append(f"<h2>{escape(HEADINGS[category])}</h2><ul>{''.join(rows)}</ul>")
    parts.append(_list_html("Known issues", release["knownIssues"]))
    parts.append(_list_html("Upgrade notes", release["upgradeNotes"]))
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>iCRM Release {escape(release['version'])}</title>
<style>
body {{ margin: 0 auto; max-width: 760px; padding: 32px 16px; font: 15px/1.55 "Segoe UI", Arial, sans-serif;
  color: #1f2328; background: #fff; }}
h1 {{ margin: 0 0 4px; font-size: 26px; }}
h2 {{ margin: 28px 0 8px; font-size: 18px; border-bottom: 1px solid #d8dee4; padding-bottom: 4px; }}
.when {{ margin: 0 0 16px; color: #59636e; }}
ul {{ padding-left: 20px; }}
li {{ margin: 6px 0; }}
.key {{ font-family: Consolas, monospace; font-size: 13px; }}
.desc {{ color: #59636e; }}
a {{ color: #0969da; }}
</style></head>
<body>{''.join(parts)}</body></html>
"""


def notes_text(release: dict) -> str:
    """Plain-text version, used as the email body."""
    lines = [f"iCRM Release {release['version']}", f"{_when(release)} · {len(release['items'])} changes", ""]
    if release.get("description"):
        lines += [release["description"], ""]

    def section(title, entries):
        if entries:
            lines.extend([title, *[f"  - {e}" for e in entries], ""])

    section("Highlights", release["highlights"])
    for category, items in _grouped(release):
        section(HEADINGS[category], [f"{i['jiraId'] + ': ' if i.get('jiraId') else ''}{i['title']}" for i in items])
    section("Known issues", release["knownIssues"])
    section("Upgrade notes", release["upgradeNotes"])
    return "\n".join(lines).rstrip() + "\n"


def build_email(release: dict, *, to: list[str], cc: list[str], message: str, sender_name: str,
                reply_to: str | None = None) -> EmailMultiAlternatives:
    intro = (message.strip() + "\n\n") if message.strip() else ""
    body = (f"{intro}{notes_text(release)}\nFull release notes with screenshots: {page_url(release)}\n"
            f"The notes are also attached as {file_name(release)}.\n\nSent by {sender_name} from Release Manager.\n")
    email = EmailMultiAlternatives(subject=f"iCRM Release {release['version']} - release notes", body=body,
                                   to=to, cc=cc, reply_to=[reply_to] if reply_to else None)
    email.attach(file_name(release), notes_html(release), "text/html")
    return email
