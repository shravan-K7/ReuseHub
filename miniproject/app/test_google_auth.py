"""
Unit and integration tests for Google OAuth 2.0 and django-allauth in ReuseHub.
"""
from unittest.mock import MagicMock
from urllib.parse import parse_qs, urlparse

from allauth.account.models import EmailAddress
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import get_adapter
from allauth.socialaccount.models import SocialAccount, SocialLogin
from django.contrib.auth.models import User
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.backends.db import SessionStore
from django.test import RequestFactory, TestCase
from django.urls import reverse

from app.adapters import ReuseHubSocialAccountAdapter
from app.models import UserProfile


class GoogleOAuthIntegrationTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.adapter = get_adapter()

    def _create_authenticated_mock_request(self, path="/", user=None):
        request = self.factory.get(path)
        request.session = SessionStore()
        request.session.save()
        messages_storage = FallbackStorage(request)
        setattr(request, "_messages", messages_storage)
        request.user = user if user else MagicMock(is_authenticated=False)
        return request

    def test_google_login_redirect_url(self):
        """Test that initiating Google OAuth redirects to Google's OAuth 2.0 endpoint."""
        response = self.client.get(reverse("google_login"))
        self.assertEqual(response.status_code, 302)
        redirect_url = response.headers.get("Location", "")
        self.assertTrue(redirect_url.startswith("https://accounts.google.com/o/oauth2/v2/auth"))

        parsed = urlparse(redirect_url)
        params = parse_qs(parsed.query)

        self.assertIn("client_id", params)
        self.assertIn("redirect_uri", params)
        self.assertTrue(params["redirect_uri"][0].endswith("/accounts/google/login/callback/"))
        self.assertIn("scope", params)
        self.assertTrue("email" in params["scope"][0] and "profile" in params["scope"][0])
        self.assertIn("prompt", params)
        self.assertEqual(params["prompt"][0], "select_account")

    def test_login_page_renders_continue_with_google(self):
        """Test that ReuseHub login page renders the Continue with Google button."""
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Continue with Google")
        self.assertContains(response, 'id="googleSignInBtn"')
        self.assertContains(response, reverse("google_login"))
        self.assertContains(response, "or sign in with username")

    def test_register_page_renders_continue_with_google(self):
        """Test that ReuseHub register page renders the Continue with Google button."""
        response = self.client.get(reverse("register"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Continue with Google")
        self.assertContains(response, 'id="googleSignUpBtn"')
        self.assertContains(response, reverse("google_login"))
        self.assertContains(response, "or register with email")

    def test_adapter_links_existing_user_by_verified_email_preserving_password(self):
        """
        Verify that an existing user registered via email/password is linked to their
        Google account when logging in with a verified Google email, preserving their password.
        """
        existing_user = User.objects.create_user(
            username="ecowarrior",
            email="ecowarrior@gmail.com",
            password="OriginalPassword123!",
            first_name="Eco",
            last_name="Warrior",
            is_active=False,
        )
        self.assertTrue(existing_user.has_usable_password())

        request = self._create_authenticated_mock_request("/")

        social_account = SocialAccount(
            provider="google",
            uid="google-uid-12345",
            extra_data={
                "email": "ecowarrior@gmail.com",
                "email_verified": True,
                "given_name": "Eco",
                "family_name": "Warrior",
            },
        )
        sociallogin = SocialLogin(account=social_account)
        sociallogin.email_addresses = [
            EmailAddress(email="ecowarrior@gmail.com", verified=True, primary=True)
        ]

        self.adapter.pre_social_login(request, sociallogin)

        # User is linked and active
        self.assertEqual(sociallogin.user, existing_user)
        existing_user.refresh_from_db()
        self.assertTrue(existing_user.is_active)
        profile = UserProfile.objects.get(user=existing_user)
        self.assertTrue(profile.email_verified)
        # Password remains usable and valid
        self.assertTrue(existing_user.has_usable_password())
        self.assertTrue(existing_user.check_password("OriginalPassword123!"))

    def test_adapter_save_user_creates_verified_profile(self):
        """Verify that a brand new Google OAuth user gets an active account and verified profile."""
        request = self._create_authenticated_mock_request("/")

        new_user = User(
            username="greencommunity",
            email="greencommunity@gmail.com",
        )
        social_account = SocialAccount(
            provider="google",
            uid="google-uid-99999",
            extra_data={
                "email": "greencommunity@gmail.com",
                "email_verified": True,
                "given_name": "Green",
                "family_name": "Community",
            },
        )
        sociallogin = SocialLogin(user=new_user, account=social_account)

        adapter = ReuseHubSocialAccountAdapter()
        saved_user = adapter.save_user(request, sociallogin)

        self.assertTrue(saved_user.is_active)
        self.assertEqual(saved_user.first_name, "Green")
        self.assertEqual(saved_user.last_name, "Community")

        profile = UserProfile.objects.get(user=saved_user)
        self.assertTrue(profile.email_verified)

        email_record = EmailAddress.objects.get(user=saved_user)
        self.assertEqual(email_record.email, "greencommunity@gmail.com")
        self.assertTrue(email_record.verified)
        self.assertTrue(email_record.primary)

    def test_adapter_authentication_error_redirects_gracefully(self):
        """Test that authentication error / cancellation is caught and redirected with flash message."""
        request = self._create_authenticated_mock_request("/accounts/google/login/callback/")

        provider = MagicMock()
        provider.id = "google"

        adapter = ReuseHubSocialAccountAdapter()
        with self.assertRaises(ImmediateHttpResponse) as cm:
            adapter.on_authentication_error(request, provider, error="access_denied")

        response = cm.exception.response
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers.get("Location"), reverse("login"))
