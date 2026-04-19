"""
Module de réconciliation pour assurer la cohérence des données
Détecte et enregistre les discrepancies entre les données dénormalisées
"""
from decimal import Decimal
from django.db import transaction, models
from django.utils import timezone
from .models import FinancialTransaction, Expense


class ReconciliationService:
    """Service de vérification et correction des données"""

    @staticmethod
    def check_invoice_total_vs_payments(invoice):
        """Vérifie que le total facturé == somme des paiements"""
        from sales.models import Payment
        
        actual_payments = Payment.objects.filter(invoice=invoice).aggregate(
            total=models.Sum('amount')
        )['total'] or Decimal('0.00')
        
        if invoice.paid_amount != actual_payments:
            return {
                'status': 'MISMATCH',
                'invoice_id': invoice.id,
                'invoice_total': invoice.paid_amount,
                'actual_payments': actual_payments,
                'difference': invoice.paid_amount - actual_payments,
                'type': 'INVOICE_PAYMENT_MISMATCH',
            }
        return {'status': 'OK'}

    @staticmethod
    def check_stock_balance_vs_movements(product, depot):
        """Vérifie que le stock enregistré == somme des mouvements"""
        from inventory.models import StockMovement, StockBalance, StockMovementItem
        
        try:
            balance = StockBalance.objects.get(product=product, depot=depot)
        except StockBalance.DoesNotExist:
            return {'status': 'MISSING_BALANCE', 'product_id': product.id, 'depot_id': depot.id}
        
        # Calculer les mouvements: entrées (depot_to) moins sorties (depot_from)
        # Les mouvements sont enregistrés via StockMovementItem
        movements_in = StockMovementItem.objects.filter(
            product=product,
            movement__depot_to=depot,
            movement__movement_type='IN'
        )
        movements_out = StockMovementItem.objects.filter(
            product=product,
            movement__depot_from=depot,
            movement__movement_type__in=['OUT', 'TRANSFER']
        )
        movements_transfer_in = StockMovementItem.objects.filter(
            product=product,
            movement__depot_to=depot,
            movement__movement_type='TRANSFER'
        )
        
        in_qty = sum(m.qty_packs for m in movements_in) + sum(m.qty_packs for m in movements_transfer_in)
        out_qty = sum(m.qty_packs for m in movements_out)
        expected_qty = in_qty - out_qty
        
        if balance.qty_packs != expected_qty:
            return {
                'status': 'MISMATCH',
                'product_id': product.id,
                'depot_id': depot.id,
                'recorded_qty': balance.qty_packs,
                'expected_qty': expected_qty,
                'difference': balance.qty_packs - expected_qty,
                'type': 'STOCK_BALANCE_MISMATCH',
            }
        return {'status': 'OK'}

    @staticmethod
    def check_financial_transaction_consistency():
        """Vérifie la cohérence des transactions financières"""
        discrepancies = []
        
        for txn in FinancialTransaction.objects.all():
            # Vérifier que expense_id_value pointe vers une Expense valide
            if txn.expense_id_value:
                try:
                    expense = Expense.objects.get(id=txn.expense_id_value)
                    if abs(expense.amount - txn.amount) > Decimal('0.01'):
                        discrepancies.append({
                            'type': 'EXPENSE_AMOUNT_MISMATCH',
                            'transaction_id': txn.id,
                            'expense_id': txn.expense_id_value,
                            'transaction_amount': float(txn.amount),
                            'expense_amount': float(expense.amount),
                        })
                except Expense.DoesNotExist:
                    discrepancies.append({
                        'type': 'MISSING_EXPENSE',
                        'transaction_id': txn.id,
                        'expense_id': txn.expense_id_value,
                    })
        
        return discrepancies

    @staticmethod
    def sync_invoice_paid_amount(invoice):
        """Resynchronise le montant payé d'une facture"""
        from sales.models import Payment
        
        actual = Payment.objects.filter(invoice=invoice).aggregate(
            total=models.Sum('amount')
        )['total'] or Decimal('0.00')
        
        if invoice.paid_amount != actual:
            invoice.paid_amount = actual
            invoice.save(update_fields=['paid_amount'])
            return True
        return False

    @staticmethod
    def sync_stock_balance(product, depot):
        """Resynchronise le solde de stock"""
        from inventory.models import StockMovement, StockBalance, StockMovementItem
        
        # Calculer les mouvements: entrées (depot_to) moins sorties (depot_from)
        movements_in = StockMovementItem.objects.filter(
            product=product,
            movement__depot_to=depot,
            movement__movement_type='IN'
        )
        movements_out = StockMovementItem.objects.filter(
            product=product,
            movement__depot_from=depot,
            movement__movement_type__in=['OUT', 'TRANSFER']
        )
        movements_transfer_in = StockMovementItem.objects.filter(
            product=product,
            movement__depot_to=depot,
            movement__movement_type='TRANSFER'
        )
        
        in_qty = sum(m.qty_packs for m in movements_in) + sum(m.qty_packs for m in movements_transfer_in)
        out_qty = sum(m.qty_packs for m in movements_out)
        expected_qty = in_qty - out_qty
        
        balance, created = StockBalance.objects.get_or_create(
            product=product, depot=depot,
            defaults={'qty_packs': expected_qty}
        )
        
        if balance.qty_packs != expected_qty:
            balance.qty_packs = expected_qty
            balance.save(update_fields=['qty_packs'])
            return True
        return False
