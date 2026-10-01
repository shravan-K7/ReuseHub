"""
ReuseHub Centralized Mailing Utility
====================================
Provides a single, reusable email service powered by the central ReuseHub sender
account (e.g. reusehub.support@gmail.com) via Gmail SMTP or production transactional provider.

Handles:
- Email verification OTPs during registration
- Password-reset emails
- Item request notifications to donors
- Request acceptance/rejection/completion updates to requesters
- Item status updates (available, given away, cancelled)
- Account & admin moderation alerts
"""

import logging
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags

logger = logging.getLogger(__name__)


def send_reusehub_email(
    subject,
    to_email,
    template_name,
    context=None,
    plain_message=None,
    fail_silently=True,
):
    """
    Central helper to send beautiful responsive HTML and plain-text emails.
    Uses DEFAULT_FROM_EMAIL configured with Gmail SMTP or environment settings.
    """
    if not to_email:
        logger.warning("Attempted to send email with empty recipient: subject=%s", subject)
        return False

    if context is None:
        context = {}

    # Standard global context values
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "ReuseHub Support <reusehub.support@gmail.com>")
    context.setdefault("from_email", from_email)
    context.setdefault("site_name", "ReuseHub")

    try:
        html_content = render_to_string(template_name, context)
        text_content = plain_message or strip_tags(html_content)

        email = EmailMultiAlternatives(
            subject=f"[ReuseHub] {subject}",
            body=text_content,
            from_email=from_email,
            to=[to_email] if isinstance(to_email, str) else list(to_email),
        )
        email.attach_alternative(html_content, "text/html")
        email.send(fail_silently=False)
        logger.info("Successfully sent email '%s' to %s", subject, to_email)
        return True
    except Exception as exc:
        logger.exception("Failed to send email '%s' to %s: %s", subject, to_email, exc)
        if not fail_silently:
            raise
        return False


def send_registration_otp_email(user, otp_code, validity_minutes=15):
    """Send 6-digit verification OTP code to new user during registration."""
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
