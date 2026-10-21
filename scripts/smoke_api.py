"""End-to-end check of every API endpoint against the real database, without keeping any change.

Everything runs inside one transaction that is rolled back at the end; screenshot files written during
the run are deleted. Run:  .venv\\Scripts\\python manage.py shell < scripts\\smoke_api.py
"""
import base64
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.test import Client, override_settings

from accounts.models import AppUser
from accounts.tokens import create_reset_token, create_token
from releases.models import ReleaseVersion

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)
SAMPLE_DOCX = Path(settings.BASE_DIR).parent / "my-react-app" / "public" / "samples" / "iCRM-Release-11.1-sample.docx"
results = []


def check(name, response, expected):
    ok = response.status_code == expected
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'} {response.status_code} {name}" + ("" if ok else f"  {response.content[:300]!r}"))
    try:
        return response.json()
    except (ValueError, TypeError):  # no JSON body (e.g. 204)
        return None


class Rollback(Exception):
    pass


image_dir = Path(settings.IMAGE_DIR)
files_before = set(image_dir.iterdir()) if image_dir.exists() else set()
admin_user = AppUser.objects.get(username="admin")
other_user = AppUser.objects.get(username="user@example.com")
H = {"HTTP_HOST": "localhost"}
admin = Client(**H, HTTP_AUTHORIZATION=f"Bearer {create_token(admin_user.id)}")
plain = Client(**H, HTTP_AUTHORIZATION=f"Bearer {create_token(other_user.id)}")
anon = Client(**H)
J = "application/json"
baseline = 0  # number of checks that existed before the integrations were added (set after them)

