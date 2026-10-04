import secrets
from datetime import timedelta
from django.contrib.auth.models import User
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from django.utils.text import slugify


class Category(models.Model):
    """Categories for organizing passed-on items."""

    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "Categories"
        ordering = ["name"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Item(models.Model):
    """Items listed by users to give away for free or repair/reuse."""

    CONDITION_CHOICES = [  # noqa: RUF012
        ("NEW", "Brand New"),
        ("LIKE_NEW", "Like New"),
        ("GOOD", "Good Condition"),
        ("FAIR", "Fair / Usable"),
        ("REPAIRABLE", "Needs Repair / Repairable"),
    ]

    STATUS_CHOICES = [  # noqa: RUF012
        ("AVAILABLE", "Available"),
        ("REQUESTED", "Request Pending"),
        ("GIVEN_AWAY", "Given Away"),
        ("CANCELLED", "Cancelled"),
    ]

    MODERATION_CHOICES = [  # noqa: RUF012
        ("APPROVED", "Approved"),
        ("PENDING", "Pending Moderation"),
        ("FLAGGED", "Flagged for Review"),
        ("REJECTED", "Rejected"),
    ]

    donor = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="donated_items"
    )
    category = models.ForeignKey(
        Category, on_delete=models.SET_NULL, null=True, blank=True, related_name="items"
    )
    title = models.CharField(max_length=200)
    description = models.TextField()
    condition = models.CharField(
        max_length=20, choices=CONDITION_CHOICES, default="GOOD"
    )
    is_repairable = models.BooleanField(
        default=False,
        help_text="Flag this item if it can be repaired, restored, or upcycled.",
    )
    repair_details = models.TextField(
        blank=True, help_text="Describe what needs repair or ideas for restoration."
    )
    pickup_location = models.CharField(
        max_length=255, help_text="Pickup landmark, neighborhood, or general area."
    )
    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Pickup latitude coordinate",
    )
    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Pickup longitude coordinate",
    )
    image = models.ImageField(upload_to="items/%Y/%m/", blank=True, null=True)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="AVAILABLE"
    )
    moderation_status = models.CharField(
        max_length=20, choices=MODERATION_CHOICES, default="APPROVED"
    )
    moderation_notes = models.TextField(blank=True)
    views_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    @property
    def is_available(self):
        return self.status == "AVAILABLE" and self.moderation_status == "APPROVED"

    @property
    def all_images(self):
        """Return list of all associated photos, falling back to primary image if none in gallery."""
        gallery = list(self.images.all())
        if gallery:
            return gallery
        if self.image:
            # Fallback wrapper with same attribute interface (.image.url)
            class ImageFallback:
                def __init__(self, img):
                    self.image = img
                    self.id = 0
            return [ImageFallback(self.image)]
        return []


class ItemImage(models.Model):
    """Multiple photos for an item listing (up to 5 images per item)."""

    item = models.ForeignKey(
        Item, on_delete=models.CASCADE, related_name="images"
    )
    image = models.ImageField(upload_to="items/%Y/%m/")
    is_cover = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-is_cover", "id"]

    def __str__(self):
        cover_tag = " (Cover)" if self.is_cover else ""
        return f"Photo #{self.id} for {self.item.title}{cover_tag}"


class ItemRequest(models.Model):
    """Requests submitted by users to claim an item."""

    STATUS_CHOICES = [  # noqa: RUF012
        ("PENDING", "Pending"),
        ("ACCEPTED", "Accepted"),
        ("REJECTED", "Rejected"),
        ("COMPLETED", "Collected / Completed"),
        ("CANCELLED", "Cancelled"),
    ]

    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="requests")
    requester = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="item_requests"
    )
    message = models.TextField(
        help_text="Introduce yourself and explain why you'd like this item or when you can collect it."
    )
    contact_info = models.CharField(
        max_length=150, blank=True, help_text="Phone number or preferred contact method"
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="PENDING")
    donor_notes = models.TextField(
        blank=True, help_text="Instructions or response from the donor"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        unique_together = ("item", "requester") #  prevents spamming multiple requests on the same item.

    def __str__(self):
        return f"{self.requester.username} -> {self.item.title} ({self.status})"


class Report(models.Model):
    """Reports filed by users regarding inappropriate listings or profiles."""

    REASON_CHOICES = [  # noqa: RUF012
        ("INAPPROPRIATE", "Inappropriate or Offensive Content"),
        ("SPAM_COMMERCIAL", "Spam / Commercial Selling / Not Free"),
        ("HAZARDOUS", "Hazardous or Prohibited Item"),
        ("MISLEADING", "Misleading Information or Condition"),
        ("HARASSMENT", "Rude, Abusive, or Harassing Behavior"),
        ("NO_SHOW", "No-show / Unreliable Exchange"),
        ("PROFILE_VIOLATION", "Inappropriate Profile Details or Photo"),
        ("OTHER", "Other Community Guideline Violation"),
    ]

    STATUS_CHOICES = [  # noqa: RUF012
        ("PENDING", "Pending Review"),
        ("RESOLVED", "Resolved (Action Taken)"),
        ("DISMISSED", "Dismissed (Listing Approved)"),
    ]

    item = models.ForeignKey(
        Item, on_delete=models.CASCADE, null=True, blank=True, related_name="reports"
    )
    reported_user = models.ForeignKey(
        User, on_delete=models.CASCADE, null=True, blank=True, related_name="reports_against"
    )
    reported_by = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="reports_made"
    )
    reason = models.CharField(max_length=40, choices=REASON_CHOICES)
    details = models.TextField(help_text="Please describe the issue in detail.")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="PENDING")
    admin_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        if self.item:
            target = f"listing '{self.item.title}'"
        elif self.reported_user:
            target = f"user '{self.reported_user.username}'"
        else:
            target = "general"
        return f"Report #{self.id} on {target} by {self.reported_by.username}"


