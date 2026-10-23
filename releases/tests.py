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
from integrations.tests.fakes import FakeProduct, FakeUser

from . import api
from .services import release_email

ADMIN = FakeUser(admin=True)
VIEWER = FakeUser(jira=True)

RELEASE = {
    "id": 5, "productId": 1, "productName": "iCRM", "version": "11.1", "releaseDate": "2026-10-01", "description": "Faster <search> & exports",
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
        mock.patch("integrations.credentials.stored", return_value={}).start()  # no connection settings saved in the app
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
        self.product = FakeProduct()
        mock.patch("releases.api.products.from_request", return_value=self.product).start()
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
            self.assertIn("iCRM version 11.1 already exists", response.data["detail"])
        self.versions.objects.filter.assert_called_with(product=self.product, version="11.1")
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


class SignedInReadTests(SimpleTestCase):
    """Release notes and their screenshots are for signed-in users only."""

    factory = APIRequestFactory()

    def test_release_list_needs_a_signed_in_user(self):
        from releases import api
        mock.patch("releases.api.all_releases_json", return_value=[]).start()
        mock.patch("releases.api.products.from_request", return_value=FakeProduct()).start()
        self.addCleanup(mock.patch.stopall)
        self.assertEqual(api.list_releases(self.factory.get("/api/releases")).status_code, 401)
        request = self.factory.get("/api/releases")
        force_authenticate(request, user=FakeUser())
        self.assertEqual(api.list_releases(request).status_code, 200)

    def test_screenshot_needs_a_session_or_a_token(self):
        from django.contrib.auth.models import AnonymousUser
        from django.http import Http404
        from releases import api
        request = self.factory.get("/api/release-images/1")
        request.user = AnonymousUser()
        self.assertEqual(api.release_image(request, 1).status_code, 401)
        request.user = mock.Mock(is_authenticated=True)
        with mock.patch("releases.api.ReleaseImage.objects.filter") as images, self.assertRaises(Http404):
            images.return_value.first.return_value = None
            api.release_image(request, 1)


class PublicReadTests(SimpleTestCase):
    """The public release notes: anyone may read them while PUBLIC_RELEASE_NOTES=true, without Jira numbers."""

    factory = APIRequestFactory()

    def setUp(self):
        product = FakeProduct()
        self.public_product = mock.patch("releases.api.products.from_public_request", return_value=product).start()
        mock.patch("releases.api.all_releases_json", return_value=[RELEASE]).start()
        mock.patch("releases.api.one_release_json",
                   side_effect=lambda **lookup: RELEASE if lookup == {"version": "11.1", "product": product} else None).start()
        self.addCleanup(mock.patch.stopall)

    @override_settings(PUBLIC_RELEASE_NOTES=True)
    def test_list_is_public_without_jira_numbers(self):
        response = api.public_releases(self.factory.get("/api/public/releases"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["title"] for item in response.data[0]["items"]], ["Fix login loop", "Bulk <edit>"])
        self.assertNotIn("CT-367", str(response.data))
        self.assertEqual(RELEASE["items"][0]["jiraId"], "CT-367")  # the signed-in JSON is left as it was

    @override_settings(PUBLIC_RELEASE_NOTES=True)
    def test_one_version_and_unknown_version(self):
        response = api.public_release_by_version(self.factory.get("/api/public/releases/version/11.1"), version="11.1")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("jiraId", response.data["items"][0])
        response = api.public_release_by_version(self.factory.get("/api/public/releases/version/9"), version="9")
        self.assertEqual(response.status_code, 404)

    def test_screenshots_use_the_public_url(self):
        from .services.release_json import public_release_json
        release = {**RELEASE, "images": [{"id": 7, "url": "/api/release-images/7", "caption": None}],
                   "items": [{**RELEASE["items"][0], "images": [{"id": 8, "url": "/api/release-images/8", "caption": "x"}]}]}
        public = public_release_json([release])[0]
        self.assertEqual(public["images"][0]["url"], "/api/public/release-images/7")
        self.assertEqual(public["items"][0]["images"][0]["url"], "/api/public/release-images/8")

    @override_settings(PUBLIC_RELEASE_NOTES=False)
    def test_switched_off_is_404(self):
        from django.http import Http404
        self.assertEqual(api.public_releases(self.factory.get("/api/public/releases")).status_code, 404)
        self.assertEqual(api.public_release_by_version(self.factory.get("/x"), version="11.1").status_code, 404)
        with self.assertRaises(Http404):
            api.public_release_image(self.factory.get("/api/public/release-images/1"), 1)

    @override_settings(PUBLIC_RELEASE_NOTES=True)
    def test_public_screenshot_needs_no_sign_in(self):
        from django.contrib.auth.models import AnonymousUser
        from django.http import Http404
        request = self.factory.get("/api/public/release-images/1")
        request.user = AnonymousUser()
        with mock.patch("releases.api.ReleaseImage.objects.filter") as images, self.assertRaises(Http404):
            images.return_value.exists.return_value = True
            images.return_value.first.return_value = None  # reaches the lookup: no 401
            api.public_release_image(request, 1)

    @override_settings(PUBLIC_RELEASE_NOTES=True)
    def test_a_screenshot_of_another_product_is_not_served(self):
        from django.http import Http404
        with mock.patch("releases.api.ReleaseImage.objects.filter") as images, self.assertRaises(Http404):
            images.return_value.exists.return_value = False
            api.public_release_image(self.factory.get("/api/public/release-images/1?key=abc"), 1)
        images.assert_called_with(pk=1, release_version__product_id=1)

    def test_public_json_hides_the_product_id_and_keeps_the_key_on_screenshots(self):
        release = {**RELEASE, "images": [{"id": 7, "url": "/api/release-images/7", "caption": None}]}
        from .services.release_json import public_release_json
        public = public_release_json([release], "k3yK3yK3y")[0]
        self.assertNotIn("productId", public)
        self.assertEqual(public["images"][0]["url"], "/api/public/release-images/7?key=k3yK3yK3y")

    @override_settings(PUBLIC_RELEASE_NOTES=True)
    def test_signed_in_endpoints_still_need_sign_in(self):
        self.assertEqual(api.list_releases(self.factory.get("/api/releases")).status_code, 401)


MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 100
WEBM = b"\x1a\x45\xdf\xa3" + b"\x00" * 100


class VideoTests(SimpleTestCase):
    """Short MP4 / WebM videos are uploaded and shown like screenshots, up to 25 MB."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        override = override_settings(IMAGE_DIR=Path(self.tmp.name))
        override.enable()
        self.addCleanup(override.disable)

    def test_mp4_and_webm_are_recognised_from_the_bytes(self):
        from .services import image_store
        self.assertEqual(image_store.sniff(MP4), "video/mp4")
        self.assertEqual(image_store.sniff(WEBM), "video/webm")
        name, content_type = image_store.save_bytes(MP4)
        self.assertTrue(name.endswith(".mp4"))
        self.assertEqual(content_type, "video/mp4")
        self.assertIsNotNone(image_store.path_for(name))

    def test_size_limits_are_25_mb_for_videos_and_5_mb_for_images(self):
        from .services import image_store
        image_store.save_bytes(MP4 + b"\x00" * (6 * 1024 * 1024))  # over the image limit, fine for a video
        with self.assertRaisesMessage(image_store.ImageError, "larger than 25 MB"):
            image_store.save_bytes(MP4 + b"\x00" * (25 * 1024 * 1024))
        with self.assertRaisesMessage(image_store.ImageError, "larger than 5 MB"):
            image_store.save_bytes(b"GIF89a" + b"\x00" * (5 * 1024 * 1024))

    def test_word_documents_cannot_carry_videos(self):
        import base64
        from .services import image_store
        with self.assertRaises(image_store.ImageError):
            image_store.to_data_url(MP4)
        with self.assertRaises(image_store.ImageError):
            image_store.save_data_url(f"data:image/png;base64,{base64.b64encode(MP4).decode()}")

    def test_range_requests_get_that_part_only(self):
        from .services import image_store
        name, _ = image_store.save_bytes(MP4)
        image = mock.Mock(file_name=name, content_type="video/mp4")
        factory = APIRequestFactory()
        with mock.patch("releases.api.ReleaseImage.objects.filter") as images:
            images.return_value.first.return_value = image
            whole = api._image_response(factory.get("/x"), 1, "private")
            self.assertEqual(whole.status_code, 200)
            self.assertEqual(whole["Accept-Ranges"], "bytes")
            whole.close()
            part = api._image_response(factory.get("/x", HTTP_RANGE="bytes=4-11"), 1, "private")
            self.assertEqual(part.status_code, 206)
            self.assertEqual(part["Content-Range"], f"bytes 4-11/{len(MP4)}")
            self.assertEqual(b"".join(part.streaming_content), b"ftypmp42")

    def test_byte_ranges(self):
        self.assertEqual(api._byte_range("bytes=0-", 100), (0, 99))
        self.assertEqual(api._byte_range("bytes=10-2000", 100), (10, 99))
        self.assertEqual(api._byte_range("bytes=-10", 100), (90, 99))
        self.assertIsNone(api._byte_range("bytes=200-", 100))
        self.assertIsNone(api._byte_range("bytes=0-1,5-6", 100))  # several ranges: the whole file instead
        self.assertIsNone(api._byte_range("", 100))


class LatestVersionTests(SimpleTestCase):
    """Latest is the released version with the highest number, compared part by part as numbers."""

    def test_version_numbers_compare_as_numbers(self):
        from .services.latest import version_key
        ordered = ["10.8.5", "10.9", "10.9.0", "10.10.0", "11.1"]
        self.assertEqual(sorted(reversed(ordered), key=version_key), ordered)
        self.assertGreater(version_key("10.9.0"), version_key("10.8.5"))
        self.assertGreater(version_key("2.0"), version_key("1.99.99"))


class ProductTests(SimpleTestCase):
    """The product of a request, and products added and removed by admins (database mocked)."""

    factory = APIRequestFactory()

    def setUp(self):
        self.audit = mock.patch("releases.api.record").start()
        self.objects = mock.patch("releases.products.Product.objects").start()
        self.addCleanup(mock.patch.stopall)

    def test_the_header_or_query_picks_the_product_and_none_means_the_first(self):
        from rest_framework.request import Request
        from rest_framework.exceptions import ValidationError
        from . import products
        iuc = FakeProduct(2, "IUC")
        lookup = self.objects.select_related.return_value.filter
        lookup.return_value.first.return_value = iuc
        self.assertIs(products.from_request(Request(self.factory.get("/api/x", HTTP_X_PRODUCT="2"))), iuc)
        lookup.assert_called_with(pk="2")
        self.assertIs(products.from_request(Request(self.factory.get("/api/x?product=2"))), iuc)
        self.objects.filter.return_value.first.return_value = FakeProduct()
        self.assertEqual(products.from_request(Request(self.factory.get("/api/x"))).name, "iCRM")
        self.objects.filter.assert_called_with(parent__isnull=True)  # none picked: the first product, not a client
        for bad in ("abc", "2; DROP"):
            with self.assertRaises(ValidationError):
                products.from_request(Request(self.factory.get("/api/x", HTTP_X_PRODUCT=bad)))
        lookup.return_value.first.return_value = None  # removed meanwhile
        with self.assertRaises(ValidationError):
            products.from_request(Request(self.factory.get("/api/x", HTTP_X_PRODUCT="9")))

    def call(self, view, user, method="post", data=None, **kwargs):
        request = getattr(self.factory, method)("/api/x", data or {}, format="json")
        force_authenticate(request, user=user)
        return view(request, **kwargs)

    def test_only_admins_add_and_remove(self):
        self.assertEqual(self.call(api.add_product, VIEWER, data={"name": "New"}).status_code, 403)
        self.assertEqual(self.call(api.remove_product, VIEWER, method="delete", product_id=2).status_code, 403)

    def test_one_with_releases_or_clients_and_the_last_product_stay(self):
        with mock.patch("releases.api.Product.objects") as objects:
            product = mock.Mock(parent_id=None, releases=mock.Mock(count=mock.Mock(return_value=2)),
                                clients=mock.Mock(count=mock.Mock(return_value=0)))
            product.name = product.label = "IUC"
            objects.select_related.return_value.filter.return_value.first.return_value = product
            remove = lambda: self.call(api.remove_product, ADMIN, method="delete", product_id=2)  # noqa: E731
            response = remove()
            self.assertEqual(response.status_code, 400)
            self.assertIn("2 release version(s)", response.data["detail"])
            product.releases.count.return_value = 0
            product.clients.count.return_value = 3
            self.assertIn("3 client(s)", remove().data["detail"])
            product.clients.count.return_value = 0
            objects.filter.return_value.count.return_value = 1
            self.assertEqual(remove().status_code, 400)
            product.delete.assert_not_called()
            objects.filter.return_value.count.return_value = 3
            self.assertEqual(remove().status_code, 204)
            product.delete.assert_called_once()
            self.assertEqual(self.audit.call_args.kwargs["target"], "IUC")

    def test_a_client_can_be_the_last_of_its_product(self):
        with mock.patch("releases.api.Product.objects") as objects:
            client = mock.Mock(parent_id=1, releases=mock.Mock(count=mock.Mock(return_value=0)),
                               clients=mock.Mock(count=mock.Mock(return_value=0)), label="IUC – Client A")
            objects.select_related.return_value.filter.return_value.first.return_value = client
            objects.filter.return_value.count.return_value = 1  # only one product: doesn't matter for a client
            self.assertEqual(self.call(api.remove_product, ADMIN, method="delete", product_id=5).status_code, 204)

    def test_names_are_trimmed_and_unique_within_their_product(self):
        with mock.patch("releases.api.Product.objects") as objects:
            objects.filter.return_value.exists.return_value = True
            response = self.call(api.add_product, ADMIN, data={"name": "  icrm "})
            self.assertEqual(response.status_code, 400)
            objects.filter.assert_called_with(parent=None, name__iexact="icrm")
            objects.filter.return_value.exists.return_value = False
            objects.aggregate.return_value = {"m": 3}
            objects.create.return_value = FakeProduct(4, "Sales   Audit 2")
            self.assertEqual(self.call(api.add_product, ADMIN, data={"name": "Sales   Audit 2"}).status_code, 201)
            objects.create.assert_called_with(name="Sales Audit 2", parent=None, display_order=4)

    def test_a_client_is_added_to_a_product_never_to_a_client(self):
        with mock.patch("releases.api.Product.objects") as objects:
            iuc = FakeProduct(2, "IUC")
            objects.filter.return_value.first.return_value = iuc
            objects.filter.return_value.exists.return_value = False
            objects.aggregate.return_value = {"m": 3}
            created = FakeProduct(7, "Client A")
            created.label = "IUC – Client A"
            objects.create.return_value = created
            response = self.call(api.add_product, ADMIN, data={"name": "Client A", "parentId": 2})
            self.assertEqual(response.status_code, 201, response.data)
            objects.filter.assert_any_call(pk=2, parent__isnull=True)
            objects.create.assert_called_with(name="Client A", parent=iuc, display_order=4)
            self.assertEqual(self.audit.call_args.kwargs["target"], "IUC – Client A")
            objects.filter.return_value.first.return_value = None  # 7 is a client, not a product
            self.assertEqual(self.call(api.add_product, ADMIN, data={"name": "Sub", "parentId": 7}).status_code, 400)

    def test_release_files_and_emails_carry_the_product_name(self):
        mock.patch("integrations.credentials.stored", return_value={}).start()
        iuc = {**RELEASE, "productName": "IUC"}
        self.assertEqual(release_email.file_name(iuc), "IUC-release-notes-11.1.html")
        self.assertIn("<h1>IUC Release 11.1</h1>", release_email.notes_html(iuc))


class PublicKeyTests(SimpleTestCase):
    """The public page names its product by a key that can't be guessed, never by its id."""

    factory = APIRequestFactory()

    def setUp(self):
        self.objects = mock.patch("releases.products.Product.objects").start()
        self.addCleanup(mock.patch.stopall)

    def pick(self, url):
        from rest_framework.request import Request
        from . import products
        return products.from_public_request(Request(self.factory.get(url)))

    def test_the_key_picks_the_product_and_no_key_the_first(self):
        client = FakeProduct(4, "Client A")
        self.objects.select_related.return_value.filter.return_value.first.return_value = client
        self.assertIs(self.pick("/api/public/releases?key=Ab3_-xYz9QwErTy1"), client)
        self.objects.select_related.return_value.filter.assert_called_with(public_key="Ab3_-xYz9QwErTy1")
        self.objects.filter.return_value.first.return_value = FakeProduct()
        self.assertEqual(self.pick("/api/public/releases").name, "iCRM")

    def test_ids_headers_and_unknown_keys_are_404(self):
        from rest_framework.exceptions import NotFound
        self.objects.select_related.return_value.filter.return_value.first.return_value = None
        self.objects.filter.return_value.first.return_value = FakeProduct()
        for url in ("/api/public/releases?key=Ab3_-xYz9QwErTy1", "/api/public/releases?key=2",
                    "/api/public/releases?key=%27%3B--"):
            with self.assertRaises(NotFound):
                self.pick(url)
        # An id in the header or ?product= is ignored: the first product, not product 2.
        from rest_framework.request import Request
        from . import products
        request = Request(self.factory.get("/api/public/releases?product=2", HTTP_X_PRODUCT="2"))
        self.assertEqual(products.from_public_request(request).name, "iCRM")

    def test_only_admins_see_the_keys(self):
        from . import products
        product = FakeProduct()
        product.public_key = "Ab3_-xYz9QwErTy1"
        self.assertNotIn("publicKey", products.product_json(product))
        self.assertEqual(products.product_json(product, admin=True)["publicKey"], "Ab3_-xYz9QwErTy1")

    def test_product_list_needs_sign_in_and_new_link_needs_admin(self):
        self.assertEqual(api.list_products(self.factory.get("/api/products")).status_code, 401)
        request = self.factory.post("/api/admin/products/2/public-key")
        force_authenticate(request, user=VIEWER)
        self.assertEqual(api.new_public_key(request, product_id=2).status_code, 403)
