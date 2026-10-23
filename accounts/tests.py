"""Sign-in tokens, revocation, rate limits, lockout and sign-up rules (no database: queries are mocked)."""
import time
from unittest import mock

from django.core.cache import cache
from django.test import SimpleTestCase, override_settings
from rest_framework.test import APIRequestFactory, force_authenticate

from integrations.tests.fakes import FakeUser

from . import api, tokens
from .models import AppUser

# Through accounts.api: importing config.api first would load it before DRF's views (a circular import).
LoginThrottle, RegisterThrottle = api.LoginThrottle, api.RegisterThrottle


@override_settings(APP_SECRET_KEY="test-secret", TOKEN_TTL_SECONDS=3600)
class TokenTests(SimpleTestCase):
    def setUp(self):
        self.cutoff = mock.patch("accounts.tokens._cutoff", return_value=0.0).start()
        self.revoked = mock.patch("accounts.tokens._jti_revoked", return_value=False).start()
        self.addCleanup(mock.patch.stopall)

    def test_round_trip(self):
        self.assertEqual(tokens.read_token(tokens.create_token(42)), 42)

    def test_tampered_token_is_refused(self):
        body, signature = tokens.create_token(42).split(".")
        forged = tokens._b64(b'{"sub": 1, "exp": 9999999999}')
        self.assertIsNone(tokens.read_token(f"{forged}.{signature}"))
        self.assertIsNone(tokens.read_token("not-a-token"))

    @override_settings(TOKEN_TTL_SECONDS=-10)
    def test_expired_token_is_refused(self):
        self.assertIsNone(tokens.read_token(tokens.create_token(42)))

    def test_signed_out_token_is_refused(self):
        token = tokens.create_token(42)
        self.revoked.return_value = True
        self.assertIsNone(tokens.read_token(token))

    def test_token_issued_before_cutoff_is_refused(self):
        token = tokens.create_token(42)
        self.cutoff.return_value = time.time() + 1
        self.assertIsNone(tokens.read_token(token))
        self.cutoff.return_value = time.time() - 60
        self.assertEqual(tokens.read_token(token), 42)

    def test_python_backend_token_counts_as_issued_at_zero(self):
        legacy = tokens._sign({"sub": 42, "exp": int(time.time()) + 60}, tokens._session_key())
        self.assertEqual(tokens.read_token(legacy), 42)
        self.cutoff.return_value = 1.0
        self.assertIsNone(tokens.read_token(legacy))

    def test_reset_token_is_not_a_sign_in_token(self):
        user = AppUser(pk=42, username="a@b.test", password="pbkdf2$hash")
        self.assertIsNone(tokens.read_token(tokens.create_reset_token(user)))

    def test_revoke_token_stores_its_jti_until_expiry(self):
        objects = mock.patch("accounts.tokens.RevokedToken.objects").start()
        token = tokens.create_token(42)
        self.assertTrue(tokens.revoke_token(token))
        kwargs = objects.update_or_create.call_args.kwargs
        self.assertEqual(len(kwargs["pk"]), 32)
        self.assertGreater(kwargs["defaults"]["expires_at"], time.time())
        self.assertFalse(tokens.revoke_token("garbage"))


class PasswordChangeRevokesTokensTests(SimpleTestCase):
    def setUp(self):
        mock.patch("django.contrib.auth.base_user.AbstractBaseUser.save").start()
        self.revoke_all = mock.patch("accounts.tokens.revoke_all_tokens").start()
        self.addCleanup(mock.patch.stopall)

    def test_changed_password_ends_earlier_sign_ins(self):
        user = AppUser(pk=5, username="a@b.test")
        user.set_password("new password 123")
        user.save()
        self.revoke_all.assert_called_once_with(5)

    def test_other_saves_and_new_users_do_not(self):
        AppUser(pk=5, username="a@b.test").save()
        new = AppUser(username="new@b.test")
        new.set_password("first password 1")
        new.save()
        self.revoke_all.assert_not_called()


