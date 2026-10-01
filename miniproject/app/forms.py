import os
from django import forms
from django.contrib.auth.models import User
from .models import Item, ItemRequest, Report, Category, UserProfile, UserReview


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault(
            "widget",
            MultipleFileInput(
                attrs={
                    "class": "form-file-input",
                    "id": "id_images",
                    "accept": ".jpg,.jpeg,.png,.webp,.gif,image/jpeg,image/png,image/webp,image/gif",
                    "multiple": True,
                }
            ),
        )
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single_file_clean = super().clean
        if isinstance(data, (list, tuple)):
            result = [single_file_clean(d, initial) for d in data]
        else:
            result = single_file_clean(data, initial)
        return result


class ItemForm(forms.ModelForm):
    images = MultipleFileField(
        required=False,
        help_text="Upload up to 5 photos. Formats: JPEG (.jpg, .jpeg), PNG (.png), WebP (.webp), GIF (.gif). Max 10MB per image."
    )

    class Meta:
        model = Item
        fields = [
            'title',
            'category',
            'condition',
            'is_repairable',
            'repair_details',
            'pickup_location',
            'latitude',
            'longitude',
            'description',
        ]
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'e.g. Wooden Dining Table, Working Vintage Radio...'
            }),
            'category': forms.Select(attrs={
                'class': 'form-select'
            }),
            'condition': forms.Select(attrs={
                'class': 'form-select'
            }),
            'is_repairable': forms.CheckboxInput(attrs={
                'class': 'form-checkbox',
                'id': 'id_is_repairable'
            }),
            'repair_details': forms.Textarea(attrs={
                'class': 'form-textarea',
                'rows': 3,
                'placeholder': 'Explain what part needs fixing, tools required, or ideas for repair/upcycling...'
            }),
            'pickup_location': forms.TextInput(attrs={
                'class': 'form-input',
                'id': 'id_pickup_location',
                'placeholder': 'e.g., Near West End Library, 5th Avenue'
            }),
            'latitude': forms.HiddenInput(attrs={'id': 'id_latitude'}),
            'longitude': forms.HiddenInput(attrs={'id': 'id_longitude'}),
            'description': forms.Textarea(attrs={
                'class': 'form-textarea',
                'rows': 4,
                'placeholder': 'Provide helpful details about size, history, usage, and any other notes...'
            }),
        }

    def clean(self):
        cleaned_data = super().clean()
        files = self.files.getlist('images')

        existing_count = 0
        if self.instance and self.instance.pk:
            delete_ids = self.data.getlist('delete_images')
            existing_count = self.instance.images.exclude(id__in=delete_ids).count()

        total_count = existing_count + len(files)
        if total_count > 5:
            self.add_error(
                'images',
                f"You can have at most 5 images in total (currently {existing_count} existing + {len(files)} new selected)."
            )

        valid_extensions = ('.jpg', '.jpeg', '.png', '.webp', '.gif')

        # image format checking
        for f in files:
            ext = os.path.splitext(f.name)[1].lower()
            if ext not in valid_extensions:
                self.add_error(
                    'images',
                    f"'{f.name}' has an unsupported format. Allowed formats: JPEG (.jpg, .jpeg), PNG (.png), WebP (.webp), and GIF (.gif)."
                )
                break
            # image size checking
            if f.size > 10 * 1024 * 1024:
                self.add_error(
                    'images',
                    f"'{f.name}' exceeds the 10MB limit (size: {f.size / (1024 * 1024):.1f}MB)."
                )
                break

        return cleaned_data


class ItemRequestForm(forms.ModelForm):
    class Meta:
        model = ItemRequest
        fields = ['message', 'contact_info']
        widgets = {
            'message': forms.Textarea(attrs={
                'class': 'form-textarea',
                'rows': 4,
                'placeholder': 'Hello! I would love to make use of this item because... I can pick it up on...'
            }),
            'contact_info': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'Phone number or preferred contact handle'
            }),
        }


class ReportForm(forms.ModelForm):
    class Meta:
        model = Report
        fields = ['reason', 'details']
        widgets = {
            'reason': forms.Select(attrs={'class': 'form-select'}),
            'details': forms.Textarea(attrs={
                'class': 'form-textarea',
                'rows': 4,
                'placeholder': 'Please specify why this listing violates community standards or needs moderation...'
            }),
        }


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['name', 'description']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Category Name'}),
            'description': forms.Textarea(attrs={'class': 'form-textarea', 'rows': 3, 'placeholder': 'Category description...'}),
        }


from django.contrib.auth.forms import PasswordResetForm, SetPasswordForm
from django.core.validators import validate_email


