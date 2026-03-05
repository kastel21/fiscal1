from django.contrib.auth.models import User
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.exceptions import ValidationError
from django.test import RequestFactory, TestCase
from django.contrib.sessions.middleware import SessionMiddleware

from fiscal.models import (
    DocumentSequence,
    DocumentSequenceAdjustment,
    InvoiceSequence,
)
from fiscal.services.invoice_number import adjust_document_sequence
from fiscal.views_fdms import fdms_sequence_adjustment


class SequenceAdjustmentServiceTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            username="seqadmin",
            password="pw12345",
            is_staff=True,
            is_superuser=True,
        )
        self.year = 2026

    def test_set_next_updates_sequence_and_audit(self):
        seq = InvoiceSequence.objects.create(year=self.year, last_number=10)

        result = adjust_document_sequence(
            "INVOICE",
            self.year,
            set_next=25,
            reason="Resync after manual import",
            user=self.staff,
        )

        seq.refresh_from_db()
        self.assertEqual(seq.last_number, 24)
        self.assertEqual(result["old_last_number"], 10)
        self.assertEqual(result["new_last_number"], 24)
        self.assertEqual(result["next_number_preview"], "INV-2026-25")

        audit = DocumentSequenceAdjustment.objects.latest("changed_at")
        self.assertEqual(audit.document_type, "INVOICE")
        self.assertEqual(audit.mode, "set_next")
        self.assertEqual(audit.value, 25)
        self.assertEqual(audit.old_last_number, 10)
        self.assertEqual(audit.new_last_number, 24)
        self.assertEqual(audit.changed_by_id, self.staff.id)

    def test_skip_by_updates_document_sequence_and_audit(self):
        seq = DocumentSequence.objects.create(
            year=self.year,
            document_type="DEBIT_NOTE",
            last_number=5,
        )

        result = adjust_document_sequence(
            "DEBIT_NOTE",
            self.year,
            skip_by=3,
            reason="Skipped damaged booklet range",
            user=self.staff,
        )

        seq.refresh_from_db()
        self.assertEqual(seq.last_number, 8)
        self.assertEqual(result["next_number_preview"], "DB-2026-9")

        audit = DocumentSequenceAdjustment.objects.latest("changed_at")
        self.assertEqual(audit.document_type, "DEBIT_NOTE")
        self.assertEqual(audit.mode, "skip_by")
        self.assertEqual(audit.value, 3)
        self.assertEqual(audit.old_last_number, 5)
        self.assertEqual(audit.new_last_number, 8)

    def test_creates_sequence_row_if_missing(self):
        self.assertFalse(InvoiceSequence.objects.filter(year=self.year).exists())
        result = adjust_document_sequence(
            "INVOICE",
            self.year,
            skip_by=2,
            reason="Initialize sequence",
            user=self.staff,
        )
        seq = InvoiceSequence.objects.get(year=self.year)
        self.assertEqual(seq.last_number, 2)
        self.assertEqual(result["next_number_preview"], "INV-2026-3")

    def test_invalid_input_cases(self):
        with self.assertRaises(ValidationError):
            adjust_document_sequence(
                "INVOICE",
                self.year,
                set_next=10,
                skip_by=2,
                reason="bad",
                user=self.staff,
            )
        with self.assertRaises(ValidationError):
            adjust_document_sequence(
                "INVOICE",
                self.year,
                reason="bad",
                user=self.staff,
            )
        with self.assertRaises(ValidationError):
            adjust_document_sequence(
                "INVOICE",
                self.year,
                skip_by=-1,
                reason="bad",
                user=self.staff,
            )

    def test_prevents_backward_set_next(self):
        InvoiceSequence.objects.create(year=self.year, last_number=50)
        with self.assertRaises(ValidationError):
            adjust_document_sequence(
                "INVOICE",
                self.year,
                set_next=40,
                reason="attempt backwards",
                user=self.staff,
            )


class SequenceAdjustmentViewTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            username="staffuser",
            password="pw12345",
            is_staff=True,
            is_superuser=True,
        )
        self.non_staff = User.objects.create_user(
            username="regular",
            password="pw12345",
            is_staff=False,
        )
        self.rf = RequestFactory()

    def _attach_session_and_messages(self, request):
        middleware = SessionMiddleware(lambda req: None)
        middleware.process_request(request)
        request.session.save()
        setattr(request, "_messages", FallbackStorage(request))
        return request

    def test_non_staff_access_denied(self):
        req = self.rf.get("/fdms/sequences/adjust/")
        req.user = self.non_staff
        req = self._attach_session_and_messages(req)
        resp = fdms_sequence_adjustment(req)
        self.assertEqual(resp.status_code, 302)

    def test_staff_can_adjust_and_create_audit(self):
        req = self.rf.post(
            "/fdms/sequences/adjust/",
            data={
                "document_type": "CREDIT_NOTE",
                "year": 2026,
                "mode": "set_next",
                "value": 12,
                "reason": "Resync from paper records",
            },
        )
        req.user = self.staff
        req = self._attach_session_and_messages(req)
        resp = fdms_sequence_adjustment(req)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(
            DocumentSequence.objects.filter(
                year=2026, document_type="CREDIT_NOTE", last_number=11
            ).exists()
        )
        self.assertTrue(
            DocumentSequenceAdjustment.objects.filter(
                document_type="CREDIT_NOTE",
                mode="set_next",
                value=12,
                changed_by=self.staff,
            ).exists()
        )

