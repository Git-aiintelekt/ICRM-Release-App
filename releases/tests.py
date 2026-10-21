"""Release notes email and download (no database: the release JSON and the audit log are mocked)."""
import smtplib
import tempfile
from email import message_from_bytes
from pathlib import Path
from unittest import mock

from django.core import mail
from django.core.mail import EmailMessage
from django.test import SimpleTestCase, override_settings
from rest_framework.test import APIRequestFactory, force_authenticate

from config.mail import EmlFileBackend
from integrations.tests.fakes import FakeUser

from . import api
from .services import release_email

ADMIN = FakeUser(admin=True)
VIEWER = FakeUser(jira=True)

RELEASE = {
    "id": 5, "version": "11.1", "releaseDate": "2026-10-01", "description": "Faster <search> & exports",
    "isLatest": True, "status": "RELEASED", "plannedLabel": None,
    "highlights": ["Search is 2x faster"], "knownIssues": ["Export of >10k rows is slow"], "upgradeNotes": [],
    "images": [],
    "items": [
        {"id": 1, "category": "BUG_FIX", "title": "Fix login loop", "description": None, "jiraId": "CT-367", "images": []},
        {"id": 2, "category": "NEW_FEATURE", "title": "Bulk <edit>", "description": "Edit many rows", "jiraId": None, "images": []},
    ],
}


@override_settings(JIRA_BASE_URL="https://jira.test", APP_BASE_URL="http://app.test",
                   EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend", DEFAULT_FROM_EMAIL="bot@app.test")
class ReleaseEmailTests(SimpleTestCase):
    factory = APIRequestFactory()

    def setUp(self):
        self.audit = mock.patch("releases.api.record").start()
        mock.patch("releases.api.one_release_json", side_effect=lambda **lookup: RELEASE if lookup == {"pk": 5} else None).start()
        self.addCleanup(mock.patch.stopall)

    def call(self, view, user, *, method="get", data=None, release_id=5):
        request = getattr(self.factory, method)("/api/x", data or {}, format="json" if method != "get" else None)
        force_authenticate(request, user=user)
        return view(request, release_id=release_id)

    def test_html_is_escaped_grouped_and_links_jira(self):
        html = release_email.notes_html(RELEASE)
        self.assertIn("Faster &lt;search&gt; &amp; exports", html)
        self.assertNotIn("<edit>", html)
        self.assertLess(html.index("What&#x27;s new"), html.index("Bug fixes"))  # category order, not item order
        self.assertIn('href="https://jira.test/browse/CT-367"', html)
        self.assertIn("Released on October 1, 2026", html)

    def test_download_is_an_html_attachment(self):
        response = self.call(api.release_notes_file, ADMIN)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Disposition"], 'attachment; filename="iCRM-release-notes-11.1.html"')

    def test_send_attaches_notes_and_audits(self):
        response = self.call(api.email_release, ADMIN, method="post",
                             data={"to": ["A@x.test", "a@x.test"], "cc": ["a@x.test", "b@x.test"], "message": "FYI"})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["recipients"], ["a@x.test", "b@x.test"])
        sent = mail.outbox[0]
        self.assertEqual((sent.to, sent.cc), (["a@x.test"], ["b@x.test"]))
        self.assertEqual(sent.subject, "iCRM Release 11.1 - release notes")
        self.assertTrue(sent.body.startswith("FYI\n\n"))
        self.assertIn("CT-367: Fix login loop", sent.body)
        self.assertIn("http://app.test/#icrm-v111", sent.body)
        name, content, mimetype = sent.attachments[0]
        self.assertEqual((name, mimetype), ("iCRM-release-notes-11.1.html", "text/html"))
        self.assertIn("Fix login loop", content)
        self.assertEqual(self.audit.call_args.args[1], "RELEASE_EMAIL")

    def test_invalid_recipients_are_rejected(self):
        for data in ({"to": []}, {"to": ["not-an-address"]}, {"to": [f"u{i}@x.test" for i in range(21)]}):
            self.assertEqual(self.call(api.email_release, ADMIN, method="post", data=data).status_code, 400)
        self.assertEqual(mail.outbox, [])

    def test_admin_only(self):
        self.assertEqual(self.call(api.email_release, VIEWER, method="post", data={"to": ["a@x.test"]}).status_code, 403)
        self.assertEqual(self.call(api.release_notes_file, VIEWER).status_code, 403)

    def test_unknown_release_is_404(self):
        self.assertEqual(self.call(api.release_notes_file, ADMIN, release_id=99).status_code, 404)

    def test_mail_server_failure_is_reported_not_hidden(self):
        with mock.patch("django.core.mail.EmailMessage.send", side_effect=smtplib.SMTPAuthenticationError(535, b"bad")):
            response = self.call(api.email_release, ADMIN, method="post", data={"to": ["a@x.test"]})
        self.assertEqual(response.status_code, 502)
        self.assertNotIn("535", response.data["detail"])
        self.assertIn("failed", self.audit.call_args.kwargs["details"])


