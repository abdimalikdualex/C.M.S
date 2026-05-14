"""
Digital coursework uploads: validation for all ICT Hub assignment types.

Supports images, archives, office docs, video containers, code text files, etc.
"""
from __future__ import annotations

import os
import re

from django.core.exceptions import ValidationError

# Per-file limit (bytes)
MAX_SUBMISSION_FILE_BYTES = 25 * 1024 * 1024

# Total count of *new* files in one POST (plus existing attachments in DB)
MAX_FILES_PER_SUBMISSION_POST = 12

# Allowed extensions (lowercase, leading dot)
ALLOWED_SUBMISSION_EXTENSIONS = frozenset(
    {
        ".pdf",
        ".zip",
        ".rar",
        ".7z",
        ".tar",
        ".gz",
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".webp",
        ".psd",
        ".tif",
        ".tiff",
        ".bmp",
        ".py",
        ".js",
        ".mjs",
        ".ts",
        ".html",
        ".htm",
        ".css",
        ".scss",
        ".sass",
        ".txt",
        ".md",
        ".json",
        ".xml",
        ".csv",
        ".xlsx",
        ".xls",
        ".ppt",
        ".pptx",
        ".doc",
        ".docx",
        ".mp4",
        ".mov",
        ".webm",
        ".mkv",
        ".avi",
        ".c",
        ".cpp",
        ".h",
        ".java",
        ".cs",
        ".go",
        ".rb",
        ".php",
        ".sql",
        ".swift",
        ".kt",
        ".rs",
        ".dart",
        ".ipynb",
    }
)

IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"})

_URL_RE = re.compile(r"^https?://[^\s]+$", re.I)


def normalize_optional_url(value: str | None) -> str:
    s = (value or "").strip()
    return s


def validate_optional_http_url(label: str, value: str) -> None:
    if not value:
        return
    if not _URL_RE.match(value):
        raise ValidationError(f"{label} must be a valid http(s) URL.")
    if len(value) > 500:
        raise ValidationError(f"{label} is too long.")


def ext_from_upload_name(name: str) -> str:
    return os.path.splitext((name or "").strip())[1].lower()


def is_image_extension(ext: str) -> bool:
    return ext in IMAGE_EXTENSIONS


def validate_submission_upload(f) -> None:
    """
    Validate a single uploaded file (Django UploadedFile).
    Raises ValidationError on failure.
    """
    if not f:
        raise ValidationError("Empty file upload.")
    name = getattr(f, "name", "") or ""
    ext = ext_from_upload_name(name)
    if ext not in ALLOWED_SUBMISSION_EXTENSIONS:
        raise ValidationError(
            f"File type “{ext or 'unknown'}” is not allowed. "
            "Use PDF, Office files, images (JPG/PNG/…), ZIP, video, or common code/data formats."
        )
    size = getattr(f, "size", None)
    if size is not None and size > MAX_SUBMISSION_FILE_BYTES:
        raise ValidationError("Each file must be 25 MB or smaller.")
