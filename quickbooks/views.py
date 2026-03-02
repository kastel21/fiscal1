"""
QuickBooks OAuth2 and API views. No frontend UI; backend only.
"""

import json
import logging
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import redirect
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from quickbooks.models import QuickBooksToken, QuickBooksWebhookEvent
from quickbooks.services import (
    build_connect_url,
    exchange_code_for_tokens,
    revoke_quickbooks_token,
    pull_invoices,
    push_invoice_update,
)
from quickbooks.utils import QuickBooksAPIException, QuickBooksTokenError, verify_qb_webhook_signature

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Webhook: QuickBooks invoice events (signature verified, process async)
# ---------------------------------------------------------------------------


@csrf_exempt
@require_POST
def qb_webhook(request):
    """
    POST /qb/webhook/
    QuickBooks webhook. Verify intuit-signature (HMAC SHA256), parse eventNotifications,
    persist only Invoice events to QuickBooksWebhookEvent, trigger Celery task.
    Return 200 quickly. Never fiscalise in view. Never process unverified webhooks.
    """
    raw_body = request.body
    if raw_body is None:
        raw_body = b""
    signature_header = (request.META.get("HTTP_INTUIT_SIGNATURE") or "").strip()

    if not verify_qb_webhook_signature(raw_body, signature_header):
        logger.warning(
            "QuickBooks webhook signature verification failed",
            extra={"realm_id": None, "event_type": "webhook", "verification": "failed"},
        )
        return HttpResponseForbidden(b"Invalid signature")

    try:
        body = json.loads(raw_body.decode("utf-8") if raw_body else "{}")
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        logger.warning(
            "QuickBooks webhook malformed JSON",
            extra={"error": str(e), "verification": "success"},
        )
        return JsonResponse({"status": "ok"}, status=200)

    event_notifications = body.get("eventNotifications") or []
    event_time = timezone.now()

    for notif in event_notifications:
        dce = notif.get("dataChangeEvent") or {}
        realm_id = str(dce.get("realmId") or body.get("realmId") or "")
        entities = dce.get("entities") or []
        for entity in entities:
            name = (entity.get("name") or "").strip()
            if name != "Invoice":
                continue
            entity_id = entity.get("id")
            if not entity_id:
                continue
            entity_id = str(entity_id)
            operation = (entity.get("operation") or "").strip()
            event_type = operation or "Create"
            try:
                ev = QuickBooksWebhookEvent.objects.create(
                    realm_id=realm_id,
                    event_type=event_type,
                    entity_name=name,
                    entity_id=entity_id,
                    event_time=event_time,
                    payload=dict(notif),
                    processed=False,
                )
                from quickbooks.tasks import process_qb_invoice_webhook
                process_qb_invoice_webhook.delay(realm_id, entity_id)
                logger.info(
                    "QuickBooks webhook event saved and task queued",
                    extra={
                        "realm_id": realm_id,
                        "invoice_id": entity_id,
                        "event_type": event_type,
                        "verification": "success",
                        "webhook_event_id": ev.pk,
                    },
                )
            except Exception as e:
                logger.exception(
                    "QuickBooks webhook save/task queue failed: %s",
                    e,
                    extra={
                        "realm_id": realm_id,
                        "invoice_id": entity_id,
                        "event_type": event_type,
                        "verification": "success",
                    },
                )

    return JsonResponse({"status": "ok"}, status=200)


def _get_user(request):
    """Return request.user if authenticated, else None (multi-tenant may key by session/realm only)."""
    return getattr(request, "user", None) if getattr(request, "user", None) and request.user.is_authenticated else None


# ---------------------------------------------------------------------------
# Connect: redirect to Intuit OAuth2
# ---------------------------------------------------------------------------


@require_GET
def qb_connect(request):
    """
    GET /qb/connect/
    Redirect user to Intuit OAuth2 authorization page.
    Stores state in session for callback verification.
    """
    try:
        state = request.session.get("qb_oauth_state")
        url, state = build_connect_url(state=state)
        request.session["qb_oauth_state"] = state
        request.session.modified = True
        return redirect(url)
    except QuickBooksTokenError as e:
        logger.warning("QuickBooks connect failed: %s", e)
        return HttpResponseBadRequest(f"QuickBooks connect not configured: {e}")


# ---------------------------------------------------------------------------
# Callback: exchange code for tokens
# ---------------------------------------------------------------------------