class UserRegisterForm(forms.ModelForm):
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={'class': 'form-input', 'placeholder': 'name@example.com'}),
        label="Email Address",
        help_text="A temporary 6-digit OTP will be sent here to verify your access."
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-input', 'placeholder': 'Create a password'}),
        label="Password"
    )
    confirm_password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-input', 'placeholder': 'Confirm your password'}),
        label="Confirm Password"
    )

    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Choose a username'}),
            'first_name': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'First name'}),
            'last_name': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Last name'}),
        }

    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip().lower()
        try:
            validate_email(email)
        except forms.ValidationError:
            raise forms.ValidationError("Please provide a valid email format (e.g. name@domain.com).")

        # Check if an active verified user already uses this email
        if User.objects.filter(email__iexact=email, is_active=True).exists():
            raise forms.ValidationError(
                "An account with this email address is already registered. Please sign in or reset your password."
            )
        return email

    def clean_username(self):
        username = self.cleaned_data.get('username', '').strip()
        # If user exists and is active, raise error
        if User.objects.filter(username__iexact=username, is_active=True).exists():
            raise forms.ValidationError("A user with this username already exists.")
        return username

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        confirm_password = cleaned_data.get('confirm_password')

        if password and confirm_password and password != confirm_password:
            self.add_error('confirm_password', "Passwords do not match.")
        return cleaned_data


class VerifyOTPForm(forms.Form):
    """Form to submit the 6-digit email verification code."""
    otp = forms.CharField(
        max_length=6,
        min_length=6,
        widget=forms.TextInput(attrs={
            'class': 'form-input otp-code-input',
            'placeholder': '123456',
            'maxlength': '6',
            'pattern': r'\d{6}',
            'inputmode': 'numeric',
            'autocomplete': 'one-time-code',
            'autofocus': 'autofocus',
        }),
        label="6-Digit Verification Code",
        help_text="Enter the 6-digit code sent to your email address."
    )

    def clean_otp(self):
        otp = self.cleaned_data.get('otp', '').strip()
        if not otp.isdigit() or len(otp) != 6:
            raise forms.ValidationError("Please enter a valid 6-digit numeric verification code.")
        return otp


class ReuseHubPasswordResetForm(PasswordResetForm):
    """Clean custom password reset form matching ReuseHub design system."""
    email = forms.EmailField(
        max_length=254,
        widget=forms.EmailInput(attrs={
            'class': 'form-input',
            'placeholder': 'Enter your registered email address',
            'autocomplete': 'email',
            'autofocus': 'autofocus',
        }),
        label="Email Address",
        help_text="We'll send password reset instructions to this email if an account exists."
    )


class ReuseHubSetPasswordForm(SetPasswordForm):
    """Custom set-password form matching ReuseHub design system."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-input'
            if 'placeholder' not in field.widget.attrs:
                field.widget.attrs['placeholder'] = field.label


class UserProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ['bio', 'phone', 'location', 'avatar']
        widgets = {
            'bio': forms.Textarea(attrs={'class': 'form-textarea', 'rows': 3, 'placeholder': 'Short bio about yourself...'}),
            'phone': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Phone number'}),
            'location': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'City, state, or area'}),
            'avatar': forms.FileInput(attrs={'class': 'form-file-input', 'accept': 'image/*'}),
        }


class UserReviewForm(forms.ModelForm):
    RATING_CHOICES = [
        (5, "5 ★★★★★ — Excellent & Super Friendly"),
        (4, "4 ★★★★☆ — Very Good & Smooth Exchange"),
        (3, "3 ★★★☆☆ — Good / Satisfactory"),
        (2, "2 ★★☆☆☆ — Fair / Minor Issues"),
        (1, "1 ★☆☆☆☆ — Poor / Disappointing"),
    ]
    rating = forms.TypedChoiceField(
        choices=RATING_CHOICES,
        coerce=int,
        initial=5,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label="Community Rating"
    )

    class Meta:
        model = UserReview
        fields = ['rating', 'comment']
        widgets = {
            'comment': forms.Textarea(attrs={
                'class': 'form-textarea',
                'rows': 3,
                'placeholder': 'Share how the exchange went (punctuality, communication, item condition, friendliness)...',
            }),
        }


class UserReportForm(forms.ModelForm):
    USER_REASON_CHOICES = [
        ("HARASSMENT", "Rude, Abusive, or Harassing Behavior"),
        ("SPAM_COMMERCIAL", "Commercial Selling / Asking for Money"),
        ("NO_SHOW", "No-show / Repeatedly Missed Pickup"),
        ("PROFILE_VIOLATION", "Inappropriate Profile Details or Photo"),
        ("INAPPROPRIATE", "Offensive or Inappropriate Content"),
        ("OTHER", "Other Community Guideline Violation"),
    ]
    reason = forms.ChoiceField(
        choices=USER_REASON_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label="Reason for Report"
    )

    class Meta:
        model = Report
        fields = ['reason', 'details']
        widgets = {
            'details': forms.Textarea(attrs={
                'class': 'form-textarea',
                'rows': 4,
                'placeholder': 'Please describe the incident or behavior in detail to assist our moderation team...',
            }),
        }

