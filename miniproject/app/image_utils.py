import io
import logging
import os
import warnings
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import InMemoryUploadedFile

logger = logging.getLogger(__name__)

# Image processing configuration
MAX_UPLOAD_SIZE = 5 * 1024 * 1024  # 5 MB
MAX_DIMENSION = 1600
WEBP_QUALITY = 82
MAX_PIXELS = 40_000_000  # 40 megapixels ceiling for decompression bomb protection

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}


def validate_image_file(uploaded_file):
    """
    Validates that the uploaded file:
    1. Has a supported extension (.jpg, .jpeg, .png, .webp).
    2. Does not exceed 5 MB in original size.
    3. Contains genuine, valid image content verified via Pillow.
    4. Does not violate decompression bomb safety limits.
    """
    filename = getattr(uploaded_file, "name", "") or ""
    ext = os.path.splitext(filename)[1].lower()

    if ext not in ALLOWED_EXTENSIONS:
        raise ValidationError(
            f"'{filename}' has an unsupported format. Allowed formats: JPEG (.jpg, .jpeg), PNG (.png), and WebP (.webp)."
        )

    size = getattr(uploaded_file, "size", 0) or 0
    if size > MAX_UPLOAD_SIZE:
        size_mb = size / (1024 * 1024)
        raise ValidationError(
            f"'{filename}' exceeds the 5MB limit (size: {size_mb:.1f}MB)."
        )

    if hasattr(uploaded_file, "seek"):
        try:
            uploaded_file.seek(0)
        except Exception:
            pass

    try:
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            try:
                # Open image without fully reading pixel data into memory
                with Image.open(uploaded_file) as img:
                    img_format = (img.format or "").upper()
                    if img_format not in ALLOWED_FORMATS:
                        raise ValidationError(
                            f"'{filename}' is not a valid JPEG, PNG, or WebP image."
                        )

                    width, height = img.size
                    if width * height > MAX_PIXELS or width > 10000 or height > 10000:
                        raise ValidationError(
                            f"'{filename}' dimensions ({width}x{height}) are too large to process safely."
                        )

                    # Verify structural integrity of image headers/data
                    img.verify()
            except Image.DecompressionBombError:
                raise ValidationError(
                    f"'{filename}' exceeds safe image dimension limits (decompression bomb warning)."
                )
    except (UnidentifiedImageError, SyntaxError, ValueError, IOError) as exc:
        if isinstance(exc, ValidationError):
            raise
        raise ValidationError(f"'{filename}' is corrupted or not a valid image.")
    finally:
        if hasattr(uploaded_file, "seek"):
            try:
                uploaded_file.seek(0)
            except Exception:
                pass


def compress_and_convert_to_webp(
    uploaded_file,
    max_dimension=MAX_DIMENSION,
    quality=WEBP_QUALITY,
):
    """
    Compresses an image, resizes it proportionally so neither width nor height
    exceeds max_dimension (preserving aspect ratio and avoiding upscaling),
    corrects EXIF orientation, preserves alpha transparency, and converts to WebP.

    Returns an InMemoryUploadedFile instance suitable for Django model saving.
    """
    if hasattr(uploaded_file, "seek"):
        try:
            uploaded_file.seek(0)
        except Exception:
            pass

    filename = getattr(uploaded_file, "name", "image.jpg") or "image.jpg"
    stem = Path(filename).stem or "image"
    new_filename = f"{stem}.webp"

    try:
        with Image.open(uploaded_file) as img:
            # 1. Correct EXIF orientation (rotation/flipping from phone cameras)
            try:
                img = ImageOps.exif_transpose(img)
            except Exception as e:
                logger.debug("Could not transpose EXIF orientation for %s: %s", filename, e)

            # 2. Resize proportionally without upscaling
            if img.width > max_dimension or img.height > max_dimension:
                img.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)

            # 3. Handle color modes and transparency correctly
            # If the image has alpha channel or palette transparency, convert to RGBA
            # to prevent black backgrounds in WebP format
            if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
                img = img.convert("RGBA")
            elif img.mode != "RGB":
                img = img.convert("RGB")

            # 4. Save to BytesIO buffer in WebP format
            output_io = io.BytesIO()
            img.save(
                output_io,
                format="WEBP",
                quality=quality,
                method=6,
            )
            output_size = output_io.tell()
            output_io.seek(0)

            # 5. Return InMemoryUploadedFile
            return InMemoryUploadedFile(
                file=output_io,
                field_name=getattr(uploaded_file, "field_name", "image"),
                name=new_filename,
                content_type="image/webp",
                size=output_size,
                charset=None,
            )
    except Exception as e:
        logger.error("Failed to compress and convert image %s to WebP: %s", filename, e, exc_info=True)
        if hasattr(uploaded_file, "seek"):
            try:
                uploaded_file.seek(0)
            except Exception:
                pass
        raise
