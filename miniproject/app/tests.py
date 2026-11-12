from datetime import timedelta
import threading
import traceback
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.db import connections
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
import requests

import io
from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile

from .emails import send_reusehub_email
from .forms import ItemForm, ReuseHubPasswordResetForm, UserRegisterForm
from .models import Category, EmailOTP, Item, ItemImage, ItemRequest, Report, SupportInquiry

# test.py is used to automatically test whether your features are working correctly. Your file contains a ReuseHubTests(TestCase) class with tests for pages, requests, admin access, profiles, OTP, emails, password reset, etc


@override_settings(BREVO_API_KEY="")
class ReuseHubTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="testdonor", password="password123", email="testdonor@example.com"
        )
        self.requester = User.objects.create_user(
            username="testrequester",
            password="password123",
            email="testrequester@example.com",
        )
        self.admin_user = User.objects.create_superuser(
            username="superadmin", password="password123", email="admin@test.com"
        )

        self.category = Category.objects.create(
            name="Electronics", description="Gadgets and gear"
        )
        self.item = Item.objects.create(
            donor=self.user,
            category=self.category,
            title="Vintage Lamp",
            description="Working vintage brass lamp.",
            condition="GOOD",
            is_repairable=False,
            pickup_location="Downtown Library",
            status="AVAILABLE",
            moderation_status="APPROVED",
        )

    def test_home_page_status_code(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Vintage Lamp")
        self.assertContains(response, "ReuseHub")

    def test_item_detail_view(self):
        # Canonical slug URL returns 200
        response = self.client.get(self.item.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Vintage Lamp")
        self.assertContains(response, "Downtown Library")

        # Legacy /items/<pk>/ redirects to canonical slug URL
        legacy_response = self.client.get(reverse("item_detail", kwargs={"pk": self.item.pk}))
        self.assertRedirects(legacy_response, self.item.get_absolute_url())

    def test_item_slug_generation_and_redirect(self):
        self.assertEqual(self.item.slug, "vintage-lamp")
        self.assertEqual(self.item.get_absolute_url(), f"/items/{self.item.pk}/vintage-lamp/")

        # Mismatched slug automatically redirects to canonical slug
        wrong_slug_url = reverse("item_detail_slug", kwargs={"pk": self.item.pk, "slug": "outdated-title"})
        response = self.client.get(wrong_slug_url)
        self.assertRedirects(response, self.item.get_absolute_url())

    def test_request_item_flow(self):
        self.client.login(username="testrequester", password="password123")
        response = self.client.post(
            reverse("request_item", kwargs={"pk": self.item.pk}),
            {"message": "I would love to pick this up!", "contact_info": "555-0199"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            ItemRequest.objects.filter(
                item=self.item, requester=self.requester
            ).exists()
        )

    def test_admin_dashboard_access_control(self):
        # Regular user cannot access
        self.client.login(username="testdonor", password="password123")
        response = self.client.get(reverse("admin_dashboard"))
        self.assertEqual(response.status_code, 302)

        # Admin user can access
        self.client.login(username="superadmin", password="password123")
        response = self.client.get(reverse("admin_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Admin Control & Activity Monitor")

    def test_public_profile_view(self):
        # Setup donor profile details
        self.user.profile.bio = "Hello! I love circular fashion and electronics."
        self.user.profile.location = "Sunnyvale Community"
        self.user.profile.phone = "555-987-6543"
        self.user.email = "private_donor_email@example.com"
        self.user.save()
        self.user.profile.save()

        response = self.client.get(
            reverse("public_profile", kwargs={"username": self.user.username})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "testdonor")
        self.assertContains(response, "Sunnyvale Community")
        self.assertContains(response, "circular fashion")

    def test_public_profile_privacy(self):
        """Verify that private data (email, phone) is strictly hidden on the public profile."""
        self.user.email = "secret_donor@private.org"
        self.user.profile.phone = "+1-555-HIDDEN-NUM"
        self.user.save()
        self.user.profile.save()

        response = self.client.get(
            reverse("public_profile", kwargs={"username": self.user.username})
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "secret_donor@private.org")
        self.assertNotContains(response, "+1-555-HIDDEN-NUM")
        self.assertContains(response, "Privacy Protected")

    def test_user_review_flow_after_completed_exchange(self):
        """Verify 1-5 star ratings can be submitted only after a completed exchange."""
        # Create request and mark it completed
        req = ItemRequest.objects.create(
            item=self.item,
            requester=self.requester,
            message="Need this vintage lamp",
            status="COMPLETED",
        )
        self.item.status = "GIVEN_AWAY"
        self.item.save()

        # Requester logs in to rate donor
        self.client.login(username="testrequester", password="password123")
        review_resp = self.client.post(
            reverse("submit_review", kwargs={"request_id": req.id}),
            {"rating": 5, "comment": "Awesome brass lamp, very generous neighbour!"},
        )
        self.assertEqual(review_resp.status_code, 302)

        # Check public profile of donor shows rating & review
        profile_resp = self.client.get(
            reverse("public_profile", kwargs={"username": self.user.username})
        )
        self.assertEqual(profile_resp.status_code, 200)
        self.assertContains(profile_resp, "Awesome brass lamp")
        self.assertContains(profile_resp, "5.0")

    def test_report_user_profile(self):
        """Verify reporting an inappropriate user profile."""
        self.client.login(username="testrequester", password="password123")
        report_resp = self.client.post(
            reverse("report_user", kwargs={"username": self.user.username}),
            {
                "reason": "HARASSMENT",
                "details": "User was using offensive language in messages.",
            },
        )
        self.assertEqual(report_resp.status_code, 302)
        self.assertTrue(
            Report.objects.filter(
                reported_user=self.user, reported_by=self.requester
            ).exists()
        )

    def test_unauthenticated_user_cannot_submit_help_report_or_message(self):
        """Unauthenticated visitor cannot submit a report or support ticket."""
        initial_reports_count = Report.objects.count()
        response = self.client.post(
            reverse("help"),
            {
                "subject": "Report a User",
                "message": "Reporting user: testdonor",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)
        self.assertEqual(Report.objects.count(), initial_reports_count)

    def test_authenticated_user_can_report_via_help_desk(self):
        """Authenticated user filing a report via help desk creates a formal Report and SupportInquiry."""
        self.client.login(username="testrequester", password="password123")
        response = self.client.post(
            reverse("help"),
            {
                "subject": "Report a User",
                "message": "Reporting user: testdonor\nUser did not show up.",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            Report.objects.filter(
                reported_by=self.requester, reported_user=self.user
            ).exists()
        )
        self.assertTrue(
            SupportInquiry.objects.filter(
                user=self.requester, subject="Report a User"
            ).exists()
        )

    def test_authenticated_user_general_support_inquiry_recorded(self):
        """Authenticated user submitting general inquiry is logged to SupportInquiry and visible to admin."""
        self.client.login(username="testrequester", password="password123")
        response = self.client.post(
            reverse("help"),
            {
                "subject": "General Inquiry",
                "message": "How do I change my preferred pickup location?",
            },
        )
        self.assertEqual(response.status_code, 302)
        inquiry = SupportInquiry.objects.filter(
            user=self.requester, subject="General Inquiry"
        ).first()
        self.assertIsNotNone(inquiry)
        self.assertEqual(inquiry.status, "PENDING")

        # Admin can view inquiry on admin support dashboard
        self.client.login(username="superadmin", password="password123")
        admin_resp = self.client.get(reverse("admin_support"))
        self.assertEqual(admin_resp.status_code, 200)
        self.assertContains(admin_resp, "How do I change my preferred pickup location?")

        # Admin can resolve the inquiry
        resolve_resp = self.client.get(
            reverse(
                "admin_support_action", kwargs={"pk": inquiry.pk, "action": "resolve"}
            )
        )
        self.assertEqual(resolve_resp.status_code, 302)
        inquiry.refresh_from_db()
        self.assertEqual(inquiry.status, "RESOLVED")

    # ==========================================================================
    # CENTRAL MAILING SYSTEM & OTP VERIFICATION TESTS
    # ==========================================================================

    def test_registration_email_validation(self):
        """Email validation: invalid format is caught and registration rejected."""
        response = self.client.post(
            reverse("register"),
            {
                "username": "bademailuser",
                "email": "not-a-valid-email-address",
                "password": "StrongPassword123!",
                "confirm_password": "StrongPassword123!",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Enter a valid email address")
        self.assertFalse(User.objects.filter(username="bademailuser").exists())

    def test_registration_creates_inactive_user_and_sends_otp(self):
        """Registration creates unverified inactive user, generates OTP, and dispatches email."""
        mail.outbox.clear()
        response = self.client.post(
            reverse("register"),
            {
                "username": "newneighbor",
                "email": "neighbor@example.com",
                "first_name": "Green",
                "last_name": "Neighbor",
                "password": "SecurePass123!",
                "confirm_password": "SecurePass123!",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("verify_otp"))

        # Check user created but inactive
        user = User.objects.get(username="newneighbor")
        self.assertFalse(user.is_active)
        self.assertFalse(user.profile.email_verified)

        # Check OTP generated
        otp = EmailOTP.objects.filter(
            user=user, purpose="REGISTRATION", is_used=False
        ).first()
        self.assertIsNotNone(otp)
        self.assertEqual(len(otp.code), 6)
        self.assertTrue(otp.code.isdigit())

        # Check email in Django test outbox
        self.assertEqual(len(mail.outbox), 1)
        sent_email = mail.outbox[0]
        self.assertIn(otp.code, sent_email.body)
        self.assertIn("neighbor@example.com", sent_email.to)
        self.assertIn("ReuseHub", sent_email.subject)

    def test_verify_otp_with_wrong_code(self):
        """Entering incorrect OTP fails, increments attempts, and keeps account unverified."""
        user = User.objects.create_user(
            username="otpuser1",
            password="password123",
            email="otpuser1@example.com",
            is_active=False,
        )
        otp = EmailOTP.generate_otp(user=user, email=user.email, purpose="REGISTRATION")

        # Simulate registration session
        session = self.client.session
        session["verify_user_id"] = user.id
        session["verify_email"] = user.email
        session.save()

        # Submit wrong code
        response = self.client.post(reverse("verify_otp"), {"otp": "000000"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Invalid verification code")

        # User remains inactive
        user.refresh_from_db()
        self.assertFalse(user.is_active)
        self.assertFalse(user.profile.email_verified)

        # Attempts incremented
        otp.refresh_from_db()
        self.assertEqual(otp.attempts, 1)
        self.assertFalse(otp.is_used)

    def test_verify_otp_with_correct_code_activates_account(self):
        """Entering correct OTP activates account, sets email_verified, and logs user in."""
        user = User.objects.create_user(
            username="otpuser2",
            password="password123",
            email="otpuser2@example.com",
            is_active=False,
        )
        otp = EmailOTP.generate_otp(user=user, email=user.email, purpose="REGISTRATION")

        session = self.client.session
        session["verify_user_id"] = user.id
        session["verify_email"] = user.email
        session.save()

        # Submit correct code
        response = self.client.post(reverse("verify_otp"), {"otp": otp.code})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("home"))

        # User is now active and verified!
        user.refresh_from_db()
        user.profile.refresh_from_db()
        self.assertTrue(user.is_active)
        self.assertTrue(user.profile.email_verified)

        otp.refresh_from_db()
        self.assertTrue(otp.is_used)

    def test_verify_otp_expired_code(self):
        """Expired OTP code cannot activate user account."""
        user = User.objects.create_user(
            username="otpuser3",
            password="password123",
            email="otpuser3@example.com",
            is_active=False,
        )
        otp = EmailOTP.generate_otp(
            user=user, email=user.email, purpose="REGISTRATION", validity_minutes=-5
        )

        session = self.client.session
        session["verify_user_id"] = user.id
        session["verify_email"] = user.email
        session.save()

        response = self.client.post(reverse("verify_otp"), {"otp": otp.code})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "expired")

        user.refresh_from_db()
        self.assertFalse(user.is_active)

    def test_resend_otp_flow_and_cooldown(self):
        """Resending OTP generates new code, and immediate re-attempt triggers cooldown."""
        user = User.objects.create_user(
            username="otpuser4",
            password="password123",
            email="otpuser4@example.com",
            is_active=False,
        )
        # Old OTP created 2 minutes ago
        old_otp = EmailOTP.generate_otp(
            user=user, email=user.email, purpose="REGISTRATION"
        )
        old_otp.created_at = timezone.now() - timedelta(minutes=2)
        old_otp.save()

        session = self.client.session
        session["verify_user_id"] = user.id
        session["verify_email"] = user.email
        session.save()

        mail.outbox.clear()
        # Request resend
        resp = self.client.post(reverse("resend_otp"))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)

        new_otp = (
            EmailOTP.objects.filter(user=user, is_used=False)
            .order_by("-created_at")
            .first()
        )
        self.assertIsNotNone(new_otp)
        self.assertNotEqual(new_otp.id, old_otp.id)

        # Immediate repeat should trigger cooldown warning
        repeat_resp = self.client.post(reverse("resend_otp"), follow=True)
        self.assertContains(repeat_resp, "Please wait")

    def test_unverified_user_login_prompts_otp(self):
        """Unverified user attempting login receives fresh OTP and is redirected to verify."""
        user = User.objects.create_user(
            username="unverifiedmember",
            password="mypassword123",
            email="unverified@example.com",
            is_active=False,
        )
        mail.outbox.clear()

        response = self.client.post(
            reverse("login"),
            {
                "username": "unverifiedmember",
                "password": "mypassword123",
            },
            follow=True,
        )

        self.assertContains(response, "not verified yet")
        self.assertContains(response, "Verify Your Email")
        self.assertEqual(len(mail.outbox), 1)

    def test_item_request_triggers_donor_email(self):
        """Requesting an item sends notification email to donor."""
        mail.outbox.clear()
        self.client.login(username="testrequester", password="password123")
        response = self.client.post(
            reverse("request_item", kwargs={"pk": self.item.pk}),
            {
                "message": "Hello, I can collect this lamp today at 5pm!",
                "contact_info": "phone: 555-4321",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        donor_email = mail.outbox[0]
        self.assertIn("testdonor@example.com", donor_email.to)
        self.assertIn("Vintage Lamp", donor_email.subject)
        self.assertIn("555-4321", donor_email.body)

    def test_respond_request_triggers_requester_email(self):
        """Donor accepting/rejecting request sends notification email to requester."""
        req = ItemRequest.objects.create(
            item=self.item,
            requester=self.requester,
            message="Would love to pick up!",
            status="PENDING",
        )
        self.client.login(username="testdonor", password="password123")

        # Test Accept
        mail.outbox.clear()
        accept_resp = self.client.get(
            reverse(
                "respond_request", kwargs={"request_id": req.id, "action": "accept"}
            )
        )
        self.assertEqual(accept_resp.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        accept_mail = mail.outbox[0]
        self.assertIn("testrequester@example.com", accept_mail.to)
        self.assertIn("Accepted", accept_mail.subject)

        # Test Reject
        mail.outbox.clear()
        reject_resp = self.client.get(
            reverse(
                "respond_request", kwargs={"request_id": req.id, "action": "reject"}
            )
        )
        self.assertEqual(reject_resp.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        reject_mail = mail.outbox[0]
        self.assertIn("testrequester@example.com", reject_mail.to)

    def test_password_reset_flow(self):
        """Password reset dispatches email with token and successfully sets new password."""
        mail.outbox.clear()
        # Request reset
        resp = self.client.post(
            reverse("password_reset"),
            {
                "email": "testdonor@example.com",
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)
        reset_mail = mail.outbox[0]
        self.assertIn("Reset", reset_mail.subject)

        # Generate token and confirm
        token = default_token_generator.make_token(self.user)
        uidb64 = urlsafe_base64_encode(force_bytes(self.user.pk))

        confirm_url = reverse(
            "password_reset_confirm", kwargs={"uidb64": uidb64, "token": token}
        )
        confirm_get = self.client.get(confirm_url)
        self.assertEqual(confirm_get.status_code, 200)
        self.assertContains(confirm_get, "Choose a New Password")

        confirm_post = self.client.post(
            confirm_url,
            {
                "new_password1": "BrandNewPassword123!",
                "new_password2": "BrandNewPassword123!",
            },
        )
        self.assertEqual(confirm_post.status_code, 302)

        # Verify password changed
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("BrandNewPassword123!"))

    def test_central_reusable_email_utility(self):
        """Reusable email utility produces branded HTML and text emails."""
        mail.outbox.clear()
        success = send_reusehub_email(
            subject="Test System Notification",
            to_email="testmember@example.com",
            template_name="emails/account_notification.html",
            context={
                "user": self.user,
                "headline": "System Alert",
                "message_body": "This is a test notification from the central mailing service.",
            },
        )
        self.assertTrue(success)
        self.assertEqual(len(mail.outbox), 1)
        out = mail.outbox[0]
        self.assertEqual(out.subject, "[ReuseHub] Test System Notification")
        self.assertIn("ReuseHub", out.body)
        self.assertIn("System Alert", out.body)
        # Has HTML alternative
        self.assertEqual(len(out.alternatives), 1)
        self.assertEqual(out.alternatives[0][1], "text/html")

    def test_password_reset_form_validation(self):
        """Form validation handles empty, malformed, and valid emails properly."""
        # Direct form unit tests
        empty_form = ReuseHubPasswordResetForm(data={"email": ""})
        self.assertFalse(empty_form.is_valid())
        self.assertIn("email", empty_form.errors)

        malformed_form = ReuseHubPasswordResetForm(
            data={"email": "invalid-email-format"}
        )
        self.assertFalse(malformed_form.is_valid())
        self.assertIn("email", malformed_form.errors)

        valid_form = ReuseHubPasswordResetForm(data={"email": "valid@example.com"})
        self.assertTrue(valid_form.is_valid())

        # View test with empty email
        resp = self.client.post(reverse("password_reset"), {"email": ""})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("form", resp.context)
        self.assertIn("email", resp.context["form"].errors)

        # Valid email for non-existent user redirects to done without leaking info
        resp3 = self.client.post(
            reverse("password_reset"), {"email": "nonexistent@example.com"}
        )
        self.assertEqual(resp3.status_code, 302)
        self.assertEqual(resp3.url, reverse("password_reset_done"))

    def test_item_form_with_dict_and_instance(self):
        """ItemForm should clean gracefully with dictionary data and instance without getlist errors."""
        form = ItemForm(
            data={
                "title": "Restored Chair",
                "category": self.category.id,
                "condition": "GOOD",
                "pickup_location": "East Library",
                "description": "A sturdy restored wooden chair.",
                "delete_images": [],
            },
            instance=self.item,
        )
        self.assertTrue(form.is_valid(), f"Errors: {form.errors}")

    def test_admin_moderate_action_without_referer(self):
        """admin_moderate_action should safely redirect to admin_listings when HTTP_REFERER is absent."""
        self.client.login(username="superadmin", password="password123")
        resp = self.client.get(
            reverse(
                "admin_moderate_action",
                kwargs={"pk": self.item.pk, "action": "approve"},
            )
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("admin_listings"))

    def test_admin_users_distinct_counts(self):
        """Admin users view should calculate distinct counts without Cartesian product multiplication."""
        ItemRequest.objects.create(
            item=self.item, requester=self.requester, message="Req 1"
        )
        Item.objects.create(
            donor=self.requester,
            category=self.category,
            title="Extra Item",
            description="Test item description",
            condition="GOOD",
            pickup_location="Downtown",
            status="AVAILABLE",
            moderation_status="APPROVED",
        )
        self.client.login(username="superadmin", password="password123")
        resp = self.client.get(reverse("admin_users"))
        self.assertEqual(resp.status_code, 200)
        users = list(resp.context["users"])
        requester_user = next(u for u in users if u.username == self.requester.username)
        self.assertEqual(requester_user.items_listed, 1)
        self.assertEqual(requester_user.requests_count, 1)

    def test_user_register_form_duplicate_username_with_different_email(self):
        """UserRegisterForm should reject registration if username is taken by another account."""
        User.objects.create_user(
            username="reserveduser",
            email="original@example.com",
            password="password123",
            is_active=False,
        )
        form = UserRegisterForm(
            data={
                "username": "reserveduser",
                "email": "different@example.com",
                "password": "StrongPassword123!",
                "confirm_password": "StrongPassword123!",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("username", form.errors)

    @patch("requests.post")
    def test_brevo_api_dispatch_success(self, mock_post):
        """send_reusehub_email successfully sends over Brevo HTTPS API when BREVO_API_KEY is configured."""
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "messageId": "<msg_brevo_test_12345@smtp-relay.brevo.com>"
        }
        mock_post.return_value = mock_response

        with self.settings(
            BREVO_API_KEY="brevo_test_mock_key_xyz",
            BREVO_FROM_EMAIL="ReuseHub Support <reusehub.support@gmail.com>",
        ):
            success = send_reusehub_email(
                subject="Account Notice",
                to_email="member@example.com",
                template_name="emails/account_notification.html",
                context={
                    "user": self.user,
                    "headline": "Notice",
                    "message_body": "Test content",
                },
            )
            self.assertTrue(success)
            mock_post.assert_called_once()
            call_url = mock_post.call_args[0][0]
            call_kwargs = mock_post.call_args[1]
            self.assertEqual(call_url, "https://api.brevo.com/v3/smtp/email")
            self.assertEqual(
                call_kwargs["headers"]["api-key"], "brevo_test_mock_key_xyz"
            )
            self.assertEqual(call_kwargs["json"]["sender"]["name"], "ReuseHub Support")
            self.assertEqual(
                call_kwargs["json"]["sender"]["email"], "reusehub.support@gmail.com"
            )
            self.assertEqual(
                call_kwargs["json"]["to"], [{"email": "member@example.com"}]
            )
            self.assertEqual(
                call_kwargs["json"]["subject"], "[ReuseHub] Account Notice"
            )
            self.assertIn("Notice", call_kwargs["json"]["htmlContent"])
            self.assertIn("Test content", call_kwargs["json"]["textContent"])

    @patch("requests.post")
    def test_brevo_api_dispatch_error_handling(self, mock_post):
        """send_reusehub_email catches HTTP 400 and returns False cleanly."""
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = '{"code":"invalid_parameter","message":"Invalid email"}'
        mock_post.return_value = mock_response

        with self.settings(BREVO_API_KEY="brevo_test_mock_key_xyz"):
            success = send_reusehub_email(
                subject="Failure Notice",
                to_email="member@example.com",
                template_name="emails/account_notification.html",
                context={
                    "user": self.user,
                    "headline": "Notice",
                    "message_body": "Test content",
                },
                fail_silently=True,
            )
            self.assertFalse(success)

    @patch("requests.post")
    def test_brevo_api_timeout_handling(self, mock_post):
        """send_reusehub_email catches requests.exceptions.Timeout and returns False safely."""
        mock_post.side_effect = requests.exceptions.Timeout("Connection timed out")

        with self.settings(BREVO_API_KEY="brevo_test_mock_key_xyz"):
            success = send_reusehub_email(
                subject="Timeout Notice",
                to_email="member@example.com",
                template_name="emails/account_notification.html",
                context={
                    "user": self.user,
                    "headline": "Notice",
                    "message_body": "Test content",
                },
                fail_silently=True,
            )
            self.assertFalse(success)

    @patch("requests.post")
    def test_registration_otp_email_via_brevo_and_account_activation(self, mock_post):
        """User registration sends OTP via Brevo HTTPS API, keeps account inactive until verified."""
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"messageId": "<msg_reg_otp_456@brevo.com>"}
        mock_post.return_value = mock_response

        with self.settings(BREVO_API_KEY="brevo_test_mock_key_xyz"):
            reg_resp = self.client.post(
                reverse("register"),
                {
                    "username": "brevouser",
                    "email": "brevouser@example.com",
                    "password": "SecurePassword123!",
                    "confirm_password": "SecurePassword123!",
                },
            )
            self.assertEqual(reg_resp.status_code, 302)
            self.assertRedirects(reg_resp, reverse("verify_otp"))

            # Verify user exists in database and is inactive
            new_user = User.objects.get(username="brevouser")
            self.assertFalse(new_user.is_active)

            # Verify Brevo API was called with OTP email
            mock_post.assert_called_once()
            call_kwargs = mock_post.call_args[1]
            self.assertEqual(
                call_kwargs["json"]["to"], [{"email": "brevouser@example.com"}]
            )
            self.assertIn("Verification Code", call_kwargs["json"]["subject"])

            # Retrieve OTP from database and verify
            otp = EmailOTP.objects.filter(
                user=new_user, purpose="REGISTRATION", is_used=False
            ).first()
            self.assertIsNotNone(otp)

            verify_resp = self.client.post(reverse("verify_otp"), {"otp": otp.code})
            self.assertEqual(verify_resp.status_code, 302)

            new_user.refresh_from_db()
            self.assertTrue(new_user.is_active)

    @patch("requests.post")
    def test_registration_delivery_failure_does_not_leak_otp(self, mock_post):
        """When Brevo delivery fails, user is informed, account remains inactive, and OTP is never exposed in response."""
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.text = (
            '{"code":"too_many_requests","message":"Rate limit exceeded"}'
        )
        mock_post.return_value = mock_response

        with self.settings(BREVO_API_KEY="brevo_test_mock_key_xyz"):
            reg_resp = self.client.post(
                reverse("register"),
                {
                    "username": "failedemailuser",
                    "email": "faileduser@example.com",
                    "password": "SecurePassword123!",
                    "confirm_password": "SecurePassword123!",
                },
                follow=True,
            )
            self.assertEqual(reg_resp.status_code, 200)

            user = User.objects.get(username="failedemailuser")
            self.assertFalse(user.is_active)

            otp = EmailOTP.objects.filter(
                user=user, purpose="REGISTRATION", is_used=False
            ).first()
            self.assertIsNotNone(otp)

            # CRITICAL SECURITY CHECK: OTP code must NEVER be present in page response or error messages
            page_text = reg_resp.content.decode("utf-8")
            self.assertNotIn(otp.code, page_text)
            self.assertIn("unable to deliver", page_text.lower())

    @patch("requests.post")
    def test_password_reset_email_dispatches_via_brevo(self, mock_post):
        """Password reset email dispatches reset URL via Brevo API."""
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"messageId": "<msg_pw_reset_789@brevo.com>"}
        mock_post.return_value = mock_response

        with self.settings(BREVO_API_KEY="brevo_test_mock_key_xyz"):
            resp = self.client.post(
                reverse("password_reset"), {"email": self.user.email}
            )
            self.assertEqual(resp.status_code, 302)
            self.assertRedirects(resp, reverse("password_reset_done"))

            mock_post.assert_called_once()
            call_kwargs = mock_post.call_args[1]
            self.assertEqual(call_kwargs["json"]["to"], [{"email": self.user.email}])
            self.assertIn("Reset Your Account Password", call_kwargs["json"]["subject"])
            self.assertIn("password-reset-confirm", call_kwargs["json"]["htmlContent"])

    def test_dev_fallback_without_brevo_api_key(self):
        """When BREVO_API_KEY is not set, dev/test fallback routes through Django mail outbox safely."""
        with self.settings(
            BREVO_API_KEY="",
            EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        ):
            mail.outbox.clear()
            success = send_reusehub_email(
                subject="Dev Test",
                to_email="devuser@example.com",
                template_name="emails/account_notification.html",
                context={
                    "user": self.user,
                    "headline": "Dev",
                    "message_body": "Testing fallback",
                },
            )
            self.assertTrue(success)
            self.assertEqual(len(mail.outbox), 1)
            self.assertEqual(mail.outbox[0].to, ["devuser@example.com"])
            self.assertIn("Dev Test", mail.outbox[0].subject)

    def test_item_create_no_images(self):
        """Creating an item without uploading images succeeds cleanly."""
        self.client.login(username="testdonor", password="password123")
        data = {
            "title": "Bookshelf Free Giveaway",
            "category": self.category.pk,
            "condition": "GOOD",
            "pickup_location": "East Side Park",
            "description": "Solid pine bookshelf, free to collect.",
        }
        resp = self.client.post(reverse("item_create"), data, follow=True)
        self.assertEqual(resp.status_code, 200)
        item = Item.objects.filter(title="Bookshelf Free Giveaway").first()
        self.assertIsNotNone(item)
        self.assertFalse(bool(item.image))
        self.assertEqual(item.images.count(), 0)

    def test_item_create_with_single_image(self):
        """Creating an item with an uploaded image compresses to WebP and associates ItemImage."""
        self.client.login(username="testdonor", password="password123")
        img_io = io.BytesIO()
        Image.new("RGB", (50, 50), color="blue").save(img_io, format="JPEG")
        img_io.seek(0)
        uploaded = SimpleUploadedFile("lamp.jpg", img_io.read(), content_type="image/jpeg")

        data = {
            "title": "Retro Desk Lamp",
            "category": self.category.pk,
            "condition": "GOOD",
            "pickup_location": "Uptown Cafe",
            "description": "Sturdy reading lamp in good condition.",
            "images": [uploaded],
            "cover_choice": "new:0",
        }
        resp = self.client.post(reverse("item_create"), data, follow=True)
        self.assertEqual(resp.status_code, 200)

        created_item = Item.objects.filter(title="Retro Desk Lamp").first()
        self.assertIsNotNone(created_item)
        self.assertTrue(bool(created_item.image))
        self.assertEqual(created_item.images.count(), 1)
        self.assertTrue(created_item.images.first().is_cover)
        with Image.open(created_item.image) as saved_img:
            self.assertEqual(saved_img.format, "WEBP")

    def test_item_create_with_multiple_images_and_custom_cover(self):
        """Creating an item with multiple images correctly converts to WebP and sets chosen cover."""
        self.client.login(username="testdonor", password="password123")

        img1_io = io.BytesIO()
        Image.new("RGB", (50, 50), color="red").save(img1_io, format="JPEG")
        img1_io.seek(0)
        f1 = SimpleUploadedFile("photo1.jpg", img1_io.read(), content_type="image/jpeg")

        img2_io = io.BytesIO()
        Image.new("RGB", (50, 50), color="green").save(img2_io, format="JPEG")
        img2_io.seek(0)
        f2 = SimpleUploadedFile("photo2.jpg", img2_io.read(), content_type="image/jpeg")

        data = {
            "title": "Wooden Chair Set",
            "category": self.category.pk,
            "condition": "GOOD",
            "pickup_location": "Community Center",
            "description": "Pair of solid wooden chairs.",
            "images": [f1, f2],
            "cover_choice": "new:1",
        }
        resp = self.client.post(reverse("item_create"), data, follow=True)
        self.assertEqual(resp.status_code, 200)

        item = Item.objects.filter(title="Wooden Chair Set").first()
        self.assertIsNotNone(item)
        self.assertEqual(item.images.count(), 2)

        cover_img = item.images.filter(is_cover=True).first()
        self.assertIsNotNone(cover_img)
        self.assertIn("photo2", cover_img.image.name)
        self.assertEqual(item.image.name, cover_img.image.name)
        with Image.open(cover_img.image) as saved_img:
            self.assertEqual(saved_img.format, "WEBP")

    def test_item_create_transparent_png_preserves_alpha(self):
        """Transparent PNG converted to WebP retains alpha transparency without black background."""
        self.client.login(username="testdonor", password="password123")
        png_io = io.BytesIO()
        img = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
        for x in range(30, 70):
            for y in range(30, 70):
                img.putpixel((x, y), (255, 0, 0, 255))
        img.save(png_io, format="PNG")
        png_io.seek(0)
        uploaded = SimpleUploadedFile("logo_transparent.png", png_io.read(), content_type="image/png")

        data = {
            "title": "Transparent Art Piece",
            "category": self.category.pk,
            "condition": "LIKE_NEW",
            "pickup_location": "Art Studio",
            "description": "Digital art sticker graphic.",
            "images": [uploaded],
            "cover_choice": "new:0",
        }
        resp = self.client.post(reverse("item_create"), data, follow=True)
        self.assertEqual(resp.status_code, 200)

        item = Item.objects.filter(title="Transparent Art Piece").first()
        self.assertIsNotNone(item)
        with Image.open(item.image) as saved_img:
            self.assertEqual(saved_img.format, "WEBP")
            self.assertEqual(saved_img.mode, "RGBA")
            corner_pixel = saved_img.getpixel((0, 0))
            self.assertEqual(corner_pixel, (0, 0, 0, 0))

    def test_proportional_resizing_landscape_and_portrait(self):
        """Images exceeding 1600px are downscaled proportionally without exceeding 1600 on either axis."""
        from .image_utils import compress_and_convert_to_webp

        # Landscape 2400x1200 -> should resize to 1600x800
        land_io = io.BytesIO()
        Image.new("RGB", (2400, 1200), color="blue").save(land_io, format="JPEG")
        land_io.seek(0)
        land_file = SimpleUploadedFile("wide.jpg", land_io.read(), content_type="image/jpeg")
        proc_land = compress_and_convert_to_webp(land_file)
        with Image.open(proc_land) as im:
            self.assertEqual(im.size, (1600, 800))
            self.assertEqual(im.format, "WEBP")

        # Portrait 1200x2400 -> should resize to 800x1600
        port_io = io.BytesIO()
        Image.new("RGB", (1200, 2400), color="green").save(port_io, format="JPEG")
        port_io.seek(0)
        port_file = SimpleUploadedFile("tall.jpg", port_io.read(), content_type="image/jpeg")
        proc_port = compress_and_convert_to_webp(port_file)
        with Image.open(proc_port) as im:
            self.assertEqual(im.size, (800, 1600))
            self.assertEqual(im.format, "WEBP")

    def test_already_compressed_webp_upload(self):
        """Uploading an existing WebP image compresses and processes cleanly."""
        self.client.login(username="testdonor", password="password123")
        webp_io = io.BytesIO()
        Image.new("RGB", (400, 300), color="purple").save(webp_io, format="WEBP", quality=90)
        webp_io.seek(0)
        uploaded = SimpleUploadedFile("already.webp", webp_io.read(), content_type="image/webp")

        data = {
            "title": "WebP Item Listing",
            "category": self.category.pk,
            "condition": "GOOD",
            "pickup_location": "North Station",
            "description": "Item with WebP photo upload.",
            "images": [uploaded],
            "cover_choice": "new:0",
        }
        resp = self.client.post(reverse("item_create"), data, follow=True)
        self.assertEqual(resp.status_code, 200)
        item = Item.objects.filter(title="WebP Item Listing").first()
        self.assertIsNotNone(item)
        with Image.open(item.image) as saved_img:
            self.assertEqual(saved_img.format, "WEBP")

    def test_oversized_image_rejected(self):
        """Files exceeding 5 MB are rejected with a clear user-friendly error message."""
        self.client.login(username="testdonor", password="password123")
        huge_bytes = b"0" * (5500 * 1024)
        huge_file = SimpleUploadedFile("huge.jpg", huge_bytes, content_type="image/jpeg")

        data = {
            "title": "Oversized Photo Item",
            "category": self.category.pk,
            "condition": "GOOD",
            "pickup_location": "Main Square",
            "description": "Should fail validation.",
            "images": [huge_file],
        }
        resp = self.client.post(reverse("item_create"), data)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "exceeds the 5MB limit")
        self.assertFalse(Item.objects.filter(title="Oversized Photo Item").exists())

    def test_unsupported_format_rejected(self):
        """Unsupported formats such as .pdf are rejected with clear error."""
        self.client.login(username="testdonor", password="password123")
        bad_file = SimpleUploadedFile("document.pdf", b"%PDF-1.4...", content_type="application/pdf")

        data = {
            "title": "Bad Format Item",
            "category": self.category.pk,
            "condition": "GOOD",
            "pickup_location": "Town Hall",
            "description": "Should fail format validation.",
            "images": [bad_file],
        }
        resp = self.client.post(reverse("item_create"), data)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "has an unsupported format")

    def test_corrupted_image_rejected(self):
        """Files disguised as images but with invalid content are caught and rejected by Pillow validation."""
        self.client.login(username="testdonor", password="password123")
        corrupted = SimpleUploadedFile("fake.jpg", b"This is not a real JPEG image file content at all.", content_type="image/jpeg")

        data = {
            "title": "Fake Image Item",
            "category": self.category.pk,
            "condition": "GOOD",
            "pickup_location": "Harbor View",
            "description": "Should fail content verification.",
            "images": [corrupted],
        }
        resp = self.client.post(reverse("item_create"), data)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "corrupted or not a valid image")

    def test_uploading_5_large_images(self):
        """Uploading 5 images converts all 5 to WebP with dimensions <= 1600."""
        self.client.login(username="testdonor", password="password123")
        uploaded_files = []
        for i in range(5):
            buf = io.BytesIO()
            Image.new("RGB", (1800, 1200), color=(i * 40, 100, 150)).save(buf, format="JPEG", quality=90)
            buf.seek(0)
            uploaded_files.append(
                SimpleUploadedFile(f"batch_{i}.jpg", buf.read(), content_type="image/jpeg")
            )

        data = {
            "title": "Five Photo Showcase",
            "category": self.category.pk,
            "condition": "LIKE_NEW",
            "pickup_location": "Riverside Plaza",
            "description": "Listing with all 5 photo slots utilized.",
            "images": uploaded_files,
            "cover_choice": "new:2",
        }
        resp = self.client.post(reverse("item_create"), data, follow=True)
        self.assertEqual(resp.status_code, 200)

        item = Item.objects.filter(title="Five Photo Showcase").first()
        self.assertIsNotNone(item)
        self.assertEqual(item.images.count(), 5)
        cover = item.images.filter(is_cover=True).first()
        self.assertIsNotNone(cover)
        self.assertIn("batch_2", cover.image.name)
        for photo in item.images.all():
            with Image.open(photo.image) as im:
                self.assertEqual(im.format, "WEBP")
                self.assertLessEqual(im.width, 1600)
                self.assertLessEqual(im.height, 1600)


class WhatsAppMessageOwnerTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.category = Category.objects.create(name="Utility & Bags", slug="utility-bags")
        self.donor = User.objects.create_user(
            username="demo_rahul",
            email="demo_rahul@example.com",
            password="StrongPass123!",
            is_active=True,
        )
        self.donor.profile.phone = "+91 98765 43210"
        self.donor.profile.save()

        self.requester = User.objects.create_user(
            username="requester_anu",
            email="anu@example.com",
            password="StrongPass123!",
            is_active=True,
        )
        self.other_user = User.objects.create_user(
            username="bystander",
            email="bystander@example.com",
            password="StrongPass123!",
            is_active=True,
        )
        self.item = Item.objects.create(
            title="Laptop Backpack",
            description="A spacious brown canvas backpack with multiple compartments.",
            category=self.category,
            condition="GOOD",
            pickup_location="Feroke, Kozhikode, Kerala, 673631, India",
            donor=self.donor,
            status="AVAILABLE",
        )
        self.item_request = ItemRequest.objects.create(
            item=self.item,
            requester=self.requester,
            message="Would love to pick this up for college commute.",
            status="ACCEPTED",
            donor_notes="Available after 5 PM near Feroke bus stand.",
        )

    def test_phone_normalization_variants(self):
        from .phone_utils import build_whatsapp_redirect_url, normalize_phone_for_whatsapp

        self.assertEqual(normalize_phone_for_whatsapp("+91 98765 43210"), "919876543210")
        self.assertEqual(normalize_phone_for_whatsapp("0091-98765-43210"), "919876543210")
        self.assertEqual(normalize_phone_for_whatsapp("9876543210"), "919876543210")
        self.assertEqual(normalize_phone_for_whatsapp("09876543210"), "919876543210")
        self.assertEqual(normalize_phone_for_whatsapp("919876543210"), "919876543210")
        self.assertEqual(normalize_phone_for_whatsapp("+1 (555) 987-6543"), "15559876543")

        self.assertIsNone(normalize_phone_for_whatsapp("@telegram_handle"))
        self.assertIsNone(normalize_phone_for_whatsapp(""))
        self.assertIsNone(normalize_phone_for_whatsapp("12345"))
        self.assertIsNone(normalize_phone_for_whatsapp("0000000000"))
        self.assertIsNone(normalize_phone_for_whatsapp("+1234567890123456"))

        url = build_whatsapp_redirect_url("9876543210", message="Hello donor")
        self.assertTrue(url.startswith("https://wa.me/919876543210?text="))
        self.assertIn("Hello+donor", url)

    def test_accepted_requester_redirected_to_whatsapp(self):
        self.client.force_login(self.requester)
        response = self.client.get(
            reverse("contact_owner_whatsapp", kwargs={"request_id": self.item_request.id})
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith("https://wa.me/919876543210?text="))
        self.assertIn("Laptop+Backpack", response["Location"])

    def test_authorization_and_status_guards(self):
        url = reverse("contact_owner_whatsapp", kwargs={"request_id": self.item_request.id})

        # Unauthenticated users cannot trigger WhatsApp redirect
        anon_resp = self.client.get(url)
        self.assertEqual(anon_resp.status_code, 302)
        self.assertIn("/login/", anon_resp["Location"])

        # Unrelated user cannot access donor's WhatsApp redirect
        self.client.force_login(self.other_user)
        other_resp = self.client.get(url)
        self.assertRedirects(other_resp, reverse("my_requests"))

        # Pending request cannot access donor's WhatsApp redirect
        self.item_request.status = "PENDING"
        self.item_request.save()
        self.client.force_login(self.requester)
        pending_resp = self.client.get(url)
        self.assertRedirects(pending_resp, reverse("my_requests"))

    def test_missing_donor_phone_falls_back_gracefully(self):
        self.donor.profile.phone = ""
        self.donor.profile.save()

        self.client.force_login(self.requester)
        dash_resp = self.client.get(reverse("my_requests"))
        self.assertEqual(dash_resp.status_code, 200)
        self.assertContains(dash_resp, "contact-donor-trigger-btn")
        self.assertNotContains(dash_resp, "contact-donor-whatsapp-btn")

        direct_resp = self.client.get(
            reverse("contact_owner_whatsapp", kwargs={"request_id": self.item_request.id}),
            follow=True,
        )
        self.assertRedirects(direct_resp, reverse("my_requests"))
        msgs = [str(m) for m in direct_resp.context["messages"]]
        self.assertTrue(any("mobile number" in m.lower() for m in msgs))

    def test_my_requests_and_item_detail_render_whatsapp_links(self):
        self.client.force_login(self.requester)
        expected_href = reverse(
            "contact_owner_whatsapp", kwargs={"request_id": self.item_request.id}
        )

        dash_resp = self.client.get(reverse("my_requests"))
        self.assertEqual(dash_resp.status_code, 200)
        self.assertContains(dash_resp, expected_href)
        self.assertContains(dash_resp, "contact-donor-whatsapp-btn")

        detail_resp = self.client.get(
            reverse("item_detail_slug", kwargs={"pk": self.item.id, "slug": self.item.slug})
        )
        self.assertEqual(detail_resp.status_code, 200)
        self.assertContains(detail_resp, "+91 98765 43210")
        self.assertContains(detail_resp, "Message Owner on WhatsApp")
        self.assertContains(detail_resp, expected_href)

    def test_owner_mobile_number_hidden_unless_request_accepted(self):
        detail_url = reverse(
            "item_detail_slug", kwargs={"pk": self.item.id, "slug": self.item.slug}
        )
        whatsapp_url = reverse(
            "contact_owner_whatsapp", kwargs={"request_id": self.item_request.id}
        )
        phone = self.donor.profile.phone

        # Anonymous visitor on item detail and donor's public profile must never see phone
        for url in (
            detail_url,
            reverse("public_profile", kwargs={"username": self.donor.username}),
        ):
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, 200)
            self.assertNotContains(resp, phone)
            self.assertNotContains(resp, whatsapp_url)

        # Other logged-in user (even when requester has ACCEPTED request) must not see phone
        self.client.force_login(self.other_user)
        other_detail = self.client.get(detail_url)
        self.assertEqual(other_detail.status_code, 200)
        self.assertNotContains(other_detail, phone)
        self.assertNotContains(other_detail, whatsapp_url)

        # Requester with non-accepted statuses must never see phone or reach WhatsApp redirect
        self.client.force_login(self.requester)
        for non_accepted_status in ("PENDING", "REJECTED", "CANCELLED", "COMPLETED"):
            self.item_request.status = non_accepted_status
            self.item_request.save()

            resp = self.client.get(detail_url)
            self.assertEqual(resp.status_code, 200)
            self.assertNotContains(resp, phone)
            self.assertNotContains(resp, whatsapp_url)

            dash_resp = self.client.get(reverse("my_requests"))
            self.assertEqual(dash_resp.status_code, 200)
            self.assertNotContains(dash_resp, phone)
            self.assertNotContains(dash_resp, whatsapp_url)

            wa_resp = self.client.get(whatsapp_url)
            self.assertRedirects(wa_resp, reverse("my_requests"))

        # Staff user who is not the requester must not trigger WhatsApp redirect either
        staff_user = User.objects.create_user(
            username="moderator_user",
            email="mod@example.com",
            password="StrongPass123!",
            is_staff=True,
            is_active=True,
        )
        self.item_request.status = "ACCEPTED"
        self.item_request.save()
        self.client.force_login(staff_user)
        staff_wa_resp = self.client.get(whatsapp_url)
        self.assertRedirects(staff_wa_resp, reverse("my_requests"))

        # Accepted requester sees mobile number and can use WhatsApp redirect
        self.client.force_login(self.requester)
        accepted_detail = self.client.get(detail_url)
        self.assertEqual(accepted_detail.status_code, 200)
        self.assertContains(accepted_detail, phone)
        self.assertContains(accepted_detail, whatsapp_url)


@override_settings(BREVO_API_KEY="")
class ItemRequestWorkflowTests(TestCase):
    """Tests for single-acceptance enforcement, rejection handling, and public visibility."""

    def setUp(self):
        self.client = Client()
        self.donor = User.objects.create_user(
            username="workflow_donor",
            email="wdonor@example.com",
            password="StrongPass123!",
            is_active=True,
        )
        self.req_user_1 = User.objects.create_user(
            username="requester_one",
            email="req1@example.com",
            password="StrongPass123!",
            is_active=True,
        )
        self.req_user_2 = User.objects.create_user(
            username="requester_two",
            email="req2@example.com",
            password="StrongPass123!",
            is_active=True,
        )
        self.req_user_3 = User.objects.create_user(
            username="requester_three",
            email="req3@example.com",
            password="StrongPass123!",
            is_active=True,
        )
        self.category = Category.objects.create(
            name="Furniture", description="Home furniture"
        )
        self.other_category = Category.objects.create(
            name="Books", description="Community books"
        )
        self.item = Item.objects.create(
            donor=self.donor,
            category=self.category,
            title="Wooden Study Desk",
            description="Sturdy oak study desk in good shape.",
            condition="GOOD",
            pickup_location="Maple Avenue",
            status="AVAILABLE",
            moderation_status="APPROVED",
        )

    def test_multiple_users_can_request_available_item(self):
        for user, msg in (
            (self.req_user_1, "I need this for my study room."),
            (self.req_user_2, "Can pick up this evening."),
            (self.req_user_3, "Available tomorrow morning."),
        ):
            self.client.force_login(user)
            resp = self.client.post(
                reverse("request_item", kwargs={"pk": self.item.pk}),
                {"message": msg, "contact_info": "555-1234"},
            )
            self.assertEqual(resp.status_code, 302)

        self.item.refresh_from_db()
        self.assertEqual(self.item.status, "AVAILABLE")
        self.assertEqual(
            self.item.requests.filter(status="PENDING").count(), 3
        )

    def test_accepting_one_request_rejects_other_pending_requests_and_notifies(self):
        req1 = ItemRequest.objects.create(
            item=self.item,
            requester=self.req_user_1,
            message="First request",
            status="PENDING",
        )
        req2 = ItemRequest.objects.create(
            item=self.item,
            requester=self.req_user_2,
            message="Second request",
            status="PENDING",
        )
        req3 = ItemRequest.objects.create(
            item=self.item,
            requester=self.req_user_3,
            message="Already cancelled earlier",
            status="CANCELLED",
        )

        mail.outbox.clear()
        self.client.force_login(self.donor)
        resp = self.client.get(
            reverse("respond_request", kwargs={"request_id": req1.id, "action": "accept"})
        )
        self.assertEqual(resp.status_code, 302)

        self.item.refresh_from_db()
        req1.refresh_from_db()
        req2.refresh_from_db()
        req3.refresh_from_db()

        self.assertEqual(self.item.status, "REQUESTED")
        self.assertEqual(req1.status, "ACCEPTED")
        self.assertEqual(req2.status, "REJECTED")
        self.assertEqual(req3.status, "CANCELLED")
        self.assertEqual(
            self.item.requests.filter(status="ACCEPTED").count(), 1
        )

        # Accepted user receives acceptance email; only previously PENDING req2 receives rejection email
        self.assertEqual(len(mail.outbox), 2)
        subjects_by_recipient = {m.to[0]: m.subject for m in mail.outbox}
        self.assertIn("Accepted", subjects_by_recipient[self.req_user_1.email])
        self.assertIn("Update on your request", subjects_by_recipient[self.req_user_2.email])
        self.assertNotIn(self.req_user_3.email, subjects_by_recipient)

    def test_cannot_accept_second_request_after_one_already_accepted(self):
        req1 = ItemRequest.objects.create(
            item=self.item,
            requester=self.req_user_1,
            message="First request",
            status="PENDING",
        )
        req2 = ItemRequest.objects.create(
            item=self.item,
            requester=self.req_user_2,
            message="Second request",
            status="PENDING",
        )

        self.client.force_login(self.donor)
        self.client.get(
            reverse("respond_request", kwargs={"request_id": req1.id, "action": "accept"})
        )

        # Attempt to accept req2 (now REJECTED) or a stray PENDING req3 after req1 is accepted
        req3 = ItemRequest.objects.create(
            item=self.item,
            requester=self.req_user_3,
            message="Stale pending request",
            status="PENDING",
        )

        mail.outbox.clear()
        resp_rej = self.client.get(
            reverse("respond_request", kwargs={"request_id": req2.id, "action": "accept"})
        )
        resp_pending = self.client.get(
            reverse("respond_request", kwargs={"request_id": req3.id, "action": "accept"})
        )
        # Re-accepting already accepted req1 should also be a no-op with no duplicate email
        resp_same = self.client.get(
            reverse("respond_request", kwargs={"request_id": req1.id, "action": "accept"})
        )

        self.assertEqual(resp_rej.status_code, 302)
        self.assertEqual(resp_pending.status_code, 302)
        self.assertEqual(resp_same.status_code, 302)

        self.item.refresh_from_db()
        req1.refresh_from_db()
        req2.refresh_from_db()
        req3.refresh_from_db()

        self.assertEqual(self.item.status, "REQUESTED")
        self.assertEqual(req1.status, "ACCEPTED")
        self.assertEqual(req2.status, "REJECTED")
        self.assertEqual(req3.status, "PENDING")
        self.assertEqual(self.item.requests.filter(status="ACCEPTED").count(), 1)
        self.assertEqual(len(mail.outbox), 0)

        # A new user cannot submit a request while the item is REQUESTED
        new_user = User.objects.create_user(
            username="late_requester",
            email="late@example.com",
            password="StrongPass123!",
            is_active=True,
        )
        self.client.force_login(new_user)
        late_resp = self.client.post(
            reverse("request_item", kwargs={"pk": self.item.pk}),
            {"message": "Still available?", "contact_info": "555-9999"},
        )
        self.assertEqual(late_resp.status_code, 302)
        self.assertFalse(
            ItemRequest.objects.filter(item=self.item, requester=new_user).exists()
        )

    def test_stale_in_memory_accept_race_cannot_produce_two_accepted_requests(self):
        from .views import _accept_item_request

        req1 = ItemRequest.objects.create(
            item=self.item,
            requester=self.req_user_1,
            message="First",
            status="PENDING",
        )
        req2 = ItemRequest.objects.create(
            item=self.item,
            requester=self.req_user_2,
            message="Second",
            status="PENDING",
        )

        # Snapshot stale in-memory objects before req1 is accepted
        stale_item = Item.objects.get(pk=self.item.pk)
        stale_req2 = ItemRequest.objects.get(pk=req2.pk)

        outcome1, _ = _accept_item_request(self.item, req1)
        self.assertEqual(outcome1, "accepted")

        # Second call with stale in-memory state must fail safely
        outcome2, rejected2 = _accept_item_request(stale_item, stale_req2)
        self.assertIn(outcome2, ("conflict_accepted", "item_unavailable", "invalid_status"))
        self.assertEqual(rejected2, [])
        self.assertEqual(self.item.requests.filter(status="ACCEPTED").count(), 1)

    def test_rejecting_pending_request_preserves_requested_status_when_another_accepted(self):
        req1 = ItemRequest.objects.create(
            item=self.item,
            requester=self.req_user_1,
            message="Accepted requester",
            status="ACCEPTED",
        )
        self.item.status = "REQUESTED"
        self.item.save()

        req2 = ItemRequest.objects.create(
            item=self.item,
            requester=self.req_user_2,
            message="Unrelated pending request",
            status="PENDING",
        )

        mail.outbox.clear()
        self.client.force_login(self.donor)
        resp = self.client.get(
            reverse("respond_request", kwargs={"request_id": req2.id, "action": "reject"})
        )
        self.assertEqual(resp.status_code, 302)

        self.item.refresh_from_db()
        req1.refresh_from_db()
        req2.refresh_from_db()

        self.assertEqual(req2.status, "REJECTED")
        self.assertEqual(req1.status, "ACCEPTED")
        self.assertEqual(self.item.status, "REQUESTED")
        self.assertEqual(len(mail.outbox), 1)

    def test_rejecting_pending_request_with_no_accepted_leaves_item_available(self):
        req1 = ItemRequest.objects.create(
            item=self.item,
            requester=self.req_user_1,
            message="Decline me",
            status="PENDING",
        )

        mail.outbox.clear()
        self.client.force_login(self.donor)
        resp = self.client.get(
            reverse("respond_request", kwargs={"request_id": req1.id, "action": "reject"})
        )
        self.assertEqual(resp.status_code, 302)

        self.item.refresh_from_db()
        req1.refresh_from_db()
        self.assertEqual(req1.status, "REJECTED")
        self.assertEqual(self.item.status, "AVAILABLE")
        self.assertEqual(len(mail.outbox), 1)

        # Repeating reject on an already rejected request sends no duplicate email
        mail.outbox.clear()
        self.client.get(
            reverse("respond_request", kwargs={"request_id": req1.id, "action": "reject"})
        )
        self.assertEqual(len(mail.outbox), 0)

    def test_mark_available_blocked_while_accepted_request_exists(self):
        ItemRequest.objects.create(
            item=self.item,
            requester=self.req_user_1,
            message="Accepted",
            status="ACCEPTED",
        )
        self.item.status = "REQUESTED"
        self.item.save()

        self.client.force_login(self.donor)
        resp = self.client.post(reverse("mark_available", kwargs={"pk": self.item.pk}))
        self.assertEqual(resp.status_code, 302)

        self.item.refresh_from_db()
        self.assertEqual(self.item.status, "REQUESTED")

    def test_rejecting_accepted_request_restores_available_unless_another_accepted(self):
        req1 = ItemRequest.objects.create(
            item=self.item,
            requester=self.req_user_1,
            message="Accepted first",
            status="ACCEPTED",
        )
        self.item.status = "REQUESTED"
        self.item.save()

        # Rejecting the sole accepted request restores item to AVAILABLE
        self.client.force_login(self.donor)
        resp = self.client.get(
            reverse("respond_request", kwargs={"request_id": req1.id, "action": "reject"})
        )
        self.assertEqual(resp.status_code, 302)
        self.item.refresh_from_db()
        req1.refresh_from_db()
        self.assertEqual(req1.status, "REJECTED")
        self.assertEqual(self.item.status, "AVAILABLE")

        # Guard: if legacy data somehow has another ACCEPTED request, rejecting one keeps REQUESTED
        req2 = ItemRequest.objects.create(
            item=self.item,
            requester=self.req_user_2,
            message="Accepted 2",
            status="ACCEPTED",
        )
        req3 = ItemRequest.objects.create(
            item=self.item,
            requester=self.req_user_3,
            message="Accepted 3",
            status="ACCEPTED",
        )
        self.item.status = "REQUESTED"
        self.item.save()

        self.client.get(
            reverse("respond_request", kwargs={"request_id": req2.id, "action": "reject"})
        )
        self.item.refresh_from_db()
        req2.refresh_from_db()
        req3.refresh_from_db()
        self.assertEqual(req2.status, "REJECTED")
        self.assertEqual(req3.status, "ACCEPTED")
        self.assertEqual(self.item.status, "REQUESTED")

    def test_completing_accepted_request_updates_request_and_item(self):
        req1 = ItemRequest.objects.create(
            item=self.item,
            requester=self.req_user_1,
            message="I can collect today",
            status="PENDING",
        )

        self.client.force_login(self.donor)
        self.client.get(
            reverse("respond_request", kwargs={"request_id": req1.id, "action": "accept"})
        )

        mail.outbox.clear()
        complete_resp = self.client.get(
            reverse("respond_request", kwargs={"request_id": req1.id, "action": "complete"})
        )
        self.assertEqual(complete_resp.status_code, 302)

        self.item.refresh_from_db()
        req1.refresh_from_db()
        self.assertEqual(req1.status, "COMPLETED")
        self.assertEqual(self.item.status, "GIVEN_AWAY")
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Completed", mail.outbox[0].subject)

        # Completing an already completed or rejected request is blocked
        req2 = ItemRequest.objects.create(
            item=self.item,
            requester=self.req_user_2,
            message="Not accepted",
            status="REJECTED",
        )
        mail.outbox.clear()
        self.client.get(
            reverse("respond_request", kwargs={"request_id": req2.id, "action": "complete"})
        )
        req2.refresh_from_db()
        self.assertEqual(req2.status, "REJECTED")
        self.assertEqual(len(mail.outbox), 0)

    def test_public_explore_and_search_only_display_available_items(self):
        requested_item = Item.objects.create(
            donor=self.donor,
            category=self.category,
            title="Requested Oak Chair",
            description="Oak chair already accepted.",
            condition="GOOD",
            pickup_location="Maple Avenue",
            status="REQUESTED",
            moderation_status="APPROVED",
        )
        given_item = Item.objects.create(
            donor=self.donor,
            category=self.category,
            title="Given Away Table",
            description="Oak table already collected.",
            condition="GOOD",
            pickup_location="Maple Avenue",
            status="GIVEN_AWAY",
            moderation_status="APPROVED",
        )
        cancelled_item = Item.objects.create(
            donor=self.donor,
            category=self.category,
            title="Cancelled Shelf",
            description="Oak shelf cancelled.",
            condition="GOOD",
            pickup_location="Maple Avenue",
            status="CANCELLED",
            moderation_status="APPROVED",
        )
        other_available_item = Item.objects.create(
            donor=self.donor,
            category=self.other_category,
            title="Python Cookbook",
            description="Clean paperback copy.",
            condition="LIKE_NEW",
            pickup_location="Pine Street",
            status="AVAILABLE",
            moderation_status="APPROVED",
        )

        home_url = reverse("home")

        # Default public explore view shows only AVAILABLE items
        default_resp = self.client.get(home_url)
        self.assertEqual(default_resp.status_code, 200)
        self.assertContains(default_resp, self.item.title)
        self.assertContains(default_resp, other_available_item.title)
        self.assertNotContains(default_resp, requested_item.title)
        self.assertNotContains(default_resp, given_item.title)
        self.assertNotContains(default_resp, cancelled_item.title)

        # ?status=REQUESTED and ?status=ALL cannot expose unavailable items
        for status_param in ("REQUESTED", "ALL", "GIVEN_AWAY", "CANCELLED"):
            resp = self.client.get(home_url, {"status": status_param})
            self.assertEqual(resp.status_code, 200)
            self.assertContains(resp, self.item.title)
            self.assertNotContains(resp, requested_item.title)
            self.assertNotContains(resp, given_item.title)
            self.assertNotContains(resp, cancelled_item.title)

        # Search query with ?status=ALL still returns only matching AVAILABLE items
        search_resp = self.client.get(home_url, {"q": "Oak", "status": "ALL"})
        self.assertEqual(search_resp.status_code, 200)
        self.assertContains(search_resp, self.item.title)
        self.assertNotContains(search_resp, requested_item.title)
        self.assertNotContains(search_resp, given_item.title)
        self.assertNotContains(search_resp, cancelled_item.title)
        self.assertNotContains(search_resp, other_available_item.title)

        # Category filter with ?status=REQUESTED still returns only AVAILABLE items in that category
        cat_resp = self.client.get(
            home_url, {"category": self.category.slug, "status": "REQUESTED"}
        )
        self.assertEqual(cat_resp.status_code, 200)
        self.assertContains(cat_resp, self.item.title)
        self.assertNotContains(cat_resp, requested_item.title)
        self.assertNotContains(cat_resp, other_available_item.title)

        # Donor's private dashboard still shows REQUESTED and GIVEN_AWAY items
        self.client.force_login(self.donor)
        my_listings_resp = self.client.get(reverse("my_listings"))
        self.assertEqual(my_listings_resp.status_code, 200)
        self.assertContains(my_listings_resp, self.item.title)
        self.assertContains(my_listings_resp, requested_item.title)
        self.assertContains(my_listings_resp, given_item.title)


@override_settings(BREVO_API_KEY="")
class ConcurrentItemRequestTests(TransactionTestCase):
    """Concurrency tests verifying simultaneous acceptance cannot yield multiple ACCEPTED requests."""

    def setUp(self):
        self.donor = User.objects.create_user(
            username="concurrent_donor",
            email="cdonor@example.com",
            password="StrongPass123!",
            is_active=True,
        )
        self.user_a = User.objects.create_user(
            username="concurrent_a",
            email="ca@example.com",
            password="StrongPass123!",
            is_active=True,
        )
        self.user_b = User.objects.create_user(
            username="concurrent_b",
            email="cb@example.com",
            password="StrongPass123!",
            is_active=True,
        )
        self.category = Category.objects.create(name="Tools", description="Hand tools")
        self.item = Item.objects.create(
            donor=self.donor,
            category=self.category,
            title="Cordless Drill",
            description="Works well with battery charger.",
            condition="GOOD",
            pickup_location="Oak Street",
            status="AVAILABLE",
            moderation_status="APPROVED",
        )
        self.req_a = ItemRequest.objects.create(
            item=self.item,
            requester=self.user_a,
            message="Need for home repair",
            status="PENDING",
        )
        self.req_b = ItemRequest.objects.create(
            item=self.item,
            requester=self.user_b,
            message="Can pick up now",
            status="PENDING",
        )

    def test_simultaneous_acceptance_produces_only_one_accepted_request(self):
        client_a = Client()
        client_b = Client()
        client_a.force_login(self.donor)
        client_b.force_login(self.donor)

        mail.outbox.clear()
        barrier = threading.Barrier(2)
        errors = []
        statuses = []

        def accept_in_thread(client, req_id):
            try:
                barrier.wait(timeout=5)
                resp = client.get(
                    reverse(
                        "respond_request",
                        kwargs={"request_id": req_id, "action": "accept"},
                    )
                )
                statuses.append(resp.status_code)
            except Exception:
                errors.append(traceback.format_exc())
            finally:
                connections.close_all()

        t1 = threading.Thread(target=accept_in_thread, args=(client_a, self.req_a.id))
        t2 = threading.Thread(target=accept_in_thread, args=(client_b, self.req_b.id))
        t1.start()
        t2.start()
        t1.join(timeout=15)
        t2.join(timeout=15)

        self.item.refresh_from_db()
        self.req_a.refresh_from_db()
        self.req_b.refresh_from_db()

        accepted_count = ItemRequest.objects.filter(
            item=self.item, status="ACCEPTED"
        ).count()
        rejected_count = ItemRequest.objects.filter(
            item=self.item, status="REJECTED"
        ).count()

        self.assertEqual(errors, [])
        self.assertEqual(statuses, [302, 302])
        self.assertEqual(self.item.status, "REQUESTED")
        self.assertEqual(accepted_count, 1)
        self.assertEqual(rejected_count, 1)
        self.assertEqual(len(mail.outbox), 2)
