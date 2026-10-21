from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """Read-only: entries are written by the app, never edited."""

    list_display = ["created_at", "action", "username", "target", "details", "ip_address"]
    list_filter = ["action"]
    search_fields = ["username", "target", "details", "ip_address"]
    date_hierarchy = "created_at"
    list_per_page = 50

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
