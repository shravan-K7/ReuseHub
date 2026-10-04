from datetime import timedelta
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from .community import get_user_badges, get_user_stats
from .emails import (
    send_admin_or_account_notification,
    send_item_request_notification,
    send_item_status_update,
    send_password_reset_email,
    send_registration_otp_email,
    send_request_status_notification,
)
from .forms import (
    CategoryForm,
    ItemForm,
    ItemRequestForm,
    ReportForm,
    ReuseHubPasswordResetForm,
    ReuseHubSetPasswordForm,
    UserProfileForm,
    UserRegisterForm,
    UserReportForm,
    UserReviewForm,
    VerifyOTPForm,
)
from .models import (
    Category,
    EmailOTP,
    Item,
    ItemImage,
    ItemRequest,
    Report,
    SupportInquiry,
    UserProfile,
    UserReview,
)


def global_context(request):
    """Context processor to provide global stats and navigation data."""
    categories = Category.objects.annotate(
        active_item_count=Count(
            "items",
            filter=Q(items__status="AVAILABLE", items__moderation_status="APPROVED"),
        )
    ).all()
    pending_reports_count = 0
    pending_support_count = 0
    server_notification_data = {
        "incoming_requests": [],
        "outgoing_requests": [],
        "moderated_items": [],
    }

    if request.user.is_authenticated:
        if request.user.is_staff:
            pending_reports_count = Report.objects.filter(status="PENDING").count()
            pending_support_count = SupportInquiry.objects.filter(status="PENDING").count()

        try:
            # 1. Incoming requests on user's listings
            inc_reqs = list(
                ItemRequest.objects.filter(item__donor=request.user)
                .order_by("-created_at")[:10]
                .values(
                    "id",
                    "status",
                    "message",
                    "created_at",
                    "item_id",
                    "item__title",
                    "requester__username",
                )
            )
            for r in inc_reqs:
                if r.get("created_at"):
                    r["created_at"] = r["created_at"].isoformat()
            server_notification_data["incoming_requests"] = inc_reqs

            # 2. Outgoing requests submitted by user
            out_reqs = list(
                ItemRequest.objects.filter(requester=request.user)
                .order_by("-updated_at")[:10]
                .values(
                    "id",
                    "status",
                    "donor_notes",
                    "updated_at",
                    "item_id",
                    "item__title",
                    "item__donor__username",
                )
            )
            for r in out_reqs:
                if r.get("updated_at"):
                    r["updated_at"] = r["updated_at"].isoformat()
            server_notification_data["outgoing_requests"] = out_reqs

            # 3. Moderated items listed by user
            mod_items = list(
                Item.objects.filter(donor=request.user)
                .exclude(moderation_status="PENDING")
                .order_by("-created_at")[:5]
                .values("id", "title", "moderation_status", "created_at")
            )
            for item in mod_items:
                if item.get("created_at"):
                    item["created_at"] = item["created_at"].isoformat()
            server_notification_data["moderated_items"] = mod_items
        except Exception:
            pass

    return {
        "nav_categories": categories,
        "pending_reports_count": pending_reports_count,
        "pending_support_count": pending_support_count,
        "server_notification_data": server_notification_data,
    }


# ==============================================================================
# USER MODULE VIEWS
# ==============================================================================


def item_list(request):
    """Explore and filter free items."""
    items = Item.objects.filter(moderation_status="APPROVED")

    # Search query
    query = request.GET.get("q", "").strip()
    if query:
        items = items.filter(
            Q(title__icontains=query)
            | Q(description__icontains=query)
            | Q(pickup_location__icontains=query)
        )

    # Category filter
    category_slug = request.GET.get("category", "").strip()
    selected_category = None
    if category_slug:
        selected_category = get_object_or_404(Category, slug=category_slug)
        items = items.filter(category=selected_category)

    # Condition filter
    condition = request.GET.get("condition", "").strip()
    if condition:
        items = items.filter(condition=condition)

    # Repairable filter
    repairable = request.GET.get("repairable", "").strip()
    if repairable == "1":
        items = items.filter(is_repairable=True)

    # Status filter (default to AVAILABLE for normal browsing)
    status_filter = request.GET.get("status", "AVAILABLE").strip()
    if status_filter != "ALL":
        items = items.filter(status=status_filter)

    # Sort
    sort = request.GET.get("sort", "newest")
    if sort == "oldest":
        items = items.order_by("created_at")
    else:
        items = items.order_by("-created_at")

    # Pagination
    paginator = Paginator(items, 12)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    categories = Category.objects.all()

    # Community impact count
    total_given = Item.objects.filter(status="GIVEN_AWAY").count()
    repairable_count = Item.objects.filter(is_repairable=True).count()

    context = {
        "items": page_obj,
        "categories": categories,
        "selected_category": selected_category,
        "query": query,
        "condition": condition,
        "repairable": repairable,
        "status_filter": status_filter,
        "sort": sort,
        "total_given": total_given,
        "repairable_count": repairable_count,
        "condition_choices": Item.CONDITION_CHOICES,
    }
    return render(request, "app/home.html", context)


def about_view(request):
    """About page introducing ReuseHub's mission, values, and community impact."""
    total_items = Item.objects.count()
    total_given = Item.objects.filter(status="GIVEN_AWAY").count()
    active_items = Item.objects.filter(
        status="AVAILABLE", moderation_status="APPROVED"
    ).count()
    repairable_count = Item.objects.filter(is_repairable=True).count()
    total_users = User.objects.count()
    categories_count = Category.objects.count()

    context = {
        "total_items": total_items,
        "total_given": total_given,
        "active_items": active_items,
        "repairable_count": repairable_count,
        "total_users": total_users,
        "categories_count": categories_count,
    }
    return render(request, "app/about.html", context)


