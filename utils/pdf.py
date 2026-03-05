from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.template.loader import render_to_string


def _default_base_url() -> str:
    """File base for resolving relative static/media assets."""
    return Path(settings.BASE_DIR).as_uri() + "/"


def render_pdf(template: str, context: dict, request=None) -> bytes:
    """
    Render a Django template to PDF using WeasyPrint only.
    request is optional; when provided, absolute URI helps resolve /static and /media.
    """
    html_string = render_to_string(template, context)
    base_url = request.build_absolute_uri("/") if request else _default_base_url()
    try:
        from weasyprint import HTML
        return HTML(string=html_string, base_url=base_url).write_pdf()
    except Exception as e:
        raise ValidationError(
            "PDF generation failed with WeasyPrint. "
            "Ensure system dependencies are installed on this host."
        ) from e


def html_string_to_pdf(html_string: str, request=None, base_url: str | None = None) -> bytes:
    """Convert raw HTML string to PDF with WeasyPrint only."""
    effective_base_url = base_url or (request.build_absolute_uri("/") if request else _default_base_url())
    try:
        from weasyprint import HTML
        return HTML(string=html_string, base_url=effective_base_url).write_pdf()
    except Exception as e:
        raise ValidationError(
            "PDF generation failed with WeasyPrint. "
            "Ensure system dependencies are installed on this host."
        ) from e

