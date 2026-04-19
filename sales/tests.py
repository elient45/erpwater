from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from accounts.models import UserProfile
from inventory.models import Depot, Product, StockBalance
from sales.models import Client, FinancialAccount, Invoice, InvoiceItem, Payment
from sales.services import cancel_invoice, recompute_invoice_totals, validate_invoice


class InvoiceWorkflowTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()
        self.staff_user = self.user_model.objects.create_user(username="staff", password="test123")
        self.admin_user = self.user_model.objects.create_user(username="admin", password="test123")

        UserProfile.objects.create(user=self.staff_user, role=UserProfile.ROLE_STAFF)
        UserProfile.objects.create(user=self.admin_user, role=UserProfile.ROLE_ADMIN)

        self.client_obj = Client.objects.create(name="Client Test")
        self.depot = Depot.objects.create(name="Depot Principal", is_active=True)
        self.product = Product.objects.create(
            name="Eau 1.5L",
            sachets_per_pack=12,
            default_sale_price=Decimal("2500.00"),
        )
        StockBalance.objects.create(depot=self.depot, product=self.product, qty_packs=10)
        self.account = FinancialAccount.objects.create(
            name="Caisse principale",
            account_type=FinancialAccount.ACCOUNT_TYPE_CASH,
        )

    def create_invoice(self, *, source_depot=None):
        invoice = Invoice.objects.create(
            number=f"FAC-TEST-{Invoice.objects.count() + 1}",
            customer=self.client_obj,
            created_by=self.staff_user,
            source_depot=source_depot,
            issue_date=timezone.now(),
            tax_rate=Decimal("16.00"),
        )
        InvoiceItem.objects.create(
            invoice=invoice,
            product=self.product,
            qty_packs=4,
            unit_price=Decimal("2500.00"),
            discount=Decimal("0.00"),
            line_total=Decimal("10000.00"),
        )
        recompute_invoice_totals(invoice)
        invoice.refresh_from_db()
        return invoice

    def test_validate_invoice_requires_source_depot(self):
        invoice = self.create_invoice()

        with self.assertRaises(ValidationError):
            validate_invoice(invoice, self.staff_user)

    def test_payment_is_blocked_for_draft_invoice(self):
        invoice = self.create_invoice(source_depot=self.depot)
        payment = Payment(
            invoice=invoice,
            account=self.account,
            received_by=self.staff_user,
            paid_at=timezone.now(),
            amount=Decimal("1000.00"),
            method=Payment.METHOD_CASH,
        )

        with self.assertRaises(ValidationError):
            payment.full_clean()

    def test_admin_can_cancel_validated_invoice_and_restore_stock(self):
        invoice = self.create_invoice(source_depot=self.depot)
        validate_invoice(invoice, self.staff_user)
        invoice.refresh_from_db()

        balance = StockBalance.objects.get(depot=self.depot, product=self.product)
        self.assertEqual(balance.qty_packs, 6)

        cancel_invoice(invoice, self.admin_user, "Client annule la commande avant livraison.")
        invoice.refresh_from_db()
        balance.refresh_from_db()

        self.assertEqual(invoice.status, Invoice.STATUS_CANCELLED)
        self.assertEqual(invoice.cancelled_by, self.admin_user)
        self.assertTrue(invoice.cancellation_reason)
        self.assertEqual(balance.qty_packs, 10)

    def test_non_admin_cannot_cancel_invoice(self):
        invoice = self.create_invoice(source_depot=self.depot)
        validate_invoice(invoice, self.staff_user)

        with self.assertRaises(ValidationError):
            cancel_invoice(invoice, self.staff_user, "Tentative non autorisee.")