def help_view(request):
    """Help & Support center answering how to use ReuseHub, FAQs, and support inquiries."""
    if request.method == "POST":
        if not request.user.is_authenticated:
            messages.error(
                request,
                "Authentication required: You must be signed in to submit a report or contact support.",
            )
            return redirect(f"{reverse('login')}?next={reverse('help')}#contact-support")

        subject = request.POST.get("subject", "General Inquiry").strip()
        message = request.POST.get("message", "").strip()

        # Bind to authenticated user credentials to prevent identity spoofing
        user = request.user
        name = user.get_full_name() or user.username
        email = user.email or request.POST.get("email", "").strip()

        if message:
            # 1. Always record in SupportInquiry so admin portal tracks all tickets
            inquiry = SupportInquiry.objects.create(
                user=user,
                name=name,
                email=email,
                subject=subject,
                message=message,
                status="PENDING",
            )

            # 2. If the user is submitting a user report via help desk, also file formal Report in moderation queue
            if subject == "Report a User":
                reported_username = ""
                if "Reporting user:" in message:
                    for line in message.splitlines():
                        if "Reporting user:" in line:
                            reported_username = line.replace("Reporting user:", "").strip()
                            break

                target_user = None
                if reported_username:
                    target_user = User.objects.filter(username__iexact=reported_username).first()

                Report.objects.create(
                    reported_user=target_user,
                    reported_by=user,
                    reason="OTHER",
                    details=f"[Help Center Ticket #{inquiry.id} - User Report]\nReported Target: {reported_username or 'Not specified'}\n\nSubmitted by: @{user.username} ({email or 'No email'})\n\nMessage:\n{message}",
                    status="PENDING",
                )
                messages.success(
                    request,
                    f"Thank you, {name}! Your report regarding '{reported_username or 'the user'}' has been recorded (Ticket #{inquiry.id}) and submitted to our moderation team.",
                )
            else:
                messages.success(
                    request,
                    f"Thank you, {name}! Your message regarding '{subject}' has been submitted (Ticket #{inquiry.id}). Our team will review it in the admin portal and follow up at {email or 'your account email'}.",
                )
            return redirect("help")
        else:
            messages.error(
                request, "Please enter your message or report details before submitting."
            )

    return render(request, "app/help.html")


def item_detail(request, pk):
    """View complete item details and handle item requests."""
    item = get_object_or_404(Item, pk=pk)

    user_request = None
    all_requests = []
    is_donor = request.user.is_authenticated and (request.user == item.donor)

    if request.user.is_authenticated:
        if is_donor:
            all_requests = item.requests.select_related(
                "requester", "requester__profile"
            ).all()
        else:
            user_request = item.requests.filter(requester=request.user).first()

    request_form = ItemRequestForm()
    report_form = ReportForm()

    donor_stats = get_user_stats(item.donor)
    donor_badges = get_user_badges(item.donor, donor_stats)

    context = {
        "item": item,
        "is_donor": is_donor,
        "user_request": user_request,
        "all_requests": all_requests,
        "request_form": request_form,
        "report_form": report_form,
        "donor_stats": donor_stats,
        "donor_badges": donor_badges,
    }
    return render(request, "app/item_detail.html", context)


@login_required
def item_create(request):
    """User can list their belongings to give away."""
    if request.method == "POST":
        form = ItemForm(request.POST, request.FILES)
        if form.is_valid():
            item = form.save(commit=False)
            item.donor = request.user

            uploaded_files = request.FILES.getlist("images")
            cover_choice = request.POST.get("cover_choice", "new:0")

            cover_idx = 0
            if cover_choice.startswith("new:"):
                try:
                    cover_idx = int(cover_choice.split(":")[1])
                except (ValueError, IndexError):
                    cover_idx = 0
            if cover_idx < 0 or cover_idx >= len(uploaded_files):
                cover_idx = 0

            if uploaded_files:
                item.image = uploaded_files[cover_idx]
            item.save()

            for i, img_file in enumerate(uploaded_files):
                ItemImage.objects.create(
                    item=item, image=img_file, is_cover=(i == cover_idx)
                )

            messages.success(request, f"'{item.title}' has been listed successfully!")
            return redirect("item_detail", pk=item.pk)
    else:
        form = ItemForm()

    return render(
        request,
        "app/item_form.html",
        {
            "form": form,
            "current_cover_choice": "new:0",
            "title": "Give an Item",
        },
    )


@login_required
def item_edit(request, pk):
    """Donor can edit their listed item."""
    item = get_object_or_404(Item, pk=pk)
    if item.donor != request.user and not request.user.is_staff:
        messages.error(request, "You are not authorized to edit this listing.")
        return redirect("item_detail", pk=pk)

    # Legacy backfill: ensure item.image has an ItemImage row
    if item.image and not item.images.exists():
        ItemImage.objects.create(item=item, image=item.image, is_cover=True)

    if request.method == "POST":
        form = ItemForm(request.POST, request.FILES, instance=item)
        if form.is_valid():
            item = form.save()

            # Handle existing images marked for deletion
            delete_image_ids = request.POST.getlist("delete_images")
            if delete_image_ids:
                item.images.filter(id__in=delete_image_ids).delete()

            # Handle newly uploaded images
            new_files = request.FILES.getlist("images")
            new_images = []
            for img_file in new_files:
                new_images.append(
                    ItemImage.objects.create(item=item, image=img_file, is_cover=False)
                )

            cover_choice = request.POST.get("cover_choice", "")
            cover_image_obj = None

            if cover_choice.startswith("existing:"):
                try:
                    cov_id = int(cover_choice.split(":")[1])
                    cover_image_obj = item.images.filter(id=cov_id).first()
                except (ValueError, IndexError):
                    cover_image_obj = None
            elif cover_choice.startswith("new:"):
                try:
                    cov_idx = int(cover_choice.split(":")[1])
                    if 0 <= cov_idx < len(new_images):
                        cover_image_obj = new_images[cov_idx]
                except (ValueError, IndexError):
                    cover_image_obj = None

            # Fallback if selected cover is deleted or not found
            if not cover_image_obj:
                cover_image_obj = item.images.filter(is_cover=True).first()
            if not cover_image_obj:
                cover_image_obj = item.images.first()

            # Update is_cover across all images and sync item.image
            item.images.update(is_cover=False)
            if cover_image_obj:
                cover_image_obj.is_cover = True
                cover_image_obj.save(update_fields=["is_cover"])
                item.image = cover_image_obj.image
                item.save(update_fields=["image"])
            else:
                item.image = None
                item.save(update_fields=["image"])

            messages.success(request, "Listing updated successfully.")
            return redirect("item_detail", pk=item.pk)
    else:
        form = ItemForm(instance=item)

    existing_images = item.images.all()
    remaining_slots = max(0, 5 - existing_images.count())
    cover_image = (
        existing_images.filter(is_cover=True).first() or existing_images.first()
    )
    current_cover_choice = f"existing:{cover_image.id}" if cover_image else "new:0"

    return render(
        request,
        "app/item_form.html",
        {
            "form": form,
            "item": item,
            "existing_images": existing_images,
            "remaining_slots": remaining_slots,
            "current_cover_choice": current_cover_choice,
            "title": "Edit Listing",
        },
    )