try:
    with transaction.atomic():
        # ---- health + auth ----
        check("health", anon.get("/api/health"), 200)
        check("auth options", anon.get("/api/auth/options"), 200)
        with override_settings(ALLOW_REGISTRATION=True, REGISTRATION_EMAIL_DOMAINS=["aiintelekt.com"]):
            check("register outside the allowed domains -> 400", anon.post("/api/auth/register", {"email": "smoke.test@example.com", "password": "smoke-pass-1"}, content_type=J), 400)
        with override_settings(ALLOW_REGISTRATION=False):
            check("register while sign-up is closed -> 403", anon.post("/api/auth/register", {"email": "smoke.test@example.com", "password": "smoke-pass-1"}, content_type=J), 403)
        with override_settings(ALLOW_REGISTRATION=True, REGISTRATION_EMAIL_DOMAINS=[]):
            check("register new account", anon.post("/api/auth/register", {"email": "smoke.test@example.com", "password": "smoke-pass-1", "displayName": "Smoke"}, content_type=J), 201)
            check("register duplicate -> 409", anon.post("/api/auth/register", {"email": "smoke.test@example.com", "password": "smoke-pass-1"}, content_type=J), 409)
        body = check("login new account", anon.post("/api/auth/login", {"email": "SMOKE.test@example.com ", "password": "smoke-pass-1"}, content_type=J), 200)
        signed_in = Client(**H, HTTP_AUTHORIZATION=f"Bearer {body['token']}")
        check("me with its token", signed_in.get("/api/auth/me"), 200)
        check("logout", signed_in.post("/api/auth/logout"), 204)
        check("signed-out token -> 401", signed_in.get("/api/auth/me"), 401)
        check("login wrong password -> 401", anon.post("/api/auth/login", {"email": "smoke.test@example.com", "password": "nope"}, content_type=J), 401)
        check("forgot password", anon.post("/api/auth/forgot-password", {"email": "smoke.test@example.com"}, content_type=J), 202)
        smoke = AppUser.objects.get(email="smoke.test@example.com")
        token = create_reset_token(smoke)
        before_reset = Client(**H, HTTP_AUTHORIZATION=f"Bearer {create_token(smoke.id)}")
        check("reset password", anon.post("/api/auth/reset-password", {"token": token, "password": "smoke-pass-2"}, content_type=J), 200)
        check("token from before the reset -> 401", before_reset.get("/api/auth/me"), 401)
        check("reset link reused -> 400", anon.post("/api/auth/reset-password", {"token": token, "password": "smoke-pass-3"}, content_type=J), 400)
        check("login with new password", anon.post("/api/auth/login", {"email": "smoke.test@example.com", "password": "smoke-pass-2"}, content_type=J), 200)
        check("session token rejected as reset token", anon.post("/api/auth/reset-password", {"token": create_token(smoke.id), "password": "smoke-pass-4"}, content_type=J), 400)

        # ---- permissions ----
        check("admin endpoint, signed out -> 401", anon.get("/api/admin/users"), 401)
        check("admin endpoint, non-admin -> 403", plain.get("/api/admin/users"), 403)
        check("jira, non-viewer -> 403", plain.get("/api/jira-issues"), 403)

        # ---- jira ----
        issues = check("jira list (admin)", admin.get("/api/jira-issues"), 200)
        check("jira detail", admin.get(f"/api/jira-issues/{issues[0]['jiraId']}"), 200)
        check("jira detail missing -> 404", admin.get("/api/jira-issues/NOPE-1"), 404)

        # ---- users + audit ----
        check("users list", admin.get("/api/admin/users"), 200)
        check("audit log CSV", admin.get("/api/admin/audit-log.csv?action=LOGIN"), 200)
        check("audit log CSV, non-admin -> 403", plain.get("/api/admin/audit-log.csv"), 403)
        body = check("grant Jira to user", admin.patch(f"/api/admin/users/{other_user.id}", {"canViewJira": True}, content_type=J), 200)
        assert body["canViewJira"] is True
        check("that user can now open Jira", plain.get("/api/jira-issues"), 200)
        check("revoke Jira again", admin.patch(f"/api/admin/users/{other_user.id}", {"canViewJira": False}, content_type=J), 200)
        check("cannot remove own admin -> 400", admin.patch(f"/api/admin/users/{admin_user.id}", {"isAdmin": False}, content_type=J), 400)
        body = check("audit log filtered", admin.get("/api/admin/audit-log?action=JIRA&limit=5"), 200)
        assert body["total"] >= 2, body
        check("audit log unknown action -> 400", admin.get("/api/admin/audit-log?action=NOPE"), 400)

        # ---- Word upload ----
        with open(SAMPLE_DOCX, "rb") as f:
            parsed = check("parse sample .docx", admin.post("/api/admin/releases/parse", {"file": f}), 200)
        print(f"     parsed version {parsed['version']}, {len(parsed['items'])} items, {len(parsed['warnings'])} warnings")
        png_url = "data:image/png;base64," + base64.b64encode(PNG).decode()
        release = check("publish new version", admin.post("/api/admin/releases", {
            "fileName": "smoke.docx", "version": "0.0-smoke", "releaseDate": "2026-09-30", "status": "UPCOMING",
            "plannedLabel": "Someday", "summary": "Smoke test", "highlights": ["One"], "markLatest": False,
            "images": [{"dataUrl": png_url, "caption": "Gallery shot"}],
            "items": [{"category": "NEW_FEATURE", "title": "Feature A", "jiraId": "CS-1", "images": [{"dataUrl": png_url}]},
                      {"category": "BUG_FIX", "title": "Fix B", "description": "detail"}],
        }, content_type=J), 201)
        assert len(release["items"]) == 2 and len(release["images"]) == 1 and len(release["items"][0]["images"]) == 1
        check("publish invalid (no items) -> 400", admin.post("/api/admin/releases", {"fileName": "x", "version": "0.0-x", "releaseDate": "2026-09-30", "items": []}, content_type=J), 400)
        rid = release["id"]
        check("public read by version", anon.get("/api/releases/version/0.0-smoke"), 200)
        check("screenshot served", anon.get(release["images"][0]["url"]), 200)
        # An upload only adds new versions; changes to an existing one are made on the Release Notes page.
        check("upload to an existing version -> 409", admin.post("/api/admin/releases", {"fileName": "smoke2.docx", "version": "0.0-smoke", "releaseDate": "2026-09-30", "mode": "append", "markLatest": False, "items": [{"category": "BUG_FIX", "title": "Fix C"}]}, content_type=J), 409)

        # ---- edit ----
        body = check("edit release details", admin.patch(f"/api/admin/releases/{rid}", {"summary": "Edited", "status": "RELEASED", "knownIssues": ["K1", " "]}, content_type=J), 200)
        assert body["description"] == "Edited" and body["plannedLabel"] is None and body["knownIssues"] == ["K1"]
        body = check("add item", admin.post(f"/api/admin/releases/{rid}/items", {"category": "SECURITY", "title": "Sec D"}, content_type=J), 201)
        item_id = next(i["id"] for i in body["items"] if i["title"] == "Sec D")
        body = check("edit item (change category)", admin.patch(f"/api/admin/release-items/{item_id}", {"category": "IMPROVEMENT", "title": "Improved D", "jiraId": "CS-2"}, content_type=J), 200)
        assert any(i["title"] == "Improved D" and i["category"] == "IMPROVEMENT" for i in body["items"])
        from django.core.files.uploadedfile import SimpleUploadedFile
        body = check("add screenshot to item", admin.post(f"/api/admin/releases/{rid}/images", {"file": SimpleUploadedFile("s.png", PNG), "caption": "Item shot", "itemId": str(item_id)}), 201)
        image_id = next(i for i in body["items"] if i["id"] == item_id)["images"][0]["id"]
        check("reject non-image upload -> 400", admin.post(f"/api/admin/releases/{rid}/images", {"file": SimpleUploadedFile("s.png", b"not an image")}), 400)
        check("edit caption", admin.patch(f"/api/admin/release-images/{image_id}", {"caption": "New caption"}, content_type=J), 200)
        check("delete screenshot", admin.delete(f"/api/admin/release-images/{image_id}"), 200)
        check("delete item", admin.delete(f"/api/admin/release-items/{item_id}"), 200)
        check("mark latest", admin.patch(f"/api/admin/releases/{rid}", {"markLatest": True}, content_type=J), 200)
        assert ReleaseVersion.objects.filter(latest=True).count() == 1
        check("delete release", admin.delete(f"/api/admin/releases/{rid}"), 204)
        check("deleted release -> 404", anon.get(f"/api/releases/{rid}"), 404)
        check("non-admin edit -> 403", plain.patch(f"/api/admin/releases/{rid}", {"summary": "x"}, content_type=J), 403)
        baseline = len(results)

        # ---- live integrations: access rules and configuration only (live data is covered by
        # integrations/tests with mocked responses; real Jira/Bitbucket are only called if .env has credentials) ----
        check("integrations status, signed out -> 401", anon.get("/api/integrations/status"), 401)
        check("integrations status, no Jira access -> 403", plain.get("/api/integrations/status"), 403)
        status = check("integrations status (admin)", admin.get("/api/integrations/status"), 200)
        check("integrations dashboard, no Jira access -> 403", plain.get("/api/integrations/dashboard"), 403)
        check("integrations refresh, non-admin -> 403", plain.post("/api/integrations/refresh"), 403)
        # 400 when Bitbucket is configured (not in BITBUCKET_REPOSITORIES), 503 while it isn't configured.
        code = admin.get("/api/integrations/bitbucket/repositories/not-allowed/commits").status_code
        results.append(code in (400, 503))
        print(f"{'PASS' if results[-1] else 'FAIL'} {code} bitbucket repo outside the allow-list -> 400/503")
        check("integrations refresh (admin)", admin.post("/api/integrations/refresh"), 200)
        check("audit log filter INTEGRATION_REFRESH", admin.get("/api/admin/audit-log?action=INTEGRATION_REFRESH"), 200)
        print(f"     Jira configured: {status['jira']['configured']}, Bitbucket configured: {status['bitbucket']['configured']}")
        raise Rollback
except Rollback:
    pass
finally:
    new_files = (set(image_dir.iterdir()) if image_dir.exists() else set()) - files_before
    for path in new_files:
        path.unlink()
    print(f"rolled back all database changes; removed {len(new_files)} test screenshot files")

print(f"\n{sum(results[:baseline])}/{baseline} original checks passed")
print(f"{sum(results[baseline:])}/{len(results) - baseline} integration access checks passed")
print(f"{sum(results)}/{len(results)} checks passed")
assert ReleaseVersion.objects.filter(version="0.0-smoke").count() == 0
assert AppUser.objects.filter(email="smoke.test@example.com").count() == 0
