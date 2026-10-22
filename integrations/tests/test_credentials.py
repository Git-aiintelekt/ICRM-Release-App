"""Connection settings entered on Settings → Integrations: they win over .env, are encrypted, and tokens never leave."""
from types import SimpleNamespace
from unittest import mock

from django.test import override_settings

from audit import models as audit
from integrations import api, bitbucket_client, credentials, jira_client

from .base import IntegrationTestCase
from .fakes import SECRETS, FakeUser

ADMIN = FakeUser(admin=True)
VIEWER = FakeUser(jira=True)


@override_settings(JIRA_BASE_URL="", JIRA_EMAIL="", JIRA_API_TOKEN="", BITBUCKET_WORKSPACE="", BITBUCKET_EMAIL="",
                   BITBUCKET_API_TOKEN="")
class SavedValuesTests(IntegrationTestCase):
    def test_saved_values_configure_both_services_without_env(self):
        self.assertFalse(jira_client.is_configured())
        self.saved_credentials.update(JIRA_BASE_URL="https://saved.atlassian.net", JIRA_EMAIL="me@example.test",
                                      JIRA_API_TOKEN="saved-token", BITBUCKET_WORKSPACE="saved-ws",
                                      BITBUCKET_EMAIL="me@example.test", BITBUCKET_API_TOKEN="bb-saved")
        self.assertTrue(jira_client.is_configured())
        self.assertEqual(jira_client.browse_url("CS-1"), "https://saved.atlassian.net/browse/CS-1")
        self.assertTrue(bitbucket_client.is_configured())
        self.assertEqual(credentials.source("JIRA_API_TOKEN"), "app")
        self.assertIsNone(credentials.source("BITBUCKET_ACCESS_TOKEN"))

    @override_settings(JIRA_EMAIL="env@example.test")
    def test_saved_value_wins_over_env_and_removing_it_falls_back(self):
        self.assertEqual((credentials.get("JIRA_EMAIL"), credentials.source("JIRA_EMAIL")), ("env@example.test", "env"))
        self.saved_credentials["JIRA_EMAIL"] = "app@example.test"
        self.assertEqual((credentials.get("JIRA_EMAIL"), credentials.source("JIRA_EMAIL")), ("app@example.test", "app"))


class EncryptionTests(IntegrationTestCase):
    def setUp(self):
        super().setUp()
        mock.patch.stopall()  # the real stored(), reading mocked rows
        self.addCleanup(credentials.forget)
        credentials.forget()

    def rows(self, *rows):
        return mock.patch("integrations.credentials.IntegrationCredential.objects.all", return_value=list(rows)).start()

    @override_settings(APP_SECRET_KEY="key-one")
    def test_round_trip_and_values_are_not_stored_in_clear(self):
        token = credentials._fernet().encrypt(b"my-token").decode()
        self.assertNotIn("my-token", token)
        self.rows(SimpleNamespace(name="JIRA_API_TOKEN", encrypted_value=token))
        self.assertEqual(credentials.stored(), {"JIRA_API_TOKEN": "my-token"})

    def test_value_encrypted_with_another_key_is_skipped(self):
        with override_settings(APP_SECRET_KEY="old-key"):
            token = credentials._fernet().encrypt(b"my-token").decode()
        with override_settings(APP_SECRET_KEY="new-key"), self.assertLogs("integrations.credentials", "WARNING"):
            self.rows(SimpleNamespace(name="JIRA_API_TOKEN", encrypted_value=token))
            self.assertEqual(credentials.stored(), {})


class CredentialsApiTests(IntegrationTestCase):
    def setUp(self):
        super().setUp()
        self.save = mock.patch("integrations.credentials.save", return_value=["JIRA_API_TOKEN"]).start()

    def put(self, data, user=ADMIN):
        return self.call(api.credentials_settings, user, method="put", data=data)

    def test_admins_only(self):
        self.assertEqual(self.call(api.credentials_settings, None).status_code, 401)
        self.assertEqual(self.call(api.credentials_settings, VIEWER).status_code, 403)
        self.assertEqual(self.put({"jiraApiToken": "x"}, user=VIEWER).status_code, 403)
        self.save.assert_not_called()

    def test_tokens_are_never_sent_back(self):
        self.saved_credentials["JIRA_API_TOKEN"] = "app-token-789"
        fields = {f["name"]: f for f in self.call(api.credentials_settings, ADMIN).data["fields"]}
        self.assertEqual(fields["JIRA_API_TOKEN"], {"name": "JIRA_API_TOKEN", "label": "Jira API token", "secret": True,
                                                    "source": "app", "value": None})
        self.assertEqual(fields["JIRA_BASE_URL"]["value"], "https://jira.test")
        text = str(fields)
        for secret in SECRETS + ("app-token-789",):
            self.assertNotIn(secret, text)

    def test_save_passes_only_given_fields_and_audits_names_not_values(self):
        response = self.put({"jiraApiToken": "new-token", "jiraBaseUrl": "https://x.atlassian.net/", "jiraEmail": ""})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.save.call_args.args[0], {"JIRA_API_TOKEN": "new-token",
                                                       "JIRA_BASE_URL": "https://x.atlassian.net", "JIRA_EMAIL": ""})
        self.assertEqual(self.audit.call_args.args[1], audit.INTEGRATION_SETTINGS)
        self.assertEqual(self.audit.call_args.kwargs["details"], "changed JIRA_API_TOKEN")
        self.assertNotIn("new-token", str(self.audit.call_args))

    def test_invalid_values_are_refused(self):
        response = self.put({"jiraBaseUrl": "http://plain-http.test", "jiraEmail": "nope",
                             "bitbucketWorkspace": "a b", "jiraApiToken": "has space"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(set(response.data["errors"]), {"jiraBaseUrl", "jiraEmail", "bitbucketWorkspace", "jiraApiToken"})
        self.save.assert_not_called()