@login_required
def item_delete(request, pk):
    """Donor or Admin can remove an item listing."""
    item = get_object_or_404(Item, pk=pk)
    if item.donor != request.user and not request.user.is_staff:
        messages.error(request, "You are not authorized to remove this listing.")
        return redirect("item_detail", pk=pk)

    if request.method == "POST":
        title = item.title
        item.delete()
        messages.success(request, f"Listing '{title}' was removed.")
        return redirect("my_listings")

    return render(request, "app/item_confirm_delete.html", {"item": item})


@login_required
def request_item(request, pk):
    """Submit a request for an item."""
    item = get_object_or_404(Item, pk=pk)
    if item.donor == request.user:
        messages.warning(request, "You cannot request your own listed item.")
        return redirect("item_detail", pk=pk)

    if item.status != "AVAILABLE":
        messages.error(request, "This item is no longer available for requests.")
        return redirect("item_detail", pk=pk)

    if request.method == "POST":
        form = ItemRequestForm(request.POST)
        if form.is_valid():
            req, created = ItemRequest.objects.get_or_create(
                item=item,
                requester=request.user,
                defaults={
                    "message": form.cleaned_data["message"],
                    "contact_info": form.cleaned_data["contact_info"],
                },
            )
            if not created:
                req.message = form.cleaned_data["message"]
                req.contact_info = form.cleaned_data["contact_info"]
                req.status = "PENDING"
                req.save()

            # Trigger notification email to the donor via central ReuseHub sender
            action_url = request.build_absolute_uri(
                reverse("item_detail", kwargs={"pk": item.pk})
            )
            send_item_request_notification(req, action_url=action_url)

            messages.success(request, "Your request has been submitted to the donor!")
            return redirect("item_detail", pk=pk)

    return redirect("item_detail", pk=pk)


@login_required
def respond_request(request, request_id, action):
    """Donor accepts or rejects an item request."""
    item_req = get_object_or_404(ItemRequest, id=request_id)
    if item_req.item.donor != request.user and not request.user.is_staff:
        messages.error(request, "You are not authorized to respond to this request.")
        return redirect("item_detail", pk=item_req.item.pk)

    action_url = request.build_absolute_uri(
        reverse("item_detail", kwargs={"pk": item_req.item.pk})
    )

    if action == "accept":
        item_req.status = "ACCEPTED"
        item_req.item.status = "REQUESTED"
        item_req.item.save()
        item_req.save()
        send_request_status_notification(
            item_req, action="accept", action_url=action_url
        )
        messages.success(
            request,
            f"You accepted {item_req.requester.username}'s request! You can now coordinate pickup.",
        )
    elif action == "complete":
        item_req.status = "COMPLETED"
        item_req.item.status = "GIVEN_AWAY"
        item_req.item.save()
        item_req.save()
        review_url = request.build_absolute_uri(
            reverse("submit_review", kwargs={"request_id": item_req.id})
        )
        send_request_status_notification(
            item_req, action="complete", action_url=action_url, review_url=review_url
        )
        messages.success(
            request,
            f"Exchange completed with {item_req.requester.username}! You can now leave a community review.",
        )
    elif action == "reject":
        item_req.status = "REJECTED"
        item_req.save()
        # If this item was requested by them, put it back to available
        if item_req.item.status == "REQUESTED":
            item_req.item.status = "AVAILABLE"
            item_req.item.save()
        send_request_status_notification(
            item_req, action="reject", action_url=action_url
        )
        messages.info(request, f"You declined {item_req.requester.username}'s request.")

    return redirect("item_detail", pk=item_req.item.pk)


@login_required
def mark_given_away(request, pk):
    """Donor marks the item as given away once collected."""
    item = get_object_or_404(Item, pk=pk)
    if item.donor != request.user and not request.user.is_staff:
        messages.error(request, "Unauthorized action.")
        return redirect("item_detail", pk=pk)

    item.status = "GIVEN_AWAY"
    item.save()

    # Automatically complete any accepted request for this item
    accepted_req = item.requests.filter(status="ACCEPTED").first()
    if accepted_req:
        accepted_req.status = "COMPLETED"
        accepted_req.save()

    action_url = request.build_absolute_uri(
        reverse("item_detail", kwargs={"pk": item.pk})
    )
    send_item_status_update(
        item, old_status="AVAILABLE", new_status="GIVEN_AWAY", action_url=action_url
    )

    messages.success(
        request,
        f"Awesome! '{item.title}' is marked as given away. Thank you for helping the community!",
    )
    return redirect("item_detail", pk=pk)


