"""The product a request is about: the X-Product header the React app sends with every call (the product picked in
the header), or ?product=<id>. Neither: the first product. Release notes, and the repositories every integration
screen shows, are those of this product.

The public page never names a product by id (ids are easy to guess): it sends the product's public key from its link,
/public/release-notes/<key> (from_public_request)."""
import re

from rest_framework import exceptions, serializers

from .models import Product, ProductRepository

HEADER = "X-Product"
PUBLIC_KEY_RE = re.compile(r"^[A-Za-z0-9_-]{8,24}$")


def products() -> list[Product]:
    """Products and their clients, in display order (the page builds the tree from parentId)."""
    return list(Product.objects.select_related("parent"))


def from_request(request) -> Product:
    value = (request.headers.get(HEADER) or request.query_params.get("product") or "").strip()
    if value:
        product = Product.objects.select_related("parent").filter(pk=value).first() if value.isdigit() else None
        if product is None:
            raise serializers.ValidationError({"product": "No such product. Reload the page to see the current list."})
        return product
    product = Product.objects.filter(parent__isnull=True).first()
    if product is None:
        raise serializers.ValidationError({"product": "No product exists. An admin adds one on Settings → Products."})
    return product


def from_public_request(request) -> Product:
    """?key=<public key>: that product or client. No key: the first product, so the original link
    (/public/release-notes) keeps working. Anything else is a 404, the same as a key that doesn't exist."""
    key = (request.query_params.get("key") or "").strip()
    if not key:
        product = Product.objects.filter(parent__isnull=True).first()
    else:
        product = Product.objects.select_related("parent").filter(public_key=key).first() if PUBLIC_KEY_RE.match(key) else None
    if product is None:
        raise exceptions.NotFound("These release notes were not found. Ask for a new link.")
    return product


def repository_slugs(product: Product) -> list[str]:
    """The repositories linked to the product (whether or not they're still in the app's repository list)."""
    return list(ProductRepository.objects.filter(product=product).values_list("repository", flat=True))


def product_json(product: Product, admin: bool = False) -> dict:
    """label: "IUC – Client A" for a client (parentId set), the name for a product. publicKey (its public link) for
    admins only: they share the links."""
    body = {"id": product.id, "name": product.name, "parentId": product.parent_id, "label": product.label}
    if admin:
        body["publicKey"] = product.public_key
    return body
