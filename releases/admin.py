from django import forms
from django.contrib import admin, messages
from django.db import transaction
from django.db.models import Count, Max
from django.utils import timezone
from django.utils.html import format_html

from audit import models as audit
from audit.service import record

from .models import ReleaseImage, ReleaseItem, ReleaseUpload, ReleaseVersion
from .services import image_store
from .services.latest import refresh_latest


def _mark_edited(request, release: ReleaseVersion, details: str) -> None:
    ReleaseVersion.objects.filter(pk=release.pk).update(edited_at=timezone.now())
    record(request, audit.RELEASE_EDIT, request.user, target=str(release), details=f"admin: {details}")


class ScreenshotForm(forms.ModelForm):
    upload = forms.FileField(required=False, help_text="PNG, JPEG, GIF or WebP, up to 5 MB.")

    class Meta:
        model = ReleaseImage
        fields = ["upload", "caption", "display_order"]

    def clean(self):
        data = super().clean()
        upload = data.get("upload")
        if upload:
            content = upload.read(image_store.MAX_IMAGE_BYTES + 1)
            if len(content) > image_store.MAX_IMAGE_BYTES:
                raise forms.ValidationError("The screenshot is larger than 5 MB.")
            content_type = image_store.sniff(content)
            if content_type is None or image_store.is_video(content_type):  # videos: Release Notes page only
                raise forms.ValidationError("Screenshots must be PNG, JPEG, GIF or WebP.")
            data["upload_bytes"] = content
        elif not self.instance.pk and self.has_changed():
            raise forms.ValidationError("Choose an image file to upload.")
        return data

    def save(self, commit=True):
        content = self.cleaned_data.get("upload_bytes")
        if content:
            old = self.instance.file_name if self.instance.pk else None
            self.instance.file_name, self.instance.content_type = image_store.save_bytes(content)
            if old:
                transaction.on_commit(lambda: image_store.delete(old))
        return super().save(commit)


def preview(image: ReleaseImage):
    if not image.pk:
        return "—"
    return format_html('<a href="{0}" target="_blank"><img src="{0}" style="max-height:80px;max-width:160px"></a>', image.url)


class GalleryInline(admin.TabularInline):
    model = ReleaseImage
    form = ScreenshotForm
    fk_name = "release_version"
    extra = 0
    verbose_name = "gallery screenshot"
    verbose_name_plural = "Gallery screenshots (release-level; screenshots of one change are edited on the change)"
    readonly_fields = ["thumbnail"]
    fields = ["thumbnail", "upload", "caption", "display_order"]

    def get_queryset(self, request):
        return super().get_queryset(request).filter(release_item__isnull=True)

    @admin.display(description="Preview")
    def thumbnail(self, obj):
        return preview(obj)


class ItemInline(admin.TabularInline):
    model = ReleaseItem
    extra = 0
    fields = ["category", "jira_id", "title", "description", "display_order"]
    show_change_link = True
    ordering = ["category", "display_order", "id"]

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        field = super().formfield_for_dbfield(db_field, request, **kwargs)
        if db_field.name == "description":
            field.widget = forms.Textarea(attrs={"rows": 2, "cols": 50})
        elif db_field.name == "title":
            field.widget = forms.TextInput(attrs={"size": 50})
        return field


@admin.register(ReleaseVersion)
class ReleaseVersionAdmin(admin.ModelAdmin):
    list_display = ["version", "release_date", "status", "latest", "planned_label", "change_count", "edited_at"]
    list_filter = ["status", "latest"]
    search_fields = ["version", "description"]
    date_hierarchy = "release_date"
    ordering = ["-release_date"]
    # Latest is always the highest released version number (releases/services/latest.py).
    readonly_fields = ["latest", "edited_at", "created_at", "updated_at"]
    inlines = [ItemInline, GalleryInline]
    fieldsets = [
        (None, {"fields": ["version", "release_date", "status", "planned_label", "latest"]}),
        ("Notes", {"fields": ["description", "highlights", "known_issues", "upgrade_notes"]}),
        ("History", {"classes": ["collapse"], "fields": ["edited_at", "created_at", "updated_at"]}),
    ]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(change_total=Count("items"))

    @admin.display(description="Changes", ordering="change_total")
    def change_count(self, obj):
        return obj.change_total

    def save_model(self, request, obj, form, change):
        if obj.status != "UPCOMING":
            obj.planned_label = None
        super().save_model(request, obj, form, change)
        refresh_latest()
        obj.refresh_from_db(fields=["latest"])

    def delete_model(self, request, obj):
        super().delete_model(request, obj)
        refresh_latest()

    def delete_queryset(self, request, queryset):
        super().delete_queryset(request, queryset)
        refresh_latest()

    def save_related(self, request, form, formsets, change):
        # Items added here go to the end of their category.
        for formset in formsets:
            if formset.model is ReleaseItem:
                for item_form in formset.forms:
                    item = item_form.instance
                    if not item.pk and item_form.has_changed() and not item_form.cleaned_data.get("display_order"):
                        last = form.instance.items.filter(category=item.category).aggregate(m=Max("display_order"))["m"]
                        item_form.instance.display_order = (last or 0) + 1
                        item_form.instance.edited_at = timezone.now()
                    elif item.pk and item_form.has_changed():
                        item_form.instance.edited_at = timezone.now()
        super().save_related(request, form, formsets, change)
        changed = [f.model._meta.verbose_name_plural for f in formsets if f.has_changed()]
        if change and (form.has_changed() or changed):
            fields = ", ".join([*form.changed_data, *changed]) or "details"
            _mark_edited(request, form.instance, f"edited {fields}")
        elif not change:
            record(request, audit.RELEASE_EDIT, request.user, target=str(form.instance), details="admin: created")

    def delete_model(self, request, obj):
        record(request, audit.RELEASE_DELETE, request.user, target=str(obj),
               details=f"admin: deleted with {obj.images.count()} screenshots")
        super().delete_model(request, obj)