@login_required
def mark_available(request, pk):
    """Donor puts the item back as available."""
    item = get_object_or_404(Item, pk=pk)
    if item.donor != request.user and not request.user.is_staff:
        messages.error(request, "Unauthorized action.")
        return redirect("item_detail", pk=pk)

    item.status = "AVAILABLE"
    item.save()

    action_url = request.build_absolute_uri(
        reverse("item_detail", kwargs={"pk": item.pk})
    )
    send_item_status_update(
        item, old_status="GIVEN_AWAY", new_status="AVAILABLE", action_url=action_url
    )

    messages.info(request, f"'{item.title}' is now marked as available again.")
    return redirect("item_detail", pk=pk)


@login_required
def my_listings(request):
    """User dashboard to manage their own donated belongings."""
    items = Item.objects.filter(donor=request.user)
    status_tab = request.GET.get("tab", "ALL")

    if status_tab == "AVAILABLE":
        items = items.filter(status="AVAILABLE")
    elif status_tab == "REQUESTED":
        items = items.filter(status="REQUESTED")
    elif status_tab == "GIVEN_AWAY":
        items = items.filter(status="GIVEN_AWAY")

    total_count = Item.objects.filter(donor=request.user).count()
    available_count = Item.objects.filter(
        donor=request.user, status="AVAILABLE"
    ).count()
    given_count = Item.objects.filter(donor=request.user, status="GIVEN_AWAY").count()

    context = {
        "items": items,
        "status_tab": status_tab,
        "total_count": total_count,
        "available_count": available_count,
        "given_count": given_count,
    }
    return render(request, "app/my_listings.html", context)


@login_required
def my_requests(request):
    """User dashboard to track items they have requested."""
    requests = (
        ItemRequest.objects.filter(requester=request.user)
        .select_related("item", "item__donor", "item__donor__profile")
        .order_by("-created_at")
    )
    reviewed_req_ids = set(
        UserReview.objects.filter(reviewer=request.user).values_list(
            "item_request_id", flat=True
        )
    )
    for req in requests:
        req.has_reviewed = req.id in reviewed_req_ids
        req.can_review = (
            req.status == "COMPLETED" or req.item.status == "GIVEN_AWAY"
        ) and not req.has_reviewed
    return render(request, "app/my_requests.html", {"requests": requests})


@login_required
def notifications_view(request):
    """Notification center for the logged-in user."""
    return render(request, "app/notifications.html")


@login_required
def report_item(request, pk):
    """User can report an item listing for moderation."""
    item = get_object_or_404(Item, pk=pk)
    if request.method == "POST":
        form = ReportForm(request.POST)
        if form.is_valid():
            report = form.save(commit=False)
            report.item = item
            report.reported_by = request.user
            report.save()

            # Flag item if multiple reports
            if item.reports.count() >= 2:
                item.moderation_status = "FLAGGED"
                item.save()

            messages.success(
                request,
                "Thank you for helping keep ReuseHub safe. Our moderators will review this listing.",
            )
            return redirect("item_detail", pk=pk)
    else:
        form = ReportForm()

    return render(request, "app/report_form.html", {"form": form, "item": item})


@login_required
def profile_view(request):
    """User profile management."""
    profile, _ = UserProfile.objects.get_or_create(user=request.user)

    if request.method == "POST":
        form = UserProfileForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, "Profile updated successfully.")
            return redirect("profile")
    else:
        form = UserProfileForm(instance=profile)

    items_given = Item.objects.filter(donor=request.user, status="GIVEN_AWAY").count()
    active_listings = Item.objects.filter(
        donor=request.user, status="AVAILABLE"
    ).count()
    items_claimed = ItemRequest.objects.filter(
        requester=request.user, status="COMPLETED"
    ).count()

    context = {
        "form": form,
        "profile": profile,
        "items_given": items_given,
        "active_listings": active_listings,
        "items_claimed": items_claimed,
    }
    return render(request, "app/profile.html", context)


def public_profile_view(request, username):
    """
    Public community profile for a member.
    Displays profile photo, username, short bio, general location, member-since date,
    items given away, active listings, community ratings (1-5 stars), and badges.
    Strictly keeps private info (phone number, email address) hidden.
    """
    target_user = get_object_or_404(User, username=username)
    profile, _ = UserProfile.objects.get_or_create(user=target_user)

    stats = get_user_stats(target_user)
    badges = get_user_badges(target_user, stats)

    # Previously given away items (items they have successfully passed on)
    items_given = (
        Item.objects.filter(donor=target_user, status="GIVEN_AWAY")
        .select_related("category")
        .order_by("-updated_at")
    )

    # Currently active / available listings
    active_items = (
        Item.objects.filter(
            donor=target_user, status="AVAILABLE", moderation_status="APPROVED"
        )
        .select_related("category")
        .order_by("-created_at")
    )

    # Community reviews received from completed exchanges
    reviews = (
        UserReview.objects.filter(reviewed_user=target_user)
        .select_related("reviewer", "reviewer__profile", "item_request__item")
        .order_by("-created_at")
    )

    # Check if logged-in user has an eligible completed exchange to review
    can_review = False
    eligible_exchange = None
    if request.user.is_authenticated and request.user != target_user:
        reqs_as_requester = ItemRequest.objects.filter(
            requester=request.user,
            item__donor=target_user,
            status="COMPLETED",
        ).select_related("item")
        reqs_given = ItemRequest.objects.filter(
            requester=request.user,
            item__donor=target_user,
            item__status="GIVEN_AWAY",
            status__in=["ACCEPTED", "COMPLETED"],
        ).select_related("item")
        reqs_as_donor = ItemRequest.objects.filter(
            requester=target_user,
            item__donor=request.user,
            status__in=["ACCEPTED", "COMPLETED"],
            item__status="GIVEN_AWAY",
        ).select_related("item")

        candidate_exchanges = (
            reqs_as_requester | reqs_given | reqs_as_donor
        ).distinct()
        reviewed_ids = set(
            UserReview.objects.filter(
                reviewer=request.user, item_request__in=candidate_exchanges
            ).values_list("item_request_id", flat=True)
        )
        unreviewed = [ex for ex in candidate_exchanges if ex.id not in reviewed_ids]
        if unreviewed:
            can_review = True
            eligible_exchange = unreviewed[0]

    review_form = UserReviewForm()
    report_form = UserReportForm()

    context = {
        "profile_user": target_user,
        "profile": profile,
        "stats": stats,
        "badges": badges,
        "items_given": items_given,
        "active_items": active_items,
        "reviews": reviews,
        "is_own_profile": request.user.is_authenticated and request.user == target_user,
        "can_review": can_review,
        "eligible_exchange": eligible_exchange,
        "review_form": review_form,
        "report_form": report_form,
    }
    return render(request, "app/public_profile.html", context)


