"""
ReuseHub Centralized Mailing Utility
====================================
Provides a single, reusable email service powered by the Resend HTTPS API (port 443).
Bypasses cloud and Render Free tier SMTP port blocks.

Handles:
- Email verification OTPs during registration
- Password-reset emails
- Item request notifications to donors
- Request acceptance/rejection/completion updates to requesters
- Item status updates (available, given away, cancelled)
- Account & admin moderation alerts
"""

import logging
import os
import re
import sys
from typing import Any

import resend
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from resend.exceptions import (
    InvalidApiKeyError,
    RateLimitError,
    ResendError,
)

logger = logging.getLogger(__name__)


def send_reusehub_email(
    subject: str,
    to_email: str | list[str],
    template_name: str,
    context: dict[str, Any] | None = None,
    plain_message: str | None = None,
    fail_silently: bool = True,
) -> bool:
    """
    Central helper to send responsive HTML and plain-text emails via Resend HTTPS API.

    1. Production & Enabled Environments:
       When RESEND_API_KEY is configured, sends via official Resend HTTPS API (port 443).
    2. Local Development & Automated Tests:
       When RESEND_API_KEY is empty in DEBUG/test mode, falls back safely to Django's
       configured EMAIL_BACKEND (console / locmem), avoiding blocked SMTP connections.

    Security & Privacy:
       Never logs API keys, passwords, OTP values, or sensitive payload data.
    """
    if not to_email:
        logger.warning("Attempted to send email with empty recipient: subject=%s", subject)
        return False

    if context is None:
        context = {}

    from_email = (
        getattr(settings, "RESEND_FROM_EMAIL", None)
        or getattr(settings, "DEFAULT_FROM_EMAIL", None)
        or os.getenv("RESEND_FROM_EMAIL", "ReuseHub <onboarding@resend.dev>")
    )
    context.setdefault("from_email", from_email)
    context.setdefault("site_name", "ReuseHub")

    try:
        html_content = render_to_string(template_name, context)
        text_content = plain_message or strip_tags(html_content)
    except Exception:
        logger.exception("Failed to render email template '%s'", template_name)
        if not fail_silently:
            raise
        return False

    recipient_list: list[str] = [to_email] if isinstance(to_email, str) else list(to_email)
    full_subject = f"[ReuseHub] {subject}"
    safe_log_subject = re.sub(r"\d{4,8}", "[REDACTED]", subject)

    # 1. Primary Delivery Method: Official Resend HTTPS API (Port 443)
    resend_api_key = getattr(settings, "RESEND_API_KEY", None) or os.getenv("RESEND_API_KEY")
    if resend_api_key:
        last_error: Exception | None = None
        try:
            resend.api_key = resend_api_key.strip()
            params: resend.Emails.SendParams = {
                "from": from_email,
                "to": recipient_list,
                "subject": full_subject,
                "html": html_content,
                "text": text_content,
            }
            resp = resend.Emails.send(params)
            email_id = resp.get("id") if isinstance(resp, dict) else getattr(resp, "id", None)
            if email_id:
                logger.info("Successfully sent email '%s' via Resend HTTPS API", safe_log_subject)
                return True
            logger.error("Resend API completed without returning an email ID for '%s'", safe_log_subject)
            return False
        except InvalidApiKeyError as exc:
            last_error = exc
            logger.error("Resend authentication failed: configured API key is invalid.")
        except RateLimitError as exc:
            last_error = exc
            logger.error("Resend API rate limit exceeded while dispatching email '%s'.", safe_log_subject)
        except ResendError as exc:
            last_error = exc
            logger.error("Resend API error dispatching email '%s': %s", safe_log_subject, exc)
        except Exception as exc:
            last_error = exc
            logger.exception("Unexpected error dispatching email '%s' via Resend API", safe_log_subject)

        if not fail_silently and last_error is not None:
            raise last_error
        return False

    # 2. Local Development & Automated Testing Fallback (Django EMAIL_BACKEND)
    # If RESEND_API_KEY is not configured:
    # - In test suites (locmem) or local DEBUG (console), route safely via Django backend.
    # - In real production (RENDER without RESEND_API_KEY), abort safely rather than attempting blocked SMTP.
    backend_name = str(getattr(settings, "EMAIL_BACKEND", ""))
    is_safe_dev_or_test = (
        "locmem" in backend_name
        or "console" in backend_name
        or getattr(settings, "DEBUG", False)
        or "test" in sys.argv
    )

    if not is_safe_dev_or_test:
        logger.error(
            "RESEND_API_KEY is not configured in production. Cannot deliver email '%s'. "
            "Configure RESEND_API_KEY in Render Dashboard -> Environment.",
            safe_log_subject,
        )
        if not fail_silently:
            raise ValueError("RESEND_API_KEY is required in production environment.")
        return False

    try:
        email = EmailMultiAlternatives(
            subject=full_subject,
            body=text_content,
            from_email=from_email,
            to=recipient_list,
        )
        email.attach_alternative(html_content, "text/html")
        email.send(fail_silently=False)
        logger.info("Sent email '%s' via Django local fallback backend", safe_log_subject)
        return True
    except Exception:
        logger.exception("Failed to send email '%s' via local fallback backend", safe_log_subject)
        if not fail_silently:
            raise
        return False


