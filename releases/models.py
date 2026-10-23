"""Release notes on the existing release_* tables (unmanaged: Django never alters them)."""
import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone


class Category(models.TextChoices):
    NEW_FEATURE = "NEW_FEATURE", "New feature"
    IMPROVEMENT = "IMPROVEMENT", "Improvement"
    BUG_FIX = "BUG_FIX", "Bug fix"
    SECURITY = "SECURITY", "Security"


CATEGORY_ORDER = [c.value for c in Category]


class Status(models.TextChoices):
    RELEASED = "RELEASED", "Released"
    UPCOMING = "UPCOMING", "Coming soon"


def new_public_key() -> str:
    """16 random URL-safe characters: a public link that can't be guessed from another one."""
    return secrets.token_urlsafe(12)


class Product(models.Model):
    """A product with its own release notes (iCRM, IUC, Sales Audit, ...), or a client of one (parent = the product):
    IUC's clients each have their own repositories, branches and versions. New table release_product.
    Its Bitbucket repositories are ProductRepository rows; every screen follows the product / client picked in the
    header. A product's own rows (no client picked) are the ones all its clients share."""

    id = models.BigAutoField(primary_key=True)
    parent = models.ForeignKey("self", on_delete=models.PROTECT, null=True, blank=True, related_name="clients")
    name = models.CharField(max_length=50)
    # The public release notes link: /public/release-notes/<public_key>. A new key makes the old link stop working.
    public_key = models.CharField(max_length=24, unique=True, default=new_public_key, editable=False)
    display_order = models.IntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        db_table = "release_product"
        ordering = ["display_order", "id"]
        constraints = [models.UniqueConstraint(fields=["parent", "name"], name="release_product_parent_name_unique")]

    def __str__(self):
        return self.label

    @property
    def label(self) -> str:
        """"IUC – Client A" for a client, the name for a product."""
        return f"{self.parent.name} – {self.name}" if self.parent_id else self.name


class ProductRepository(models.Model):
    """A Bitbucket repository (slug) of a product. One repository can belong to several products (a shared framework)."""

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="repositories")
    repository = models.CharField(max_length=100)

    class Meta:
        db_table = "release_product_repository"
        ordering = ["product", "repository"]
        constraints = [models.UniqueConstraint(fields=["product", "repository"], name="release_product_repository_unique")]

    def __str__(self):
        return f"{self.product}: {self.repository}"


class ReleaseVersion(models.Model):
    id = models.BigAutoField(primary_key=True)
    # Added to the existing table by releases/0002 (product_id, unique together with version).
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="releases", db_column="product_id",
                                db_constraint=False)
    version = models.CharField(max_length=50)
    release_date = models.DateField()
    description = models.CharField("summary", max_length=1000, blank=True)
    latest = models.BooleanField("latest", default=False, db_column="is_latest",
                                 help_text="Only one version is the latest; marking this one unmarks the others.")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RELEASED)
    planned_label = models.CharField(max_length=100, null=True, blank=True,
                                     help_text='Upcoming releases only, e.g. "October 2026".')
    # One entry per line.
    highlights = models.TextField(null=True, blank=True, help_text="One per line.")
    known_issues = models.TextField(null=True, blank=True, help_text="One per line.")
    upgrade_notes = models.TextField(null=True, blank=True, help_text="One per line.")
    # Set when an admin edits the release; the seed rebuild refuses to overwrite it.
    edited_at = models.DateTimeField(null=True, blank=True, editable=False)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        managed = False
        db_table = "release_version"
        ordering = ["-release_date"]
        verbose_name = "release version"
        unique_together = [("product", "version")]

    def __str__(self):
        return f"{self.product.label} {self.version}" if self.product_id else f"Version {self.version}"

    def save(self, *args, **kwargs):
        self.updated_at = timezone.now()
        super().save(*args, **kwargs)

    @staticmethod
    def lines(text: str | None) -> list[str]:
        return [line.strip() for line in (text or "").splitlines() if line.strip()]


class ReleaseItem(models.Model):
    id = models.BigAutoField(primary_key=True)
    release_version = models.ForeignKey(ReleaseVersion, on_delete=models.CASCADE, related_name="items",
                                        db_column="release_version_id")
    category = models.CharField(max_length=50, choices=Category.choices)
    title = models.CharField(max_length=500)
    description = models.CharField(max_length=1000, null=True, blank=True)
    jira_id = models.CharField("Jira ID", max_length=20, null=True, blank=True)
    display_order = models.IntegerField(default=0)
    edited_at = models.DateTimeField(null=True, blank=True, editable=False)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        managed = False
        db_table = "release_item"
        ordering = ["display_order", "id"]
        verbose_name = "release item"

    def __str__(self):
        return f"{self.jira_id}: {self.title}" if self.jira_id else self.title

    def save(self, *args, **kwargs):
        self.updated_at = timezone.now()
        super().save(*args, **kwargs)

    @property
    def label(self) -> str:
        return self.jira_id or self.title[:60]


class ReleaseImage(models.Model):
    """A screenshot; the file is <UPLOAD_DIR>/release-images/<file_name>."""

    id = models.BigAutoField(primary_key=True)
    release_version = models.ForeignKey(ReleaseVersion, on_delete=models.CASCADE, related_name="images",
                                        db_column="release_version_id")
    # Null for release-level screenshots (the gallery); set for screenshots of one change.
    release_item = models.ForeignKey(ReleaseItem, on_delete=models.CASCADE, null=True, blank=True,
                                     related_name="images", db_column="release_item_id")
    file_name = models.CharField(max_length=100, editable=False)
    content_type = models.CharField(max_length=50, editable=False)
    caption = models.CharField(max_length=255, null=True, blank=True)
    display_order = models.IntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        managed = False
        db_table = "release_image"
        ordering = ["display_order", "id"]
        verbose_name = "screenshot"

    def __str__(self):
        return self.caption or self.file_name

    @property
    def url(self) -> str:
        return f"/api/release-images/{self.id}"


class ReleaseUpload(models.Model):
    """Every Word document an admin published."""

    release_version = models.ForeignKey(ReleaseVersion, on_delete=models.CASCADE, related_name="uploads",
                                        db_column="release_version_id")
    file_name = models.CharField(max_length=255)
    item_count = models.IntegerField()
    mode = models.CharField(max_length=20)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+",
                                    db_column="uploaded_by")
    uploaded_at = models.DateTimeField(default=timezone.now)

    class Meta:
        managed = False
        db_table = "release_upload"
        ordering = ["-uploaded_at"]
        verbose_name = "Word document upload"

    def __str__(self):
        return self.file_name