@login_required
def submit_review_view(request, request_id):
    """
    Submit a 1-5 star rating and short review after a completed exchange.
    Restricted to exchange participants only after collection/completion.
    """
    item_req = get_object_or_404(
        ItemRequest.objects.select_related("item", "item__donor", "requester"),
        id=request_id,
    )

    if request.user != item_req.requester and request.user != item_req.item.donor:
        messages.error(request, "You were not a participant in this exchange.")
        return redirect("home")

    is_exchange_done = (
        item_req.status == "COMPLETED"
        or item_req.item.status == "GIVEN_AWAY"
        or item_req.status == "ACCEPTED"
    )
    if not is_exchange_done:
        messages.error(
            request,
            "Community ratings are only allowed after a successful completed exchange.",
        )
        return redirect("item_detail", pk=item_req.item.pk)

    if request.user == item_req.requester:
        target_user = item_req.item.donor
    else:
        target_user = item_req.requester

    if target_user == request.user:
        messages.error(request, "You cannot review yourself.")
        return redirect("public_profile", username=target_user.username)

    if request.method == "POST":
        form = UserReviewForm(request.POST)
        if form.is_valid():
            rating_val = form.cleaned_data["rating"]
            comment_val = form.cleaned_data["comment"]

            review, created = UserReview.objects.update_or_create(
                reviewer=request.user,
                item_request=item_req,
                defaults={
                    "reviewed_user": target_user,
                    "rating": rating_val,
                    "comment": comment_val,
                },
            )
            action_text = "posted" if created else "updated"
            messages.success(
                request,
                f"Thank you! Your {review.rating}★ rating for {target_user.username} has been {action_text}.",
            )
            return redirect("public_profile", username=target_user.username)
        else:
            messages.error(request, "Please choose a rating between 1 and 5 stars.")

    return redirect("public_profile", username=target_user.username)


@login_required
def report_user_view(request, username):
    """User reports an inappropriate user profile or behavior."""
    target_user = get_object_or_404(User, username=username)

    if target_user == request.user:
        messages.error(request, "You cannot report your own profile.")
        return redirect("public_profile", username=username)

    if request.method == "POST":
        form = UserReportForm(request.POST)
        if form.is_valid():
            report = form.save(commit=False)
            report.reported_user = target_user
            report.reported_by = request.user
            report.status = "PENDING"
            report.save()
            messages.success(
                request,
                f"Thank you for looking out for our community. Your report regarding user '{target_user.username}' has been submitted for moderation.",
            )
            return redirect("public_profile", username=username)
    else:
        form = UserReportForm()

    return render(
        request,
        "app/report_user_form.html",
        {"form": form, "target_user": target_user},
    )


# ==============================================================================
# AUTH VIEWS
# ==============================================================================


def register_view(request):
    """New user registration with email format validation and OTP verification."""
    if request.user.is_authenticated:
        return redirect("home")

    if request.method == "POST":
        form = UserRegisterForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"].strip().lower()
            username = form.cleaned_data["username"].strip()
            password = form.cleaned_data["password"]
            first_name = form.cleaned_data.get("first_name", "").strip()
            last_name = form.cleaned_data.get("last_name", "").strip()

            # Check if there is an existing unverified user with this email or username
            inactive_user = User.objects.filter(
                Q(email__iexact=email) | Q(username__iexact=username), is_active=False
            ).first()

            if inactive_user:
                user = inactive_user
                user.username = username
                user.email = email
                user.first_name = first_name
                user.last_name = last_name
                user.set_password(password)
                user.save()
            else:
                user = User.objects.create_user(
                    username=username,
                    email=email,
                    password=password,
                    first_name=first_name,
                    last_name=last_name,
                    is_active=False,  # Unverified until OTP verification succeeds
                )

            # Ensure profile exists
            profile, _ = UserProfile.objects.get_or_create(user=user)
            profile.email_verified = False
            profile.save()

            # Generate 6-digit OTP code and send via central ReuseHub sender
            otp = EmailOTP.generate_otp(
                user=user, email=user.email, purpose="REGISTRATION", validity_minutes=15
            )
            send_registration_otp_email(user, otp.code, validity_minutes=15)

            # Keep user info in session for OTP verification step
            request.session["verify_user_id"] = user.id
            request.session["verify_email"] = user.email

            messages.info(
                request,
                f"We sent a 6-digit verification code to {user.email}. Enter it below to activate your account.",
            )
            return redirect("verify_otp")
    else:
        form = UserRegisterForm()

    return render(request, "app/auth/register.html", {"form": form})


