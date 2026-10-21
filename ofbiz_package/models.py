"""History of generated OFBiz packages. New table ofbiz_package (created by Django's migration)."""
from django.conf import settings
from django.db import models
from django.utils import timezone


class OfbizPackage(models.Model):
    file_name = models.CharField(max_length=150, unique=True)
    release_version = models.CharField("latest version", max_length=50)
    generated_at = models.DateTimeField(default=timezone.now)
    # No database constraint: app_user is an existing table Django doesn't manage.
    generated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                     db_constraint=False, related_name="+")
    generated_by_name = models.CharField(max_length=100, blank=True)
    size_bytes = models.BigIntegerField(default=0)
    sha256 = models.CharField("SHA-256", max_length=64)
    version_count = models.IntegerField(default=0)
    item_count = models.IntegerField(default=0)
    image_count = models.IntegerField(default=0)

    class Meta:
        db_table = "ofbiz_package"
        ordering = ["-generated_at", "-id"]
        verbose_name = "OFBiz package"

    def __str__(self):
        return self.file_name

    @property
    def path(self):
        return settings.PACKAGE_DIR / self.file_name
