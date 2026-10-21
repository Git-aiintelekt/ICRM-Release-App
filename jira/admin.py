from django import forms
from django.contrib import admin
from django.db.models import Count

from .models import JiraIssue, JiraSeedEntry, JiraTableEntry


class SeedInline(admin.StackedInline):
    model = JiraSeedEntry
    extra = 0
    fields = [("type", "seed_ref", "display_order"), "content"]
    classes = ["collapse"]


class TableInline(admin.StackedInline):
    model = JiraTableEntry
    extra = 0
    fields = [("type", "table_name", "display_order"), ("primary_key_field", "primary_key_value"),
              ("name_description", "seed_ref"), "content"]
    classes = ["collapse"]


@admin.register(JiraIssue)
class JiraIssueAdmin(admin.ModelAdmin):
    list_display = ["jira_id", "description", "seed_total", "table_total", "updated_at"]
    search_fields = ["jira_id", "description"]
    readonly_fields = ["created_at", "updated_at"]
    fields = ["jira_id", "description", "link", "created_at", "updated_at"]
    inlines = [SeedInline, TableInline]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(seed_n=Count("seeds", distinct=True), table_n=Count("tables", distinct=True))

    @admin.display(description="Seeds", ordering="seed_n")
    def seed_total(self, obj):
        return obj.seed_n

    @admin.display(description="Tables", ordering="table_n")
    def table_total(self, obj):
        return obj.table_n

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        field = super().formfield_for_dbfield(db_field, request, **kwargs)
        if db_field.name == "description":
            field.widget = forms.Textarea(attrs={"rows": 3, "cols": 80})
        return field