class EmlFileBackendTests(SimpleTestCase):
    def test_each_message_is_saved_as_its_own_eml_file(self):
        with tempfile.TemporaryDirectory() as folder, override_settings(EMAIL_FILE_PATH=folder):
            email = EmailMessage("Hi", "Body", "bot@app.test", ["a@x.test"])
            email.attach("notes.html", "<p>x</p>", "text/html")
            self.assertEqual(EmlFileBackend().send_messages([email, EmailMessage("Two", "B", to=["b@x.test"])]), 2)
            files = sorted(Path(folder).glob("*.eml"))
            self.assertEqual(len(files), 2)
            parsed = [message_from_bytes(f.read_bytes()) for f in files]
            first = next(m for m in parsed if m["Subject"] == "Hi")
            self.assertEqual([p.get_filename() for p in first.walk() if p.get_filename()], ["notes.html"])


class PublishExistingVersionTests(SimpleTestCase):
    """An upload only ever creates a new version; it never replaces or adds to an existing one."""

    factory = APIRequestFactory()
    BODY = {"fileName": "notes.docx", "version": "11.1", "releaseDate": "2026-10-01",
            "items": [{"category": "BUG_FIX", "title": "Fix login loop"}]}

    def setUp(self):
        self.versions = mock.patch("releases.api.ReleaseVersion").start()
        self.audit = mock.patch("releases.api.record").start()
        self.addCleanup(mock.patch.stopall)

    def publish(self, body):
        request = self.factory.post("/api/admin/releases", body, format="json")
        force_authenticate(request, user=ADMIN)
        return api.publish(request)

    def test_existing_version_is_refused_and_left_untouched(self):
        self.versions.objects.filter.return_value.exists.return_value = True
        for mode in (None, "replace", "append"):  # an old client's mode changes nothing
            response = self.publish({**self.BODY, **({"mode": mode} if mode else {})})
            self.assertEqual(response.status_code, 409)
            self.assertIn("Version 11.1 already exists", response.data["detail"])
        self.versions.objects.filter.assert_called_with(version="11.1")
        self.versions.objects.create.assert_not_called()
        self.audit.assert_not_called()


class CsvParserTests(SimpleTestCase):
    def test_reads_the_export_columns(self):
        from .services.csv_parser import parse_csv
        doc = parse_csv(
            b'\xef\xbb\xbf"Version","Release date","Status","Latest","Category","Jira ID","Title","Description"\r\n'
            b'"11.2","2026-11-15","UPCOMING","","BUG_FIX","CT-377","Fix login loop","Was looping"\r\n'
            b'"11.2","2026-11-15","UPCOMING","","New","","\'=Totals row","" \r\n'
            b'"11.1","2026-10-01","RELEASED","yes","Security","","Other version",""\r\n'
        )
        self.assertEqual((doc.version, str(doc.release_date), doc.status), ("11.2", "2026-11-15", "UPCOMING"))
        self.assertEqual([(i["category"], i["jira_id"], i["title"]) for i in doc.items],
                         [("BUG_FIX", "CT-377", "Fix login loop"), ("NEW_FEATURE", None, "=Totals row")])
        self.assertIn("11.1", doc.warnings[0])

    def test_title_only_semicolon_file(self):
        from .services.csv_parser import parse_csv
        doc = parse_csv(b"Title;Type\nCT-9: Fix the crash on save;\n")
        self.assertEqual(doc.items[0]["jira_id"], "CT-9")
        self.assertEqual(doc.items[0]["category"], "BUG_FIX")
        self.assertIsNone(doc.version)

    def test_needs_a_title_column(self):
        from .services.csv_parser import CsvParseError, parse_csv
        with self.assertRaises(CsvParseError):
            parse_csv(b"Version,Jira\n11.2,CT-1\n")
