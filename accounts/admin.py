from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import AdminPasswordChangeForm
from django.utils import timezone

from audit import models as audit
from audit.service import record

from .models import ADMIN_GROUP_ID, AppUser, AppUserSecurityGroup


def _other_active_admins(user: AppUser) -> int:
    now = timezone.now()
    return (
        AppUserSecurityGroup.objects.filter(group_id=ADMIN_GROUP_ID, from_date__lte=now, user__is_active=True)
        .exclude(thru_date__lte=now).exclude(user_id=user.pk).values("user_id").distinct().count()
    )


class AppUserCreationForm(forms.ModelForm):
    password1 = forms.CharField(label="Password", widget=forms.PasswordInput, min_length=8)
    password2 = forms.CharField(label="Password again", widget=forms.PasswordInput)
    make_admin = forms.BooleanField(label="Admin (FULLADMIN)", required=False)

    class Meta:
        model = AppUser
        fields = ["email", "display_name"]

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip().lower()
        if not email:
            raise forms.ValidationError("New accounts sign in with their email.")
        if AppUser.objects.filter(email=email).exists() or AppUser.objects.filter(username=email).exists():
            raise forms.ValidationError("An account with that email already exists.")
        return email

    def clean(self):
        data = super().clean()
        if data.get("password1") and data.get("password1") != data.get("password2"):
            self.add_error("password2", "The passwords don't match.")
        return data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.username = user.email  # new accounts use their email as the username, like the React sign-up
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
        return user


class AppUserChangeForm(forms.ModelForm):
    class Meta:
        model = AppUser
        fields = ["username", "email", "display_name", "is_active"]

    def clean_email(self):
        return (self.cleaned_data.get("email") or "").strip().lower() or None

    def clean_is_active(self):
        active = self.cleaned_data["is_active"]
        user = self.instance
        if not active and user.pk and user.is_admin and _other_active_admins(user) == 0:
            raise forms.ValidationError("At least one enabled admin must remain.")
        return active


class MembershipFormSet(forms.models.BaseInlineFormSet):
    def clean(self):
        super().clean()
        user = self.instance
        if not user.pk or not user.is_admin or _other_active_admins(user) > 0:
            return
        now = timezone.now()
        keeps_admin = any(
            f.cleaned_data and not f.cleaned_data.get("DELETE") and f.cleaned_data.get("group_id") == ADMIN_GROUP_ID
            and f.cleaned_data.get("from_date") and f.cleaned_data["from_date"] <= now
            and (not f.cleaned_data.get("thru_date") or f.cleaned_data["thru_date"] > now)
            for f in self.forms
        )
        if not keeps_admin:
            raise forms.ValidationError("At least one enabled admin must remain: keep a current FULLADMIN membership.")


class MembershipInline(admin.TabularInline):
    model = AppUserSecurityGroup
    formset = MembershipFormSet
    extra = 0
    fields = ["group_id", "from_date", "thru_date", "current"]
    readonly_fields = ["current"]
    verbose_name_plural = "Access: FULLADMIN = admin (Django Admin, upload, edit, OFBiz packages); JIRA_VIEWER = Jira issues"

    @admin.display(boolean=True, description="Active now")
    def current(self, obj):
        return obj.is_current if obj.pk else None


@admin.register(AppUser)
class AppUserAdmin(UserAdmin):
    form = AppUserChangeForm
    add_form = AppUserCreationForm
    change_password_form = AdminPasswordChangeForm
    list_display = ["username", "email", "display_name", "is_active", "admin_flag", "jira_flag", "last_login", "created_at"]
    list_filter = ["is_active"]
    search_fields = ["username", "email", "display_name"]
    ordering = ["username"]
    filter_horizontal = []
    readonly_fields = ["last_login", "created_at"]
    fieldsets = [
        (None, {"fields": ["username", "password"]}),
        ("Profile", {"fields": ["email", "display_name", "is_active"]}),
        ("History", {"fields": ["last_login", "created_at"]}),
    ]
    add_fieldsets = [(None, {"fields": ["email", "display_name", "password1", "password2", "make_admin"]})]
    inlines = [MembershipInline]

    def get_inlines(self, request, obj):
        return self.inlines if obj else []

    @admin.display(boolean=True, description="Admin")
    def admin_flag(self, obj):
        return obj.is_admin

    @admin.display(boolean=True, description="Jira")
    def jira_flag(self, obj):
        return obj.can_view_jira

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not change:
            if form.cleaned_data.get("make_admin"):
                obj.set_group(ADMIN_GROUP_ID, True)
            record(request, audit.ACCESS_CHANGE, request.user, target=obj.username,
                   details="admin: created account" + (", granted admin" if form.cleaned_data.get("make_admin") else ""))
        elif form.changed_data:
            record(request, audit.ACCESS_CHANGE, request.user, target=obj.username,
                   details="admin: changed " + ", ".join(form.changed_data))

    def save_formset(self, request, form, formset, change):
        super().save_formset(request, form, formset, change)
        if formset.has_changed():
            record(request, audit.ACCESS_CHANGE, request.user, target=form.instance.username,
                   details="admin: changed security groups")

    def has_delete_permission(self, request, obj=None):
        # Disable accounts instead: uploads and the audit log refer to them.
        return False


# Access is FULLADMIN / JIRA_VIEWER on each user (above); Django's own groups aren't used.
from django.contrib.auth.models import Group  # noqa: E402

admin.site.unregister(Group)
