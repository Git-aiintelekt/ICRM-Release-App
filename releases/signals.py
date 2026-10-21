"""Remove a screenshot's file once its row is deleted (directly, or with its item or release)."""
from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import ReleaseImage
from .services import image_store


@receiver(post_delete, sender=ReleaseImage)
def delete_image_file(sender, instance, **kwargs):
    file_name = instance.file_name
    transaction.on_commit(lambda: image_store.delete(file_name))