def verify_otp_view(request):
    """Verify registration OTP to activate the user account."""
    if request.user.is_authenticated:
        return redirect("home")

    user_id = request.session.get("verify_user_id")
    if not user_id:
        messages.warning(request, "Please register or sign in to verify your account.")
        return redirect("register")

    user = get_object_or_404(User, id=user_id)
    if user.is_active:
        messages.info(request, "Your account is already activated. Please sign in.")
        return redirect("login")

    # Mask email for privacy display (e.g., j***n@example.com)
    email = user.email
    if "@" in email:
        local_part, domain = email.split("@", 1)
        if len(local_part) <= 2:
            masked_local = local_part[0] + "***"
        else:
            masked_local = local_part[0] + "***" + local_part[-1]
        masked_email = f"{masked_local}@{domain}"
    else:
        masked_email = email

    central_sender = getattr(
        settings, "DEFAULT_FROM_EMAIL", "reusehub.support@gmail.com"
    )

    if request.method == "POST":
        form = VerifyOTPForm(request.POST)
        if form.is_valid():
            entered_code = form.cleaned_data["otp"].strip()
            otp = (
                EmailOTP.objects.filter(
                    user=user, purpose="REGISTRATION", is_used=False
                )
                .order_by("-created_at")
                .first()
            )

            if not otp or otp.is_expired():
                form.add_error(
                    "otp",
                    "This verification code has expired. Please click 'Resend Verification Code' below.",
                )
            elif otp.attempts >= otp.max_attempts:
                form.add_error(
                    "otp",
                    "Too many incorrect attempts. Please click 'Resend Verification Code' to receive a new code.",
                )
            elif otp.code != entered_code:
                otp.attempts += 1
                otp.save()
                remaining = max(0, otp.max_attempts - otp.attempts)
                form.add_error(
                    "otp",
                    f"Invalid verification code. Please check your email and try again ({remaining} attempts left).",
                )
            else:
                # Valid OTP! Activate account and confirm email verification
                otp.is_used = True
                otp.save()

                profile, _ = UserProfile.objects.get_or_create(user=user)
                profile.email_verified = True
                profile.save()
                user.profile = profile

                user.is_active = True
                user.save()

                # Clean up session
                request.session.pop("verify_user_id", None)
                request.session.pop("verify_email", None)

                # Log user in
                login(request, user)
                messages.success(
                    request,
                    f"Welcome to ReuseHub, {user.username}! Your email has been verified successfully. Let's reduce waste together!",
                )
                return redirect("home")
    else:
        form = VerifyOTPForm()

    context = {
        "form": form,
        "email": masked_email,
        "full_email": user.email,
        "central_sender": central_sender,
    }
    return render(request, "app/auth/verify_otp.html", context)


def resend_otp_view(request):
    """Resend a fresh 6-digit OTP code with cooldown rate-limiting."""
    if request.user.is_authenticated:
        return redirect("home")

    user_id = request.session.get("verify_user_id")
    if not user_id:
        messages.error(
            request, "Your verification session has expired. Please register again."
        )
        return redirect("register")

    user = get_object_or_404(User, id=user_id)
    if user.is_active:
        messages.info(request, "Your account is already active. Please sign in.")
        return redirect("login")

    # Rate limiting: minimum 60 seconds between resends
    last_otp = (
        EmailOTP.objects.filter(user=user, purpose="REGISTRATION")
        .order_by("-created_at")
        .first()
    )
    if last_otp and (timezone.now() - last_otp.created_at) < timedelta(seconds=60):
        remaining = 60 - int((timezone.now() - last_otp.created_at).total_seconds())
        messages.warning(
            request, f"Please wait {remaining} seconds before requesting another code."
        )
        return redirect("verify_otp")

    new_otp = EmailOTP.generate_otp(
        user=user, email=user.email, purpose="REGISTRATION", validity_minutes=15
    )
    send_registration_otp_email(user, new_otp.code, validity_minutes=15)
    messages.success(
        request, f"A fresh 6-digit verification code has been sent to {user.email}."
    )
    return redirect("verify_otp")


def login_view(request):
    """User authentication with unverified account detection."""
    if request.user.is_authenticated:
        return redirect("home")

    if request.method == "POST":
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get("username")
            password = form.cleaned_data.get("password")
            user = authenticate(username=username, password=password)
            if user is not None:
                login(request, user)
                messages.success(request, f"Welcome back, {user.username}!")
                next_url = request.GET.get("next")
                return redirect(next_url if next_url else "home")
        else:
            # Check if this is an unverified user whose password matches
            username = request.POST.get("username", "").strip()
            password = request.POST.get("password", "")
            inactive_user = User.objects.filter(
                username__iexact=username, is_active=False
            ).first()
            if inactive_user and inactive_user.check_password(password):
                request.session["verify_user_id"] = inactive_user.id
                request.session["verify_email"] = inactive_user.email
                otp = EmailOTP.generate_otp(
                    user=inactive_user,
                    email=inactive_user.email,
                    purpose="REGISTRATION",
                )
                send_registration_otp_email(inactive_user, otp.code)
                messages.warning(
                    request,
                    f"Your account is not verified yet. We have sent a new verification code to {inactive_user.email}.",
                )
                return redirect("verify_otp")
            messages.error(request, "Invalid username or password.")
    else:
        form = AuthenticationForm()

    return render(request, "app/auth/login.html", {"form": form})


def password_reset_request_view(request):
    """Handle password reset requests and dispatch reset email via central sender."""
    if request.user.is_authenticated:
        return redirect("home")

    if request.method == "POST":
        form = ReuseHubPasswordResetForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"].strip().lower()
            matching_users = User.objects.filter(email__iexact=email, is_active=True)
            for u in matching_users:
                token = default_token_generator.make_token(u)
                uidb64 = urlsafe_base64_encode(force_bytes(u.pk))
                reset_url = request.build_absolute_uri(
                    reverse(
                        "password_reset_confirm",
                        kwargs={"uidb64": uidb64, "token": token},
                    )
                )
                send_password_reset_email(u, reset_url)
            return redirect("password_reset_done")
    else:
        form = ReuseHubPasswordResetForm()

    return render(request, "app/auth/password_reset.html", {"form": form})


def password_reset_done_view(request):
    """Display confirmation screen that password reset instructions were dispatched."""
    return render(request, "app/auth/password_reset_done.html")


def password_reset_confirm_view(request, uidb64, token):
    """Verify reset token and allow setting a new password."""
    if request.user.is_authenticated:
        return redirect("home")

    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    validlink = user is not None and default_token_generator.check_token(user, token)

    if not validlink:
        return render(
            request, "app/auth/password_reset_confirm.html", {"validlink": False}
        )

    if request.method == "POST":
        form = ReuseHubSetPasswordForm(user, request.POST)
        if form.is_valid():
            form.save()
            messages.success(
                request,
                "Your password has been reset successfully! You can now log in.",
            )
            return redirect("password_reset_complete")
    else:
        form = ReuseHubSetPasswordForm(user)

    return render(
        request,
        "app/auth/password_reset_confirm.html",
        {"form": form, "validlink": True},
    )