class AuthApiTestCase(SimpleTestCase):
    factory = APIRequestFactory()

    def setUp(self):
        cache.clear()
        self.audit = mock.patch("accounts.api.record").start()
        mock.patch("accounts.api._find_user", return_value=None).start()
        self.addCleanup(mock.patch.stopall)

    def post(self, view, data=None, user=None, token=None, ip="10.0.0.1"):
        request = self.factory.post("/api/x", data or {}, format="json", REMOTE_ADDR=ip)
        if user is not None:
            force_authenticate(request, user=user, token=token)
        return view(request)


@override_settings(LOGIN_LOCKOUT_ATTEMPTS=3, LOGIN_LOCKOUT_SECONDS=900)
class LoginLimitTests(AuthApiTestCase):
    def setUp(self):
        super().setUp()
        self.authenticate = mock.patch("accounts.api.EmailOrUsernameBackend.authenticate", return_value=None).start()
        mock.patch.object(LoginThrottle, "THROTTLE_RATES", {"login": "1000/min"}).start()

    def login(self, email="victim@aiintelekt.com", ip="10.0.0.1"):
        return self.post(api.login, {"email": email, "password": "guess"}, ip=ip)

    def test_account_locks_after_repeated_failures_from_any_ip(self):
        for n in range(3):
            self.assertEqual(self.login(ip=f"10.0.0.{n}").status_code, 401)
        self.assertEqual(self.login(ip="10.9.9.9").status_code, 429)
        self.assertEqual(self.authenticate.call_count, 3)  # the locked attempt never checks the password
        self.assertIn("locked", self.audit.call_args.kwargs["details"])

    def test_lock_is_per_account(self):
        for _ in range(3):
            self.login()
        self.assertEqual(self.login(email="someone-else@aiintelekt.com").status_code, 401)

    def test_successful_sign_in_clears_the_failures(self):
        self.login()
        self.login()
        user = mock.Mock()
        self.authenticate.return_value = user
        with mock.patch("accounts.api._start_session", return_value={"token": "t"}):
            self.assertEqual(self.login().status_code, 200)
        self.authenticate.return_value = None
        self.login()
        self.login()
        self.assertEqual(self.login().status_code, 401)  # counting started again

    def test_ip_rate_limit(self):
        mock.patch.object(LoginThrottle, "THROTTLE_RATES", {"login": "2/min"}).start()
        statuses = [self.login(email=f"user{n}@aiintelekt.com").status_code for n in range(3)]
        self.assertEqual(statuses, [401, 401, 429])
        self.assertEqual(self.login(email="other@aiintelekt.com", ip="10.0.0.2").status_code, 401)

    def test_forwarded_for_header_is_ignored_without_proxies(self):
        mock.patch.object(LoginThrottle, "THROTTLE_RATES", {"login": "1/min"}).start()
        self.login()
        request = self.factory.post("/api/x", {"email": "x@y.test", "password": "p"}, format="json",
                                    REMOTE_ADDR="10.0.0.1", HTTP_X_FORWARDED_FOR="1.2.3.4")
        self.assertEqual(api.login(request).status_code, 429)


class RegistrationRuleTests(AuthApiTestCase):
    def setUp(self):
        super().setUp()
        mock.patch.object(RegisterThrottle, "THROTTLE_RATES", {"register": "1000/hour"}).start()
        self.exists = mock.patch("accounts.api.AppUser.objects").start()

    def register(self, email):
        return self.post(api.register, {"email": email, "password": "long enough 1"})

    @override_settings(ALLOW_REGISTRATION=False)
    def test_closed_sign_up(self):
        self.assertEqual(self.register("new@aiintelekt.com").status_code, 403)
        self.exists.filter.assert_not_called()

    @override_settings(ALLOW_REGISTRATION=True, REGISTRATION_EMAIL_DOMAINS=["aiintelekt.com"])
    def test_other_domains_are_refused(self):
        response = self.register("someone@gmail.com")
        self.assertEqual(response.status_code, 400)
        self.assertIn("@aiintelekt.com", response.data["detail"])
        self.assertEqual(self.register("someone@evil-aiintelekt.com").status_code, 400)

    @override_settings(ALLOW_REGISTRATION=True, REGISTRATION_EMAIL_DOMAINS=["aiintelekt.com"], PUBLIC_RELEASE_NOTES=False)
    def test_options_tell_the_sign_in_page(self):
        response = api.auth_options(self.factory.get("/api/auth/options"))
        self.assertEqual(response.data, {"registrationOpen": True, "registrationDomains": ["aiintelekt.com"],
                                         "publicReleaseNotes": False})


