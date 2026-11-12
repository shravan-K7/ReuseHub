import re
from urllib.parse import urlencode

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist


def normalize_phone_for_whatsapp(raw_phone, default_country_code=None):
    """Normalize a stored phone string into E.164 digits without a leading '+', or return None."""
    if not raw_phone:
        return None

    cleaned = str(raw_phone).strip()
    if not cleaned or any(ch.isalpha() for ch in cleaned):
        return None

    if default_country_code is None:
        default_country_code = getattr(settings, "DEFAULT_WHATSAPP_COUNTRY_CODE", "91")
    country_code = re.sub(r"\D", "", str(default_country_code or "91")) or "91"

    has_explicit_country_code = cleaned.startswith("+") or cleaned.startswith("00")
    digits = re.sub(r"\D", "", cleaned)

    if cleaned.startswith("00") and digits.startswith("00"):
        digits = digits[2:]

    if not digits or not digits.strip("0"):
        return None

    if not has_explicit_country_code:
        if digits.startswith("0"):
            digits = digits.lstrip("0")
        if len(digits) < 7:
            return None
        if len(digits) == 10:
            digits = f"{country_code}{digits}"
        elif len(digits) < 10 and not digits.startswith(country_code):
            digits = f"{country_code}{digits}"

    if not (7 <= len(digits) <= 15):
        return None

    return digits


def build_whatsapp_redirect_url(raw_phone, message=None, default_country_code=None):
    """Build a https://wa.me/<digits> URL that opens WhatsApp app or WhatsApp Web."""
    normalized = normalize_phone_for_whatsapp(
        raw_phone, default_country_code=default_country_code
    )
    if not normalized:
        return None

    base_url = f"https://wa.me/{normalized}"
    if message:
        return f"{base_url}?{urlencode({'text': message})}"
    return base_url


def get_owner_phone_for_accepted_request(item_request):
    """Return the item owner's phone number only when the request status is ACCEPTED."""
    if item_request is None or getattr(item_request, "status", None) != "ACCEPTED":
        return ""

    item = getattr(item_request, "item", None)
    donor = getattr(item, "donor", None) if item is not None else None
    if donor is None:
        return ""

    try:
        profile = donor.profile
    except ObjectDoesNotExist:
        return ""

    return getattr(profile, "phone", "") or ""


def get_owner_whatsapp_url(item_request):
    """Fetch the item owner's phone for an accepted request and return a WhatsApp chat URL, or None."""
    raw_phone = get_owner_phone_for_accepted_request(item_request)
    if not raw_phone:
        return None

    item = item_request.item
    donor = item.donor
    message = (
        f"Hi @{donor.username}, my request for '{item.title}' on ReuseHub was accepted. "
        "When would be a good time to coordinate pickup?"
    )
    return build_whatsapp_redirect_url(raw_phone, message=message)