def password_reset_complete_view(request):
    """Display success page after successful password reset."""
    return render(request, "app/auth/password_reset_complete.html")


def logout_view(request):
    """Log out user."""
    logout(request)
    messages.info(request, "You have been logged out.")
    return redirect("home")


# ==============================================================================
# ADMIN MODULE VIEWS
# ==============================================================================


def is_admin(user):
    return user.is_authenticated and user.is_staff


@user_passes_test(is_admin)
def admin_dashboard(request):
    """Admin Module overview and platform analytics."""
    total_items = Item.objects.count()
    active_items = Item.objects.filter(
        status="AVAILABLE", moderation_status="APPROVED"
    ).count()
    given_away_items = Item.objects.filter(status="GIVEN_AWAY").count()
    repairable_items = Item.objects.filter(is_repairable=True).count()
    total_users = User.objects.count()
    pending_reports = Report.objects.filter(status="PENDING").count()
    pending_support = SupportInquiry.objects.filter(status="PENDING").count()
    pending_moderation = Item.objects.filter(moderation_status="PENDING").count()
    flagged_items = Item.objects.filter(moderation_status="FLAGGED").count()

    recent_items = Item.objects.select_related("donor", "category").all()[:6]
    recent_reports = Report.objects.select_related("item", "reported_user", "reported_by").filter(
        status="PENDING"
    )[:5]
    recent_support = SupportInquiry.objects.select_related("user").filter(
        status="PENDING"
    )[:5]

    context = {
        "total_items": total_items,
        "active_items": active_items,
        "given_away_items": given_away_items,
        "repairable_items": repairable_items,
        "total_users": total_users,
        "pending_reports": pending_reports,
        "pending_support": pending_support,
        "pending_moderation": pending_moderation,
        "flagged_items": flagged_items,
        "recent_items": recent_items,
        "recent_reports": recent_reports,
        "recent_support": recent_support,
    }
    return render(request, "app/admin/dashboard.html", context)


@user_passes_test(is_admin)
def admin_listings(request):
    """Admin review and moderation of items."""
    status_filter = request.GET.get("mod_status", "ALL")
    items = Item.objects.select_related("donor", "category").all()

    if status_filter != "ALL":
        items = items.filter(moderation_status=status_filter)

    query = request.GET.get("q", "").strip()
    if query:
        items = items.filter(
            Q(title__icontains=query) | Q(donor__username__icontains=query)
        )

    paginator = Paginator(items, 15)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    context = {
        "items": page_obj,
        "status_filter": status_filter,
        "query": query,
    }
    return render(request, "app/admin/listings.html", context)


@user_passes_test(is_admin)
def admin_moderate_action(request, pk, action):
    """Admin action to approve, flag, reject, or delete a listing."""
    item = get_object_or_404(Item, pk=pk)

    if action == "approve":
        item.moderation_status = "APPROVED"
        item.save()
        messages.success(request, f"Item '{item.title}' has been approved.")
        action_url = request.build_absolute_uri(
            reverse("item_detail", kwargs={"pk": item.pk})
        )
        send_admin_or_account_notification(
            user=item.donor,
            subject=f"Listing Approved: '{item.title}'",
            headline="Your Item Listing is Live! 🎉",
            message_body=f"Great news! Your listing for '{item.title}' has been reviewed and approved by the ReuseHub moderation team. Neighbors in your community can now discover and request it.",
            action_url=action_url,
            action_text="View Your Active Listing",
        )
    elif action == "reject":
        item.moderation_status = "REJECTED"
        item.save()
        messages.warning(request, f"Item '{item.title}' has been rejected.")
        send_admin_or_account_notification(
            user=item.donor,
            subject=f"Listing Review: '{item.title}'",
            headline="Listing Moderation Notice",
            message_body=f"Your listing for '{item.title}' was reviewed by our moderation team and could not be approved at this time. Please ensure listings meet our community reuse and safety standards.",
            action_url=request.build_absolute_uri(reverse("my_listings")),
            action_text="View My Listings",
        )
    elif action == "flag":
        item.moderation_status = "FLAGGED"
        item.save()
        messages.info(request, f"Item '{item.title}' marked as flagged.")
    elif action == "remove":
        title = item.title
        donor = item.donor
        item.delete()
        send_admin_or_account_notification(
            user=donor,
            subject=f"Listing Removed: '{title}'",
            headline="Listing Removal Notice",
            message_body=f"Your listing for '{title}' was removed by an administrator in accordance with ReuseHub community safety standards.",
            action_url=request.build_absolute_uri(reverse("my_listings")),
            action_text="View My Listings",
        )
        messages.success(
            request, f"Inappropriate listing '{title}' permanently deleted."
        )

    return redirect(request.META.get("HTTP_REFERER", "admin_listings"))


@user_passes_test(is_admin)
def admin_categories(request):
    """Admin category management (Add, view, organize)."""
    categories = Category.objects.annotate(item_count=Count("items")).all()

    if request.method == "POST":
        form = CategoryForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "New category created.")
            return redirect("admin_categories")
    else:
        form = CategoryForm()

    context = {
        "categories": categories,
        "form": form,
    }
    return render(request, "app/admin/categories.html", context)


@user_passes_test(is_admin)
def admin_category_delete(request, pk):
    """Admin delete category."""
    category = get_object_or_404(Category, pk=pk)
    name = category.name
    category.delete()
    messages.success(request, f"Category '{name}' deleted.")
    return redirect("admin_categories")


