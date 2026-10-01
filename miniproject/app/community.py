"""
Community profile, badge, and rating calculation utilities for ReuseHub.
"""
from django.db.models import Avg, Count, Q
from .models import Item, ItemRequest, UserReview


def get_user_stats(user):
    """
    Calculate public community statistics for a user:
    - items given away
    - active listings
    - successful exchanges
    - average rating (1.0 to 5.0)
    - total review count
    - rating breakdown (5, 4, 3, 2, 1 stars)
    """

    # Counts how many items the user has successfully given away.
    items_given = Item.objects.filter(donor=user, status="GIVEN_AWAY").count()

    # Counts active listings that are approved for sharing
    active_listings = Item.objects.filter(
        donor=user, status="AVAILABLE", moderation_status="APPROVED"
    ).count()

    # Counts completed exchanges (where the item was successfully given and received):
    # 1. Requests completed for items this user donated
    # 2. Requests this user made that were completed
    exchanges_completed = ItemRequest.objects.filter(
        (Q(item__donor=user) | Q(requester=user)) & Q(status="COMPLETED")
    ).distinct().count()

    review_stats = UserReview.objects.filter(reviewed_user=user).aggregate(
        avg_rating=Avg("rating"),
        review_count=Count("id")
    )
    raw_avg = review_stats["avg_rating"]
    avg_rating = round(raw_avg, 1) if raw_avg is not None else 0.0
    review_count = review_stats["review_count"] or 0

    # Star rating distribution
    breakdown = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    for row in UserReview.objects.filter(reviewed_user=user).values("rating").annotate(c=Count("id")):
        breakdown[row["rating"]] = row["c"]

    # Star visual representation: list of bool or state for 5 stars
    stars = []
    for i in range(1, 6):
        if avg_rating >= i:
            stars.append("full")
        elif avg_rating >= i - 0.5:
            stars.append("half")
        else:
            stars.append("empty")

    breakdown_rows = []
    for r in [5, 4, 3, 2, 1]:
        cnt = breakdown.get(r, 0)
        pct = int(round((cnt / review_count) * 100)) if review_count > 0 else 0
        breakdown_rows.append({"stars": r, "count": cnt, "percent": pct})

    return {
        "items_given": items_given,
        "active_listings": active_listings,
        "successful_exchanges": exchanges_completed,
        "avg_rating": avg_rating,
        "review_count": review_count,
        "stars": stars,
        "rating_breakdown": breakdown,
        "breakdown_rows": breakdown_rows,
    }


def get_user_badges(user, stats=None):
    """
    Determine community badges earned by the user:
    1. Verified Account: Profile is verified or staff/admin
    2. Reuse Starter: 1+ items given away or 1+ exchanges completed
    3. Eco Contributor: 5+ items given away
    4. Community Helper: 8+ exchanges or rating >= 4.5 with at least 3 reviews
    """
    if stats is None:
        stats = get_user_stats(user)

    badges = []

    # 1. Verification Indicator (email/account verified)
    is_verified = False
    if hasattr(user, "profile") and user.profile.is_verified:
        is_verified = True
    elif user.is_staff or user.is_superuser:
        is_verified = True

    if is_verified:
        badges.append({
            "code": "verified",
            "name": "Verified Account",
            "icon": "verified",
            "css_class": "badge-verified",
            "description": "Authentic community member verified by ReuseHub moderation.",
        })

    # 2. Reuse Starter
    if stats["items_given"] >= 1 or stats["successful_exchanges"] >= 1:
        badges.append({
            "code": "reuse_starter",
            "name": "Reuse Starter",
            "icon": "starter",
            "css_class": "badge-starter",
            "description": "Passed on their first item or completed an exchange to keep goods circulating.",
        })

    # 3. Eco Contributor
    if stats["items_given"] >= 5:
        badges.append({
            "code": "eco_contributor",
            "name": "Eco Contributor",
            "icon": "eco",
            "css_class": "badge-eco",
            "description": "5+ pre-loved belongings rehomed, preventing unnecessary waste.",
        })

    # 4. Community Helper
    if stats["successful_exchanges"] >= 8 or (stats["review_count"] >= 3 and stats["avg_rating"] >= 4.5):
        badges.append({
            "code": "community_helper",
            "name": "Community Helper",
            "icon": "helper",
            "css_class": "badge-helper",
            "description": "Trusted neighbour recognized for prompt, kind, and reliable exchanges.",
        })

    return badges
