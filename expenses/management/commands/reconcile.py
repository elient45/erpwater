from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from decimal import Decimal

from expenses.models import ReconciliationLog
from expenses.reconciliation import ReconciliationService
from sales.models import Invoice
from inventory.models import StockBalance, Product, Depot


class Command(BaseCommand):
    help = 'Exécute les vérifications de réconciliation et enregistre les discrepancies'

    def add_arguments(self, parser):
        parser.add_argument(
            '--type',
            type=str,
            choices=['all', 'invoices', 'stock', 'transactions', 'soft_links'],
            default='all',
            help='Type de réconciliation à exécuter'
        )
        parser.add_argument(
            '--fix',
            action='store_true',
            help='Corriger automatiquement les discrepancies détectables'
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Afficher les détails complets'
        )

    def handle(self, *args, **options):
        reconciliation_type = options['type']
        auto_fix = options['fix']
        verbose = options['verbose']
        
        discrepancies_found = 0
        auto_fixed = 0
        
        self.stdout.write(
            self.style.SUCCESS(f"🔍 Démarrage de la réconciliation ({reconciliation_type})")
        )

        # Vérifier les factures
        if reconciliation_type in ['all', 'invoices']:
            self.stdout.write("  Vérification des factures...")
            for invoice in Invoice.objects.all():
                result = ReconciliationService.check_invoice_total_vs_payments(invoice)
                if result['status'] == 'MISMATCH':
                    discrepancies_found += 1
                    if verbose:
                        self.stdout.write(f"    ❌ Invoice #{invoice.id}: {result}")
                    
                    # Enregistrer la discrepancy
                    ReconciliationLog.objects.create(
                        discrepancy_type=ReconciliationLog.TYPE_INVOICE_PAYMENT_MISMATCH,
                        object_app='sales',
                        object_model='Invoice',
                        object_id=invoice.id,
                        expected_value=str(result['actual_payments']),
                        actual_value=str(result['invoice_total']),
                        detail=result,
                        status=ReconciliationLog.STATUS_DETECTED if not auto_fix else ReconciliationLog.STATUS_AUTO_FIXED,
                    )
                    
                    if auto_fix:
                        ReconciliationService.sync_invoice_paid_amount(invoice)
                        auto_fixed += 1
                        if verbose:
                            self.stdout.write(f"    ✅ Facture #{invoice.id} corrigée")

        # Vérifier le stock
        if reconciliation_type in ['all', 'stock']:
            self.stdout.write("  Vérification du stock...")
            for balance in StockBalance.objects.select_related('product', 'depot'):
                result = ReconciliationService.check_stock_balance_vs_movements(
                    balance.product, balance.depot
                )
                if result['status'] == 'MISMATCH':
                    discrepancies_found += 1
                    if verbose:
                        self.stdout.write(f"    ❌ Stock #{balance.id}: {result}")
                    
                    ReconciliationLog.objects.create(
                        discrepancy_type=ReconciliationLog.TYPE_STOCK_BALANCE_MISMATCH,
                        object_app='inventory',
                        object_model='StockBalance',
                        object_id=balance.id,
                        expected_value=str(result['expected_qty']),
                        actual_value=str(result['recorded_qty']),
                        detail=result,
                        status=ReconciliationLog.STATUS_DETECTED if not auto_fix else ReconciliationLog.STATUS_AUTO_FIXED,
                    )
                    
                    if auto_fix:
                        ReconciliationService.sync_stock_balance(balance.product, balance.depot)
                        auto_fixed += 1
                        if verbose:
                            self.stdout.write(f"    ✅ Stock #{balance.id} corrigé")

        # Vérifier les transactions
        if reconciliation_type in ['all', 'transactions']:
            self.stdout.write("  Vérification des transactions...")
            discrepancies = ReconciliationService.check_financial_transaction_consistency()
            discrepancies_found += len(discrepancies)
            
            for disc in discrepancies:
                if verbose:
                    self.stdout.write(f"    ❌ Txn #{disc['transaction_id']}: {disc['type']}")
                
                ReconciliationLog.objects.create(
                    discrepancy_type=ReconciliationLog.TYPE_EXPENSE_AMOUNT_MISMATCH,
                    object_app='expenses',
                    object_model='FinancialTransaction',
                    object_id=disc['transaction_id'],
                    detail=disc,
                    status=ReconciliationLog.STATUS_MANUAL_REVIEW,
                )

        # Vérifier les soft links
        if reconciliation_type in ['all', 'soft_links']:
            self.stdout.write("  Vérification des soft links...")
            # À implémenter selon les besoins spécifiques

        # Résumé
        self.stdout.write(self.style.SUCCESS(
            f"\n✓ Réconciliation terminée:\n"
            f"  - Discrepancies trouvées: {discrepancies_found}\n"
            f"  - Auto-corrigées: {auto_fixed}\n"
            f"  - Requièrent révision manuelle: {discrepancies_found - auto_fixed}"
        ))
