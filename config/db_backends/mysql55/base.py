"""Django's MySQL backend, adjusted for the existing MySQL 5.5 server.

Django 6.x supports MySQL 8.0.11+ only. The release-notes database runs on 5.5.62, so this backend
  * lowers the version check to 5.5, and
  * creates DATETIME / TIME columns without fractional seconds, which 5.5 doesn't have
    (this only affects tables Django creates: its own tables and ofbiz_package).
The existing release tables are unmanaged, so Django never alters them.

Remove this backend (ENGINE = "django.db.backends.mysql") once the server is upgraded to MySQL 8.
"""
from django.db.backends.mysql import base, features
from django.utils.functional import cached_property


class DatabaseFeatures(features.DatabaseFeatures):
    minimum_database_version = (5, 5)


class DatabaseWrapper(base.DatabaseWrapper):
    features_class = DatabaseFeatures

    @cached_property
    def data_types(self):
        return {**super().data_types, "DateTimeField": "datetime", "TimeField": "time"}