def send_registration_otp_email(user, otp_code, validity_minutes=15):
    """Send 6-digit verification OTP code to new user during registration."""
    logger.info("Dispatching registration verification OTP email to user '%s'", user.username)
    subject = f"Your Verification Code is {otp_code}"
    context = {
        "user": user,
        "username": user.username,
        "otp_code": otp_code,
        "validity_minutes": validity_minutes,
    }
    return send_reusehub_email(
        subject=subject,
        to_email=user.email,
        template_name="emails/registration_otp.html",
        context=context,
    )


def send_password_reset_email(user, reset_url):
    """Send password reset link to user."""
    subject = "Reset Your Account Password"
    context = {
        "user": user,
        "reset_url": reset_url,
    }
    return send_reusehub_email(
        subject=subject,
        to_email=user.email,
        template_name="emails/password_reset.html",
        context=context,
    )


def send_item_request_notification(item_request, action_url=None):
    """Notify donor that someone requested their listed item."""
    donor = item_request.item.donor
    if not donor.email:
        return False

    subject = f"New Request for '{item_request.item.title}'"
    context = {
        "donor": donor,
        "requester": item_request.requester,
        "item": item_request.item,
        "request_message": item_request.message,
        "contact_info": item_request.contact_info,
        "action_url": action_url or f"/items/{item_request.item.pk}/",
    }
    return send_reusehub_email(
        subject=subject,
        to_email=donor.email,
        template_name="emails/item_request_notification.html",
        context=context,
    )


def send_request_status_notification(item_request, action, action_url=None, review_url=None):
    """Notify requester when their request is accepted, rejected, or completed."""
    requester = item_request.requester
    if not requester.email:
        return False

    status_titles = {
        "accept": f"Accepted: Your request for '{item_request.item.title}'",
        "reject": f"Update on your request for '{item_request.item.title}'",
        "complete": f"Exchange Completed: '{item_request.item.title}'",
    }
    subject = status_titles.get(action, f"Update on request for '{item_request.item.title}'")

    context = {
        "requester": requester,
        "item": item_request.item,
        "action": action,
        "donor_notes": item_request.donor_notes,
        "action_url": action_url or f"/items/{item_request.item.pk}/",
        "review_url": review_url,
    }
    return send_reusehub_email(
        subject=subject,
        to_email=requester.email,
        template_name="emails/request_status_notification.html",
        context=context,
    )


def send_item_status_update(item, old_status, new_status, action_url=None):
    """Notify interested requesters or owner when item status changes."""
    recipients = []
    # Include donor
    if item.donor.email:
        recipients.append(item.donor.email)

    # If given away, notify all accepted/pending requesters
    for req in item.requests.select_related("requester").all():
        if req.requester.email and req.requester.email not in recipients:
            recipients.append(req.requester.email)

    if not recipients:
        return False

    status_labels = dict(item.STATUS_CHOICES)
    status_display = status_labels.get(new_status, new_status)
    subject = f"Listing Update: '{item.title}' is now {status_display}"

    status_messages = {
        "GIVEN_AWAY": "This item has been successfully given away and is no longer available.",
        "AVAILABLE": "This item is now back and available for community requests.",
        "CANCELLED": "This listing has been cancelled by the donor.",
        "REQUESTED": "This item currently has an accepted claim and is pending collection.",
    }

    success_count = 0
    for email in recipients:
        context = {
            "item": item,
            "status_display": status_display,
            "status_message": status_messages.get(new_status, ""),
            "action_url": action_url or f"/items/{item.pk}/",
        }
        if send_reusehub_email(
            subject=subject,
            to_email=email,
            template_name="emails/item_status_update.html",
            context=context,
        ):
            success_count += 1
    return success_count > 0


def send_admin_or_account_notification(user, subject, headline, message_body, action_url=None, action_text=None):
    """Send administrative or account status notification to a user."""
    if not user.email:
        return False

    context = {
        "user": user,
        "subject": subject,
        "headline": headline,
        "message_body": message_body,
        "action_url": action_url,
        "action_text": action_text or "View Details",
    }
    return send_reusehub_email(
        subject=subject,
        to_email=user.email,
        template_name="emails/account_notification.html",
        context=context,
    )
