"""Which version is the latest: always the released version with the highest version number, per product.

Upcoming versions never are. Kept in release_version.is_latest, and refreshed after every publish, edit and delete
(and by manage.py setup), so it can't be left on an older version that was uploaded later.
"""
import re

from ..models import ReleaseVersion, Status


def version_key(version: str) -> tuple:
    """Compares part by part, numbers as numbers: 10.10.0 > 10.9.0 > 10.9 > 10.8.5."""
    return tuple((1, int(part), "") if part.isdigit() else (0, 0, part.lower())
                 for part in re.split(r"[._-]+", version) if part)


def refresh_latest(product=None) -> ReleaseVersion | None:
    """Mark the highest released version of the product as its latest and unmark its other versions; without a
    product, do so for every product. Returns the product's latest (None without a product)."""
    if product is None:
        for product_id in ReleaseVersion.objects.values_list("product_id", flat=True).distinct():
            _refresh(ReleaseVersion.objects.filter(product_id=product_id))
        return None
    return _refresh(ReleaseVersion.objects.filter(product=product))


def _refresh(versions) -> ReleaseVersion | None:
    released = versions.exclude(status=Status.UPCOMING).only("id", "version", "release_date")
    latest = max(released, key=lambda r: (version_key(r.version), r.release_date), default=None)
    others = versions.filter(latest=True)
    if latest:
        others = others.exclude(pk=latest.pk)
        ReleaseVersion.objects.filter(pk=latest.pk, latest=False).update(latest=True)
    others.update(latest=False)
    return latest
