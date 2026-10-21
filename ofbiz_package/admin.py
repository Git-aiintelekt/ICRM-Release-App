from django.contrib import admin, messages
from django.http import FileResponse, Http404
from django.shortcuts import redirect
from django.template.defaultfilters import filesizeformat
from django.urls import path, reverse
from django.utils.html import format_html
from django.views.decorators.http import require_POST

from audit import models as audit
from audit.service import record

from .models import OfbizPackage
from .services.generator import PackageError, generate, preview


@admin.register(OfbizPackage)
class OfbizPackageAdmin(admin.ModelAdmin):
    """Generate / download OFBiz packages. Every package is kept, so an older one can be deployed again."""

    change_list_template = "admin/ofbiz_package/ofbizpackage/change_list.html"
    list_display = ["file_name", "release_version", "generated_at", "generated_by_name", "contents", "size", "download"]
    list_display_links = None
    search_fields = ["file_name", "release_version", "generated_by_name"]
    date_hierarchy = "generated_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False  # packages are retained so any of them can be downloaded again

    @admin.display(description="Contents")
    def contents(self, obj):
        return f"{obj.version_count} versions, {obj.item_count} changes, {obj.image_count} screenshots"

    @admin.display(description="Size", ordering="size_bytes")
    def size(self, obj):
        return filesizeformat(obj.size_bytes)

    @admin.display(description="")
    def download(self, obj):
        if not obj.path.is_file():
            return "file missing"
        url = reverse("admin:ofbiz_package_download", args=[obj.pk])
        return format_html('<a class="button" href="{}" title="SHA-256 {}">Download</a>', url, obj.sha256)

    def get_urls(self):
        return [
            path("generate/", self.admin_site.admin_view(require_POST(self.generate_view)), name="ofbiz_package_generate"),
            path("<int:package_id>/download/", self.admin_site.admin_view(self.download_view), name="ofbiz_package_download"),
            *super().get_urls(),
        ]

    def changelist_view(self, request, extra_context=None):
        latest = OfbizPackage.objects.order_by("-generated_at", "-id").first()
        extra_context = {
            **(extra_context or {}),
            "next_package": preview(),
            "latest_package": latest,
            "latest_download_url": reverse("admin:ofbiz_package_download", args=[latest.pk]) if latest else None,
            "just_generated": request.GET.get("generated") == str(latest.pk) if latest else False,
            "generate_url": reverse("admin:ofbiz_package_generate"),
        }
        return super().changelist_view(request, extra_context)

    def generate_view(self, request):
        try:
            package = generate(request.user)
        except PackageError as exc:
            messages.error(request, f"The package wasn't generated: {exc}")
            return redirect("admin:ofbiz_package_ofbizpackage_changelist")
        record(request, audit.OFBIZ_PACKAGE, request.user, target=package.file_name,
               details=f"generated: {package.version_count} versions, {package.item_count} changes, "
                       f"{package.image_count} screenshots, sha256 {package.sha256[:16]}")
        messages.success(request, f"Generated {package.file_name}. Download it below and deploy it into OFBiz.")
        return redirect(reverse("admin:ofbiz_package_ofbizpackage_changelist") + f"?generated={package.pk}")

    def download_view(self, request, package_id):
        package = OfbizPackage.objects.filter(pk=package_id).first()
        if package is None or not package.path.is_file():
            raise Http404("Package not found.")
        return FileResponse(open(package.path, "rb"), as_attachment=True, filename=package.file_name,
                            content_type="application/zip")
