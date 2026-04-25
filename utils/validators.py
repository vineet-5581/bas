"""
Input validation utilities
"""
from pathlib import Path
from typing import Tuple
from config.constants import SUPPORTED_INPUT_FORMATS, SUPPORTED_OUTPUT_FORMATS
from config.settings import settings


class ValidationError(Exception):
    """Validation error"""
    pass


def validate_input_file(file_path: str) -> Path:
    """Validate input PDF file"""
    path = Path(file_path)

    # Check if file exists
    if not path.exists():
        raise ValidationError(f"File not found: {file_path}")

    # Check file extension
    if path.suffix.lower() not in SUPPORTED_INPUT_FORMATS:
        raise ValidationError(
            f"Invalid file format. Supported formats: {SUPPORTED_INPUT_FORMATS}"
        )

    # Check file size
    file_size_mb = path.stat().st_size / (1024 * 1024)
    if file_size_mb > settings.MAX_UPLOAD_SIZE_MB:
        raise ValidationError(
            f"File size exceeds limit: {file_size_mb:.2f}MB "
            f"(max: {settings.MAX_UPLOAD_SIZE_MB}MB)"
        )

    return path


def validate_output_path(file_path: str) -> Path:
    """Validate output file path"""
    path = Path(file_path)

    # Check parent directory exists or can be created
    path.parent.mkdir(parents=True, exist_ok=True)

    # Check file extension
    if path.suffix.lower() not in SUPPORTED_OUTPUT_FORMATS:
        raise ValidationError(
            f"Invalid output format. Supported formats: {SUPPORTED_OUTPUT_FORMATS}"
        )

    return path


def validate_page_range(total_pages: int, start: int = 1, end: int = None) -> Tuple[int, int]:
    """Validate and normalize page range"""
    if start < 1:
        raise ValidationError("Start page must be >= 1")

    if end is None:
        end = total_pages
    elif end > total_pages:
        raise ValidationError(f"End page exceeds document pages: {total_pages}")
    elif start > end:
        raise ValidationError("Start page must be <= end page")

    return start, end