class ItemScreenshotInline(GalleryInline):
    fk_name = "release_item"
    verbose_name = "screenshot"
    verbose_name_plural = "Screenshots of this change"

    def get_queryset(self, request):
        return ReleaseImage.objects.filter(release_item__isnull=False)


@admin.register(ReleaseItem)
class ReleaseItemAdmin(admin.ModelAdmin):
    list_display = ["title", "jira_id", "category", "release_version", "display_order", "edited_at"]
    list_display_links = ["title"]
    list_filter = ["category", "release_version"]
    list_select_related = ["release_version"]
    search_fields = ["title", "description", "jira_id", "release_version__version"]
    ordering = ["-release_version__release_date", "category", "display_order"]
    autocomplete_fields = ["release_version"]
    readonly_fields = ["edited_at", "created_at", "updated_at"]
    fieldsets = [
        (None, {"fields": ["release_version", "category", "jira_id", "title", "description", "display_order"]}),
        ("History", {"classes": ["collapse"], "fields": ["edited_at", "created_at", "updated_at"]}),
    ]
    inlines = [ItemScreenshotInline]

    def save_model(self, request, obj, form, change):
        obj.edited_at = timezone.now()
        if not change and not form.cleaned_data.get("display_order"):
            last = ReleaseItem.objects.filter(release_version=obj.release_version, category=obj.category)
            obj.display_order = (last.aggregate(m=Max("display_order"))["m"] or 0) + 1
        super().save_model(request, obj, form, change)

    def save_formset(self, request, form, formset, change):
        # Screenshots of a change belong to its release too.
        for image_form in formset.forms:
            if image_form.has_changed():
                image_form.instance.release_version_id = form.instance.release_version_id
        super().save_formset(request, form, formset, change)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        verb = "edited" if change else "added"
        _mark_edited(request, form.instance.release_version, f"{verb} change {form.instance.label}")

    def delete_model(self, request, obj):
        _mark_edited(request, obj.release_version, f"removed change {obj.label}")
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        for item in queryset.select_related("release_version"):
            _mark_edited(request, item.release_version, f"removed change {item.label}")
        super().delete_queryset(request, queryset)


@admin.register(ReleaseImage)
class ReleaseImageAdmin(admin.ModelAdmin):
    form = ScreenshotForm
    list_display = ["thumbnail", "caption", "release_version", "release_item", "display_order"]
    list_filter = ["release_version"]
    list_select_related = ["release_version", "release_item"]
    search_fields = ["caption", "release_version__version", "release_item__title"]
    autocomplete_fields = ["release_version", "release_item"]
    readonly_fields = ["thumbnail", "file_name", "content_type", "created_at"]
    fields = ["release_version", "release_item", "thumbnail", "upload", "caption", "display_order",
              "file_name", "content_type", "created_at"]

    def get_form(self, request, obj=None, **kwargs):
        kwargs["fields"] = ["release_version", "release_item", "upload", "caption", "display_order"]
        return super().get_form(request, obj, **kwargs)

    @admin.display(description="Preview")
    def thumbnail(self, obj):
        return preview(obj)

    def save_model(self, request, obj, form, change):
        if obj.release_item_id and obj.release_item.release_version_id != obj.release_version_id:
            messages.warning(request, "The screenshot was moved to the release of the change it belongs to.")
            obj.release_version_id = obj.release_item.release_version_id
        super().save_model(request, obj, form, change)
        _mark_edited(request, obj.release_version, "edited a screenshot" if change else "added a screenshot")


@admin.register(ReleaseUpload)
class ReleaseUploadAdmin(admin.ModelAdmin):
    list_display = ["file_name", "release_version", "mode", "item_count", "uploaded_by", "uploaded_at"]
    list_filter = ["mode", "release_version"]
    date_hierarchy = "uploaded_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