@user_passes_test(is_admin)
def admin_reports(request):
    """Admin review of user-submitted reports."""
    reports = Report.objects.select_related(
        "item", "item__donor", "reported_user", "reported_by"
    ).all()
    status_filter = request.GET.get("status", "PENDING")

    if status_filter != "ALL":
        reports = reports.filter(status=status_filter)

    context = {
        "reports": reports,
        "status_filter": status_filter,
    }
    return render(request, "app/admin/reports.html", context)


@user_passes_test(is_admin)
def admin_report_resolve(request, pk, action):
    """Admin resolve or dismiss report."""
    report = get_object_or_404(Report, pk=pk)

    if action == "resolve":
        report.status = "RESOLVED"
        report.save()
        messages.success(request, f"Report #{report.id} marked as resolved.")
    elif action == "dismiss":
        report.status = "DISMISSED"
        report.save()
        messages.info(request, f"Report #{report.id} dismissed.")
    elif action == "take_down_item" and report.item:
        report.status = "RESOLVED"
        report.save()
        report.item.moderation_status = "REJECTED"
        report.item.save()
        messages.warning(
            request, f"Listing '{report.item.title}' has been removed from public view."
        )
    elif action == "deactivate_user" and report.reported_user:
        report.status = "RESOLVED"
        report.save()
        report.reported_user.is_active = False
        report.reported_user.save()
        messages.warning(
            request, f"User '{report.reported_user.username}' has been deactivated."
        )

    return redirect("admin_reports")


@user_passes_test(is_admin)
def admin_support(request):
    """Admin view and management of user-submitted support inquiries and direct tickets."""
    inquiries = SupportInquiry.objects.select_related("user").all()
    status_filter = request.GET.get("status", "PENDING")

    if status_filter != "ALL":
        inquiries = inquiries.filter(status=status_filter)

    query = request.GET.get("q", "").strip()
    if query:
        inquiries = inquiries.filter(
            Q(subject__icontains=query)
            | Q(message__icontains=query)
            | Q(name__icontains=query)
            | Q(email__icontains=query)
            | Q(user__username__icontains=query)
        )

    paginator = Paginator(inquiries, 15)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    context = {
        "inquiries": page_obj,
        "status_filter": status_filter,
        "query": query,
    }
    return render(request, "app/admin/support.html", context)


@user_passes_test(is_admin)
def admin_support_action(request, pk, action):
    """Admin update status or respond to support inquiry."""
    inquiry = get_object_or_404(SupportInquiry, pk=pk)

    if request.method == "POST":
        response_text = request.POST.get("admin_response", "").strip()
        if response_text:
            inquiry.admin_response = response_text
            inquiry.status = "RESOLVED"
            inquiry.save()

            # Send email notification to user
            send_admin_or_account_notification(
                user=inquiry.user,
                subject=f"Update regarding your inquiry: '{inquiry.subject}'",
                headline="Support Inquiry Response 💬",
                message_body=f"Hello {inquiry.name},\n\nOur support team has reviewed your message regarding '{inquiry.subject}':\n\n\"{response_text}\"",
                action_url=request.build_absolute_uri(reverse("help")),
                action_text="Visit Help & Support",
            )
            messages.success(
                request,
                f"Response sent to {inquiry.user.username} ({inquiry.email}) and ticket #{inquiry.id} marked as resolved.",
            )
            return redirect("admin_support")

    if action == "resolve":
        inquiry.status = "RESOLVED"
        inquiry.save()
        messages.success(request, f"Ticket #{inquiry.id} marked as resolved.")
    elif action == "in_progress":
        inquiry.status = "IN_PROGRESS"
        inquiry.save()
        messages.info(request, f"Ticket #{inquiry.id} marked as in progress.")
    elif action == "close":
        inquiry.status = "CLOSED"
        inquiry.save()
        messages.info(request, f"Ticket #{inquiry.id} closed.")
    elif action == "reopen":
        inquiry.status = "PENDING"
        inquiry.save()
        messages.info(request, f"Ticket #{inquiry.id} reopened.")

    return redirect("admin_support")


@user_passes_test(is_admin)
def admin_users(request):
    """Admin manage community members."""
    users = (
        User.objects.select_related("profile")
        .annotate(
            items_listed=Count("donated_items"), requests_count=Count("item_requests")
        )
        .order_by("-date_joined")
    )

    query = request.GET.get("q", "").strip()
    if query:
        users = users.filter(Q(username__icontains=query) | Q(email__icontains=query))

    context = {
        "users": users,
        "query": query,
    }
    return render(request, "app/admin/users.html", context)


@user_passes_test(is_admin)
def admin_user_toggle_status(request, pk):
    """Admin toggle user active status."""
    user_obj = get_object_or_404(User, pk=pk)
    if user_obj == request.user:
        messages.error(request, "You cannot deactivate your own account.")
        return redirect("admin_users")

    user_obj.is_active = not user_obj.is_active
    user_obj.save()
    status_text = "activated" if user_obj.is_active else "deactivated"
    messages.info(request, f"User {user_obj.username} has been {status_text}.")
    return redirect("admin_users")


@user_passes_test(is_admin)
def admin_user_toggle_verification(request, pk):
    """Admin toggle user verified community badge."""
    user_obj = get_object_or_404(User, pk=pk)
    profile, _ = UserProfile.objects.get_or_create(user=user_obj)
    profile.is_verified = not profile.is_verified
    profile.save()
    status_txt = (
        "verified as a trusted community member"
        if profile.is_verified
        else "unverified"
    )
    messages.success(
        request, f"User {user_obj.username} is now marked as {status_txt}."
    )

    if profile.is_verified:
        action_url = request.build_absolute_uri(reverse("profile"))
        send_admin_or_account_notification(
            user=user_obj,
            subject="You've earned the Verified Community Member badge!",
            headline="Community Profile Verified 🏅",
            message_body=f"Congratulations {user_obj.username}! An administrator has verified your ReuseHub community profile. You now display the verified member trust badge when sharing and requesting items.",
            action_url=action_url,
            action_text="View Your Verified Profile",
        )

    return redirect("admin_users")
