from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path

from accounts import api as accounts_api
from config.health import health
from audit import api as audit_api
from frontend_app.views import spa
from integrations import api as integrations_api
from jira import api as jira_api
from releases import api as releases_api

admin.site.site_header = "iCRM Release Notes administration"
admin.site.site_title = "iCRM Release Notes"
admin.site.index_title = "Manage release notes"

# Same paths as python-backend (no trailing slashes), so the React app needs no changes.
api = [
    path("releases", releases_api.list_releases),
    path("releases/version/<str:version>", releases_api.release_by_version),
    path("releases/<int:release_id>", releases_api.release_by_id),
    path("release-images/<int:image_id>", releases_api.release_image),
    path("health", health),
    path("auth/options", accounts_api.auth_options),
    path("auth/register", accounts_api.register),
    path("auth/login", accounts_api.login),
    path("auth/logout", accounts_api.logout),
    path("auth/logout-all", accounts_api.logout_everywhere),
    path("auth/me", accounts_api.me),
    path("auth/forgot-password", accounts_api.forgot_password),
    path("auth/reset-password", accounts_api.reset_password),
    path("auth/change-password", accounts_api.change_password),
    path("jira-issues", jira_api.list_issues),
    path("jira-issues/<str:jira_id>", jira_api.issue_detail),
    path("admin/releases/parse", releases_api.parse_upload),
    path("admin/releases", releases_api.publish),
    path("admin/releases/<int:release_id>", releases_api.release_detail),
    path("admin/releases/<int:release_id>/items", releases_api.add_item),
    path("admin/releases/<int:release_id>/items/import", releases_api.import_items),
    path("admin/releases/<int:release_id>/images", releases_api.add_image),
    path("admin/releases/<int:release_id>/notes-file", releases_api.release_notes_file),
    path("admin/releases/<int:release_id>/email", releases_api.email_release),
    path("admin/release-items/<int:item_id>", releases_api.item_detail),
    path("admin/release-images/<int:image_id>", releases_api.image_detail),
    path("admin/users", accounts_api.list_users),
    path("admin/users/<int:user_id>", accounts_api.update_user),
    path("admin/audit-log", audit_api.audit_log),
    path("admin/audit-log.csv", audit_api.audit_log_csv),
    # Live Jira Cloud / Bitbucket Cloud data (integrations/api.py).
    path("integrations/status", integrations_api.status),
    path("integrations/refresh", integrations_api.refresh),
    path("integrations/credentials", integrations_api.credentials_settings),
    path("integrations/scope", integrations_api.scope_add),
    path("integrations/scope/<int:scope_id>", integrations_api.scope_remove),
    path("integrations/dashboard", integrations_api.dashboard),
    path("integrations/jira/filters", integrations_api.jira_filters),
    path("integrations/jira/summary", integrations_api.jira_summary),
    path("integrations/jira/issues", integrations_api.jira_issues),
    path("integrations/jira/releases", integrations_api.jira_releases),
    path("integrations/bitbucket/repositories", integrations_api.bitbucket_repositories),
    path("integrations/bitbucket/repositories/<str:slug>/branches", integrations_api.bitbucket_branches),
    path("integrations/bitbucket/repositories/<str:slug>/commits", integrations_api.bitbucket_commits),
    path("integrations/bitbucket/repositories/<str:slug>/pullrequests", integrations_api.bitbucket_pull_requests),
]

urlpatterns = [
    # Off unless ENABLE_DJANGO_ADMIN=true; /admin/... then returns 404 (the React catch-all below skips admin/).
    *([path("admin/", admin.site.urls)] if settings.ENABLE_DJANGO_ADMIN else []),
    path("api/", include(api)),
    # Everything else is a React page (files such as /assets/... are served by WhiteNoise first).
    re_path(r"^(?!api/|admin/|static/)(?P<path>.*)$", spa),
]
