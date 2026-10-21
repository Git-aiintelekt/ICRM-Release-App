"""PBKDF2-SHA256 in the python-backend format: pbkdf2_sha256$<iterations>$<salt>$<hex digest>.

Django's own PBKDF2 hasher uses the same prefix but a base64 digest, so it can't check these hashes.
This one writes the python-backend format, so a password set in either app works in both.
"""
import hashlib
import hmac
import secrets

from django.contrib.auth.hashers import BasePasswordHasher, mask_hash
from django.utils.translation import gettext_noop as _


class LegacyPBKDF2Hasher(BasePasswordHasher):
    algorithm = "pbkdf2_sha256"
    iterations = 390_000

    def salt(self):
        return secrets.token_hex(16)

    def encode(self, password, salt, iterations=None):
        iterations = iterations or self.iterations
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), iterations).hex()
        return f"{self.algorithm}${iterations}${salt}${digest}"

    def decode(self, encoded):
        algorithm, iterations, salt, digest = encoded.split("$", 3)
        return {"algorithm": algorithm, "iterations": int(iterations), "salt": salt, "hash": digest}

    def verify(self, password, encoded):
        try:
            parts = self.decode(encoded)
        except ValueError:
            return False
        candidate = self.encode(password, parts["salt"], parts["iterations"])
        return hmac.compare_digest(candidate.encode(), encoded.encode())

    def safe_summary(self, encoded):
        parts = self.decode(encoded)
        return {_("algorithm"): parts["algorithm"], _("iterations"): parts["iterations"],
                _("salt"): mask_hash(parts["salt"]), _("hash"): mask_hash(parts["hash"])}

    def must_update(self, encoded):
        return False

    def harden_runtime(self, password, encoded):
        pass