class SupportInquiry(models.Model):
    """Direct support inquiries, technical bug reports, and messages sent via the Help Center."""

    STATUS_CHOICES = [  # noqa: RUF012
        ("PENDING", "Pending Review"),
        ("IN_PROGRESS", "In Progress"),
        ("RESOLVED", "Resolved"),
        ("CLOSED", "Closed"),
    ]

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="support_inquiries"
    )
    name = models.CharField(max_length=150)
    email = models.EmailField()
    subject = models.CharField(max_length=150)
    message = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="PENDING")
    admin_response = models.TextField(
        blank=True, help_text="Notes or response sent to the user by staff."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Support Inquiry"
        verbose_name_plural = "Support Inquiries"

    def __str__(self):
        return f"Support #{self.id} [{self.status}] '{self.subject}' from @{self.user.username}"


class UserProfile(models.Model):
    """User profile for community members."""

    # This creates a one-to-one relationship between Django's User and another model.
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    bio = models.TextField(
        blank=True, help_text="Tell the community a little about yourself."
    )
    phone = models.CharField(max_length=30, blank=True)
    location = models.CharField(
        max_length=150, blank=True, help_text="City or neighborhood."
    )
    avatar = models.ImageField(upload_to="avatars/", blank=True, null=True)
    is_verified = models.BooleanField(
        default=False, help_text="Designates whether this user has a verified community profile."
    )
    email_verified = models.BooleanField(
        default=False, help_text="Designates whether the user verified their email address via OTP."
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username}'s Profile"


class EmailOTP(models.Model):
    """Temporary One-Time Password (OTP) for email verification and security flows."""

    PURPOSE_CHOICES = [  # noqa: RUF012
        ("REGISTRATION", "Account Registration"),
        ("PASSWORD_RESET", "Password Reset"),
        ("EMAIL_CHANGE", "Email Address Change"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="otp_codes")
    email = models.EmailField()
    code = models.CharField(max_length=6)
    purpose = models.CharField(max_length=30, choices=PURPOSE_CHOICES, default="REGISTRATION")
    attempts = models.PositiveSmallIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(default=5)
    is_used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Email OTP"
        verbose_name_plural = "Email OTPs"
        indexes = [  # noqa: RUF012
            models.Index(fields=["user", "purpose", "is_used"]),
            models.Index(fields=["email", "code"]),
        ]

    def __str__(self):
        status = "Used" if self.is_used else ("Expired" if self.is_expired() else "Active")
        return f"OTP for {self.email} ({self.purpose}) - {status}"

    def is_expired(self):
        return timezone.now() > self.expires_at

    def is_valid(self):
        return not self.is_used and not self.is_expired() and self.attempts < self.max_attempts

    @classmethod
    def generate_otp(cls, user, email, purpose="REGISTRATION", validity_minutes=15):
        """Generate a 6-digit cryptographic random OTP, invalidating previous unused ones."""
        cls.objects.filter(user=user, purpose=purpose, is_used=False).update(is_used=True)
        code = f"{secrets.SystemRandom().randint(100000, 999999):06d}"
        expires_at = timezone.now() + timedelta(minutes=validity_minutes)
        return cls.objects.create(
            user=user,
            email=email,
            code=code,
            purpose=purpose,
            expires_at=expires_at,
        )


class UserReview(models.Model):
    """1-5 star community rating and short review after a completed exchange."""

    RATING_CHOICES = [  # noqa: RUF012
        (1, "1 - Poor"),
        (2, "2 - Fair"),
        (3, "3 - Good"),
        (4, "4 - Very Good"),
        (5, "5 - Excellent"),
    ]

    reviewer = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="reviews_given"
    )
    reviewed_user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="reviews_received"
    )
    item_request = models.ForeignKey(
        ItemRequest, on_delete=models.CASCADE, related_name="reviews"
    )
    rating = models.PositiveSmallIntegerField(
        choices=RATING_CHOICES,
        default=5,
        help_text="Community rating from 1 to 5 stars."
    )
    comment = models.TextField(
        blank=True,
        help_text="Short review about your experience with this member."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        unique_together = ("reviewer", "item_request") # guarantees only one review can be submitted per completed exchange.

    def __str__(self):
        return f"{self.reviewer.username} rated {self.reviewed_user.username} {self.rating}★"


@receiver(post_save, sender=User)
#  automatically creates a UserProfile whenever a new Django User is registered.
def create_or_save_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.get_or_create(user=instance)
    else:
        update_fields = kwargs.get("update_fields")
        if update_fields and "last_login" in update_fields:
            return
        if hasattr(instance, "profile"):
            instance.profile.save()