class LogoutTests(AuthApiTestCase):
    def setUp(self):
        super().setUp()
        mock.patch("accounts.api.django_logout").start()
        self.revoke = mock.patch("accounts.api.revoke_token").start()
        self.revoke_all = mock.patch("accounts.api.revoke_all_tokens").start()

    def test_logout_revokes_this_token(self):
        self.assertEqual(self.post(api.logout, user=FakeUser(), token="this-token").status_code, 204)
        self.revoke.assert_called_once_with("this-token")

    def test_logout_without_a_token_still_succeeds(self):
        self.assertEqual(self.post(api.logout).status_code, 204)
        self.revoke.assert_not_called()

    def test_logout_everywhere(self):
        self.assertEqual(self.post(api.logout_everywhere, user=FakeUser(id=9), token="t").status_code, 204)
        self.revoke_all.assert_called_once_with(9)
        self.assertEqual(self.post(api.logout_everywhere).status_code, 401)


class ChangePasswordTests(AuthApiTestCase):
    def setUp(self):
        super().setUp()
        mock.patch.object(api.PasswordResetThrottle, "THROTTLE_RATES", {"password_reset": "1000/hour"}).start()
        self.required = mock.patch("accounts.api.PasswordChangeRequired.objects").start()
        mock.patch("accounts.api._start_session", return_value={"token": "new"}).start()
        mock.patch("accounts.api.transaction.atomic").start()
        self.user = mock.Mock(id=3, is_authenticated=True, check_password=lambda raw: raw == "admin")

    def change(self, current, new):
        return self.post(api.change_password, {"currentPassword": current, "newPassword": new}, user=self.user)

    def test_wrong_current_password_or_short_new_one_is_refused(self):
        self.assertEqual(self.change("guess", "a new password").status_code, 400)
        self.assertEqual(self.change("admin", "short").status_code, 400)
        self.user.set_password.assert_not_called()

    def test_change_clears_the_requirement_and_signs_in_again(self):
        response = self.change("admin", "a new password")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {"token": "new"})
        self.user.set_password.assert_called_once_with("a new password")
        self.required.filter.assert_called_once_with(user_id=3)
        self.assertEqual(self.audit.call_args.args[1], "PASSWORD_CHANGE")

    def test_signed_out_gets_401(self):
        self.assertEqual(self.post(api.change_password, {"currentPassword": "a", "newPassword": "b" * 8}).status_code, 401)


class PasswordChangeGateTests(SimpleTestCase):
    """A user who must change their password reaches only the endpoints needed to do it."""

    def setUp(self):
        from .authentication import BearerTokenAuthentication
        self.auth = BearerTokenAuthentication()
        mock.patch("accounts.authentication.read_token", return_value=3).start()
        self.user = mock.Mock(is_active=True, must_change_password=True)
        mock.patch("accounts.authentication.AppUser.objects.filter").start().return_value.first.return_value = self.user
        self.addCleanup(mock.patch.stopall)

    def authenticate(self, path):
        return self.auth.authenticate(APIRequestFactory().get(path, HTTP_AUTHORIZATION="Bearer t"))

    def test_only_the_password_change_endpoints_are_open(self):
        for path in ("/api/auth/me", "/api/auth/change-password", "/api/auth/logout"):
            self.assertEqual(self.authenticate(path), (self.user, "t"))
        from rest_framework.exceptions import PermissionDenied
        for path in ("/api/releases", "/api/admin/users", "/api/integrations/credentials"):
            with self.assertRaises(PermissionDenied):
                self.authenticate(path)

    def test_everything_is_open_after_the_change(self):
        self.user.must_change_password = False
        self.assertEqual(self.authenticate("/api/admin/users"), (self.user, "t"))
