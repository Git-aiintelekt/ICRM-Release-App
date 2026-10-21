"""Users on the existing app_user / app_user_security_group tables (unmanaged: Django never alters them).

Admin rights follow iCRM/OFBiz: a user is an admin while they hold an active (from_date <= now < thru_date)
FULLADMIN membership, the same rule as UserLoginSecurityGroup ... filterByDate(). FULLADMIN members can open
Django Admin and have every permission there.
"""
from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone

ADMIN_GROUP_ID = "FULLADMIN"
JIRA_VIEWER_GROUP_ID = "JIRA_VIEWER"
GROUP_CHOICES = [(ADMIN_GROUP_ID, "Admin (FULLADMIN)"), (JIRA_VIEWER_GROUP_ID, "Jira viewer (JIRA_VIEWER)")]


class AppUserManager(BaseUserManager):
    def create_user(self, username, password=None, *, email=None, display_name=None, is_admin=False):
        email = self.normalize_email(email).lower() if email else None
        user = self.model(username=username.strip().lower(), email=email, display_name=display_name or None)
        user.set_password(password)
        with transaction.atomic():
            user.save(using=self._db)
            if is_admin:
                user.set_group(ADMIN_GROUP_ID, True)
        return user

    def create_superuser(self, username, password=None, **extra):
        extra.setdefault("email", username if "@" in username else None)
        return self.create_user(username, password, is_admin=True, **extra)


class AppUser(AbstractBaseUser):
    username = models.CharField(max_length=100, unique=True)
    email = models.EmailField(max_length=191, unique=True, null=True, blank=True)
    display_name = models.CharField(max_length=150, null=True, blank=True)
    # Column names differ from Django's defaults; the data and hash format are unchanged.
    password = models.CharField("password", max_length=255, db_column="password_hash")
    is_active = models.BooleanField("enabled", default=True, db_column="is_enabled")
    last_login = models.DateTimeField("last sign-in", null=True, blank=True, db_column="last_login_at")
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    objects = AppUserManager()

    USERNAME_FIELD = "username"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        managed = False
        db_table = "app_user"
        ordering = ["username"]
        verbose_name = "user"

    def __str__(self):
        return self.email or self.username

    # ---- security groups ----

    def active_groups(self) -> set[str]:
        if not self.pk:
            return set()
        now = timezone.now()
        return set(
            self.security_groups.filter(Q(thru_date__isnull=True) | Q(thru_date__gt=now), from_date__lte=now)
            .values_list("group_id", flat=True)
        )

    @property
    def is_admin(self) -> bool:
        return ADMIN_GROUP_ID in self.active_groups()

    @property
    def can_view_jira(self) -> bool:
        return bool(self.active_groups() & {ADMIN_GROUP_ID, JIRA_VIEWER_GROUP_ID})

    def set_group(self, group_id: str, member: bool) -> bool:
        """Grant (new row) or revoke (set thru_date), like OFBiz UserLoginSecurityGroup. True if changed."""
        now = timezone.now()
        active = self.security_groups.filter(
            Q(thru_date__isnull=True) | Q(thru_date__gt=now), group_id=group_id, from_date__lte=now
        )
        if member and not active.exists():
            AppUserSecurityGroup.objects.create(user=self, group_id=group_id, from_date=now)
            return True
        if not member and active.exists():
            active.update(thru_date=now)
            return True
        return False

    def save(self, *args, **kwargs):
        # set_password() leaves the new raw password in _password until the save: a changed password
        # (reset link, Django Admin, changepassword) ends every sign-in token issued before it.
        password_changed = self._password is not None and self.pk is not None
        super().save(*args, **kwargs)
        if password_changed:
            from .tokens import revoke_all_tokens
            revoke_all_tokens(self.pk)

    # ---- Django Admin access: FULLADMIN members only, with every permission ----

    @property
    def is_staff(self) -> bool:
        return self.is_active and self.is_admin

    @property
    def is_superuser(self) -> bool:
        return self.is_staff

    def has_perm(self, perm, obj=None) -> bool:
        return self.is_staff

    def has_perms(self, perm_list, obj=None) -> bool:
        return self.is_staff

    def has_module_perms(self, app_label) -> bool:
        return self.is_staff


class AppUserSecurityGroup(models.Model):
    user = models.ForeignKey(AppUser, on_delete=models.CASCADE, related_name="security_groups", db_column="user_id")
    group_id = models.CharField("group", max_length=50, choices=GROUP_CHOICES)
    from_date = models.DateTimeField(default=timezone.now)
    thru_date = models.DateTimeField(null=True, blank=True, help_text="Leave empty for no end date.")

    class Meta:
        managed = False
        db_table = "app_user_security_group"
        ordering = ["-from_date"]
        verbose_name = "security group membership"

    def __str__(self):
        return f"{self.group_id} for {self.user}"

    @property
    def is_current(self) -> bool:
        now = timezone.now()
        return self.from_date <= now and (self.thru_date is None or self.thru_date > now)


# ---- Sign-in token revocation: new tables, created by Django's migration (app_user itself stays unaltered) ----

class UserTokenCutoff(models.Model):
    """Sign-in tokens of this user issued before `not_before` are refused: set on a password change,
    when an admin disables the account, and by "sign out everywhere"."""
    user = models.OneToOneField(AppUser, on_delete=models.CASCADE, primary_key=True, db_constraint=False,
                                related_name="+", db_column="user_id")
    not_before = models.FloatField(help_text="Unix time; tokens issued earlier are refused.")

    class Meta:
        db_table = "user_token_cutoff"
        verbose_name = "sign-in token cutoff"


class RevokedToken(models.Model):
    """One signed-out token (its jti), kept until the token would have expired anyway."""
    jti = models.CharField(max_length=32, primary_key=True)
    expires_at = models.FloatField(db_index=True)

    class Meta:
        db_table = "revoked_token"
        verbose_name = "revoked sign-in token"
