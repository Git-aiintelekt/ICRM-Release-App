"""Which version is the latest: always the released version with the highest version number.

Upcoming versions never are. Kept in release_version.is_latest, and refreshed after every publish, edit and delete
(and by manage.py setup), so it can't be left on an older version that was uploaded later.
"""
import re

from ..models import ReleaseVersion, Status


def version_key(version: str) -> tuple:
    """Compares part by part, numbers as numbers: 10.10.0 > 10.9.0 > 10.9 > 10.8.5."""
    return tuple((1, int(part), "") if part.isdigit() else (0, 0, part.lower())
                 for part in re.split(r"[._-]+", version) if part)


def refresh_latest() -> ReleaseVersion | None:
    """Mark the highest released version as the latest and unmark every other one. Returns the latest."""
    released = ReleaseVersion.objects.exclude(status=Status.UPCOMING).only("id", "version", "release_date")
    latest = max(released, key=lambda r: (version_key(r.version), r.release_date), default=None)
    others = ReleaseVersion.objects.filter(latest=True)
    if latest:
        others = others.exclude(pk=latest.pk)
        ReleaseVersion.objects.filter(pk=latest.pk, latest=False).update(latest=True)
    others.update(latest=False)
    return latest