@require_GET
def qb_callback(request):
    """
    GET /qb/callback/?code=...&realmId=...&state=...
    Exchange authorization code for tokens and store in QuickBooksToken.
    """
    code = request.GET.get("code")
    realm_id = request.GET.get("realmId") or request.GET.get("realm_id")
    state_in = request.GET.get("state")
    state_stored = request.session.pop("qb_oauth_state", None)

    if not code or not realm_id:
        logger.warning("QuickBooks callback missing code or realmId")
        return HttpResponseBadRequest("Missing code or realmId.")

    if state_stored and state_in != state_stored:
        logger.warning("QuickBooks callback state mismatch")
        return HttpResponseBadRequest("Invalid state.")

    try:
        user = _get_user(request)
        exchange_code_for_tokens(code=code, realm_id=realm_id, user=user)
    except QuickBooksTokenError as e:
        logger.exception("QuickBooks callback token exchange failed: %s", e)
        return HttpResponseBadRequest(f"Token exchange failed: {e}")

    # Success: return simple success page (no frontend UI required)
    html = (
        "<!DOCTYPE html><html><head><title>QuickBooks Connected</title></head><body>"
        "<h1>QuickBooks connected successfully</h1><p>You can close this page.</p></body></html>"
    )
    return HttpResponse(html, content_type="text/html")


# ---------------------------------------------------------------------------
# Disconnect: revoke and deactivate token
# ---------------------------------------------------------------------------


@require_http_methods(["GET", "POST"])
def qb_disconnect(request):
    """
    GET/POST /qb/disconnect/
    Optional: ?realm_id=... to disconnect a specific realm; otherwise use first active token.
    Revokes token at Intuit and marks token inactive, clearing stored tokens.
    """
    realm_id = request.GET.get("realm_id") or (request.POST.get("realm_id") if request.method == "POST" else None)
    user = _get_user(request)

    qs = QuickBooksToken.objects.filter(is_active=True)
    if realm_id:
        qs = qs.filter(realm_id=realm_id)
    if user is not None:
        qs = qs.filter(user=user)
    token = qs.order_by("-updated_at").first()

    if not token:
        return JsonResponse({"success": False, "error": "No active QuickBooks connection found."}, status=404)

    try:
        revoke_quickbooks_token(token)
        return JsonResponse({"success": True, "message": "QuickBooks disconnected."})
    except Exception as e:
        logger.exception("QuickBooks disconnect failed: %s", e)
        return JsonResponse({"success": False, "error": str(e)}, status=500)


# ---------------------------------------------------------------------------
# Invoices: pull
# ---------------------------------------------------------------------------


@require_GET
def qb_invoices_pull(request):
    """
    GET /qb/invoices/pull/?realm_id=...&max_results=20
    Pull invoices from QuickBooks for the given realm. Requires valid token.
    """
    realm_id = request.GET.get("realm_id")
    if not realm_id:
        return JsonResponse({"error": "realm_id is required."}, status=400)
    try:
        max_results = min(int(request.GET.get("max_results", 20)), 100)
    except ValueError:
        max_results = 20

    user = _get_user(request)
    try:
        invoices = pull_invoices(realm_id=realm_id, user=user, max_results=max_results)
        return JsonResponse({"invoices": invoices})
    except (QuickBooksTokenError, QuickBooksAPIException) as e:
        logger.warning("QuickBooks invoice pull failed: %s", e)
        return JsonResponse({"error": str(e)}, status=400)


# ---------------------------------------------------------------------------
# Invoices: push (update after fiscalisation)
# ---------------------------------------------------------------------------


@require_http_methods(["GET", "POST"])
def qb_invoices_push(request, invoice_id):
    """
    GET/POST /qb/invoices/push/<invoice_id>/
    Query or JSON body: realm_id (required), sync_token (required), private_note (optional).
    Updates QuickBooks invoice (e.g. set PrivateNote with fiscal receipt info).
    """
    if request.method == "POST" and request.content_type and "application/json" in request.content_type:
        try:
            import json
            body = json.loads(request.body.decode("utf-8"))
            realm_id = body.get("realm_id")
            sync_token = body.get("sync_token")
            private_note = body.get("private_note") or body.get("PrivateNote")
        except Exception:
            realm_id = sync_token = private_note = None
    else:
        realm_id = request.GET.get("realm_id") or request.POST.get("realm_id")
        sync_token = request.GET.get("sync_token") or request.POST.get("sync_token")
        private_note = request.GET.get("private_note") or request.POST.get("private_note")

    if not realm_id or sync_token is None:
        return JsonResponse(
            {"error": "realm_id and sync_token are required."},
            status=400,
        )

    user = _get_user(request)
    try:
        result = push_invoice_update(
            realm_id=realm_id,
            invoice_id=invoice_id,
            sync_token=sync_token,
            private_note=private_note,
            user=user,
        )
        return JsonResponse({"success": True, "invoice": result})
    except (QuickBooksTokenError, QuickBooksAPIException) as e:
        logger.warning("QuickBooks invoice push failed: %s", e)
        return JsonResponse({"error": str(e)}, status=400)
