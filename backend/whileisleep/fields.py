"""Model fields that are encrypted in the database and plain in Python."""

import json

from django.db import models

from . import encryption


class EncryptedTextField(models.TextField):
    """A secret string. Can't be filtered or ordered on: the database only holds ciphertext."""

    def from_db_value(self, value, expression, connection):
        return encryption.decrypt(value) if value else (value or "")

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if not value or encryption.is_encrypted(value):
            return value or ""
        return encryption.encrypt(value)


class EncryptedJSONField(models.TextField):
    """A JSON value (dict or list) whose whole serialized form is a secret."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("default", dict)
        super().__init__(*args, **kwargs)

    def from_db_value(self, value, expression, connection):
        return self.to_python(value)

    def to_python(self, value):
        if isinstance(value, dict | list):
            return value
        text = encryption.decrypt(value) if value else ""
        if not text:
            return self.get_default()
        try:
            return json.loads(text)
        except ValueError:
            return self.get_default()

    def get_prep_value(self, value):
        if isinstance(value, str):
            # Already serialized (a raw ciphertext passed through, or JSON text).
            return value if encryption.is_encrypted(value) else encryption.encrypt(value)
        if not value:
            return ""
        return encryption.encrypt(json.dumps(value, separators=(",", ":"), ensure_ascii=False))

    def value_to_string(self, obj):
        return json.dumps(self.value_from_object(obj))
