"""Context processors for legal app: EULA banner visibility."""

from .utils import user_has_accepted_eula


def eula_banner(request):
    """
    Add EULA banner state to template context.
    - show_eula_banner: True if the user is logged in and has not yet accepted (and is not deemed accepted by 30-day use).
    - has_accepted_eula: True if the user is considered to have accepted (explicit or deemed).
    """
    if not request.user.is_authenticated:
        return {"show_eula_banner": False, "has_accepted_eula": True}
    has_accepted = user_has_accepted_eula(request.user)
    return {
        "show_eula_banner": not has_accepted,
        "has_accepted_eula": has_accepted,
    }
