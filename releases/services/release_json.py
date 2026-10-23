"""Releases as the JSON the React app reads (the shape python-backend's /api/releases returned).

Used by the API and by the OFBiz package generator, so the packaged viewer shows exactly what the API does.
"""
from django.db.models import Case, IntegerField, Prefetch, Value, When

from ..models import ReleaseImage, ReleaseItem, ReleaseVersion


def image_json(image: ReleaseImage, url: str | None = None) -> dict:
    """contentType tells the page to show a video player (video/mp4, video/webm) instead of an image."""
    return {"id": image.id, "url": url or image.url, "caption": image.caption, "contentType": image.content_type}


def release_json(release: ReleaseVersion, image_url=None) -> dict:
    """image_url(image) -> str overrides screenshot URLs (the OFBiz package serves them as static files)."""
    url = image_url or (lambda image: image.url)
    images = list(release.images.all())
    by_item: dict[int, list[ReleaseImage]] = {}
    for image in images:
        if image.release_item_id is not None:
            by_item.setdefault(image.release_item_id, []).append(image)
    return {
        "id": release.id,
        "version": release.version,
        "releaseDate": release.release_date.isoformat(),
        "description": release.description,
        "isLatest": release.latest,
        "status": release.status,
        "plannedLabel": release.planned_label,
        "highlights": ReleaseVersion.lines(release.highlights),
        "knownIssues": ReleaseVersion.lines(release.known_issues),
        "upgradeNotes": ReleaseVersion.lines(release.upgrade_notes),
        "images": [image_json(i, url(i)) for i in images if i.release_item_id is None],
        "items": [
            {
                "id": item.id,
                "category": item.category,
                "title": item.title,
                "description": item.description,
                "jiraId": item.jira_id,
                "images": [image_json(i, url(i)) for i in by_item.get(item.id, [])],
            }
            for item in release.items.all()
        ],
    }


def releases_queryset():
    """Upcoming releases first, then newest first; items and screenshots in display order."""
    return (
        ReleaseVersion.objects.annotate(
            upcoming=Case(When(status="UPCOMING", then=Value(1)), default=Value(0), output_field=IntegerField())
        )
        .order_by("-upcoming", "-release_date")
        .prefetch_related(
            Prefetch("items", queryset=ReleaseItem.objects.order_by("display_order", "id")),
            Prefetch("images", queryset=ReleaseImage.objects.order_by("display_order", "id")),
        )
    )


def all_releases_json(image_url=None) -> list[dict]:
    return [release_json(r, image_url) for r in releases_queryset()]


def one_release_json(**lookup) -> dict | None:
    release = releases_queryset().filter(**lookup).first()
    return release_json(release) if release else None


def public_release_json(releases: list[dict]) -> list[dict]:
    """The releases as the public page shows them: no Jira numbers, screenshots from the public image URL."""

    def image(i: dict) -> dict:
        return {**i, "url": f"/api/public/release-images/{i['id']}"}

    return [
        {
            **release,
            "images": [image(i) for i in release["images"]],
            "items": [
                {**{k: v for k, v in item.items() if k != "jiraId"}, "images": [image(i) for i in item["images"]]}
                for item in release["items"]
            ],
        }
        for release in releases
    ]
