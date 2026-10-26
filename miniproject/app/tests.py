from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
import requests

from .emails import send_reusehub_email
from .forms import ItemForm, ReuseHubPasswordResetForm, UserRegisterForm
from .models import Category, EmailOTP, Item, ItemRequest, Report, SupportInquiry

# test.py is used to automatically test whether your features are working correctly. Your file contains a ReuseHubTests(TestCase) class with tests for pages, requests, admin access, profiles, OTP, emails, password reset, etc


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
        response = self.client.get(reverse("item_detail", kwargs={"pk": self.item.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Vintage Lamp")
        self.assertContains(response, "Downtown Library")

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
