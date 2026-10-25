"""
Custom Social Account Adapter for ReuseHub.
Handles Google OAuth 2.0 authentication workflows, seamless account linking
for verified emails, profile synchronization, and graceful error handling.
"""
import logging
from typing import cast

from allauth.account.models import EmailAddress
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib import messages
from django.contrib.auth.models import User
from django.shortcuts import redirect

from app.models import UserProfile

logger = logging.getLogger(__name__)


class ReuseHubSocialAccountAdapter(DefaultSocialAccountAdapter):
    """
    Custom adapter for ReuseHub to handle Google OAuth authentication securely:
    - Automatically links Google logins to existing accounts with matching verified emails.
    - Preserves existing passwords and credentials.
    - Ensures UserProfile exists and sets email_verified = True for Google users.
    - Gracefully handles cancelled logins and authentication errors.
    """

    def pre_social_login(self, request, sociallogin):
        """
        Invoked just after Google authentication succeeds, before login is finalized.
        Handles account linking and profile activation.
        """
        # If user is already logged in (e.g. connecting account from profile)
        if request.user.is_authenticated:
            if sociallogin.is_existing and sociallogin.user != request.user:
                messages.warning(
                    request,
                    "This Google account is already linked to another ReuseHub user."
                )
                raise ImmediateHttpResponse(redirect("profile"))
            return

        # Case 1: Existing Google social account connection
        if sociallogin.is_existing:
            user = sociallogin.user
            if not user:
                return
            needs_save = False

            if not user.is_active:
                user.is_active = True
                needs_save = True

            # Synchronize first and last name if empty
            extra_data = sociallogin.account.extra_data
            given_name = extra_data.get("given_name") or ""
            family_name = extra_data.get("family_name") or ""
            if not user.first_name and given_name:
                user.first_name = given_name
                needs_save = True
            if not user.last_name and family_name:
                user.last_name = family_name
                needs_save = True

            if needs_save:
                user.save()

            # Ensure profile email_verified is True
            profile, _ = UserProfile.objects.get_or_create(user=user)
            if not profile.email_verified:
                profile.email_verified = True
                profile.save()

            # Ensure allauth EmailAddress is recorded
            if user.email:
                EmailAddress.objects.get_or_create(
                    user=user,
                    email=user.email.lower(),
                    defaults={"verified": True, "primary": True},
                )
            return

        # Case 2: New Google social login - check for existing user with identical verified email
        email = (
            sociallogin.account.extra_data.get("email")
            or (sociallogin.email_addresses[0].email if sociallogin.email_addresses else None)
        )

        if not email:
            logger.warning("Google OAuth did not provide an email address.")
            return

        email = email.strip().lower()
        existing_user = User.objects.filter(email__iexact=email).first()

        if existing_user:
            # Check Google email verification status
            is_google_verified = (
                sociallogin.account.extra_data.get("email_verified", False)
                or any(e.verified for e in sociallogin.email_addresses if e.email.lower() == email)
            )

            if is_google_verified:
                # Safe linking: Google has verified this email address matches the existing user
                sociallogin.connect(request, existing_user)

                # Activate user if previously inactive (e.g. pending email OTP)
                needs_save = False
                if not existing_user.is_active:
                    existing_user.is_active = True
                    needs_save = True

                extra_data = sociallogin.account.extra_data
                given_name = extra_data.get("given_name") or ""
                family_name = extra_data.get("family_name") or ""
                if not existing_user.first_name and given_name:
                    existing_user.first_name = given_name
                    needs_save = True
                if not existing_user.last_name and family_name:
                    existing_user.last_name = family_name
                    needs_save = True

                if needs_save:
                    existing_user.save()

                profile, _ = UserProfile.objects.get_or_create(user=existing_user)
                if not profile.email_verified:
                    profile.email_verified = True
                    profile.save()

                # Ensure allauth EmailAddress record exists
                EmailAddress.objects.get_or_create(
                    user=existing_user,
                    email=email,
                    defaults={"verified": True, "primary": True},
                )

                logger.info(
                    "Connected Google identity to existing ReuseHub user '%s' (%s).",
                    existing_user.username,
                    email,
                )
            else:
                messages.error(
                    request,
                    "Your Google email is not verified by Google. Cannot link automatically for security."
                )
                raise ImmediateHttpResponse(redirect("login"))

    def save_user(self, request, sociallogin, form=None):
        """
        Saves a newly registered social login user.
        Ensures active status, verified email flag, and name attributes.
        """
        user = cast(User, super().save_user(request, sociallogin, form))
        user.is_active = True

        extra_data = sociallogin.account.extra_data
        given_name = str(extra_data.get("given_name") or "")
        family_name = str(extra_data.get("family_name") or "")
        if given_name and not user.first_name:
            user.first_name = given_name
        if family_name and not user.last_name:
            user.last_name = family_name
        user.save()

        # Ensure ReuseHub UserProfile exists and marks email as verified
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.email_verified = True
        profile.save()

        # Ensure allauth EmailAddress record is verified and primary
        if user.email:
            email_record, _ = EmailAddress.objects.get_or_create(
                user=user,
                email=user.email.lower(),
                defaults={"verified": True, "primary": True},
            )
            if not email_record.verified or not email_record.primary:
                email_record.verified = True
                email_record.primary = True
                email_record.save()

        return user

    def on_authentication_error(
        self, request, provider, error=None, exception=None, extra_context=None
    ):
        """
        Gracefully handles cancellation or OAuth failure without showing raw traceback.
        """
        logger.warning(
            "Google authentication error: error=%s, exception=%s", error, exception
        )
        messages.warning(
            request,
            "Google sign-in was cancelled or encountered an issue. Please try again or use your password."
        )
        raise ImmediateHttpResponse(redirect("login"))
