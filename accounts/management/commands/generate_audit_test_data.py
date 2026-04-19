from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.db import transaction
from decimal import Decimal
from datetime import datetime

from accounts.models import UserProfile, AuditLog
from expenses.models import Expense, ExpenseCategory
from sales.models import Client, Invoice, FinancialAccount
from inventory.models import Product, Depot, StockBalance


class Command(BaseCommand):
    help = 'Génère des logs d\'audit pour les tests'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('🔄 Génération de données test et logs d\'audit...\n'))
        
        with transaction.atomic():
            # Récupérer un utilisateur existant ou en créer un
            try:
                user = User.objects.first()  # Prendre le premier utilisateur existant
                if not user:
                    user = User.objects.create_user(
                        username='testadmin',
                        email='admin@test.com',
                        password='password123'
                    )
                    self.stdout.write(f'  ✓ Utilisateur créé: {user.username}')
                else:
                    self.stdout.write(f'  ℹ Utilisateur existant: {user.username}')
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'  ❌ Erreur création utilisateur: {e}'))
                return
            
            # Profil utilisateur
            try:
                profile, created = UserProfile.objects.get_or_create(
                    user=user,
                    defaults={'role': 'STAFF'}
                )
            except Exception as e:
                self.stdout.write(f'  ⚠️  Profil utilisateur non modifié: {e}')
            
            # Créer une catégorie de dépense
            category, created = ExpenseCategory.objects.get_or_create(
                name='Test Category',
            )
            if created:
                self.stdout.write('  ✓ Catégorie créée')
            
            # Créer un compte financier
            account, created = FinancialAccount.objects.get_or_create(
                account_number='TEST-001',
                defaults={
                    'name': 'Test Account',
                    'account_type': 'CASH'
                }
            )
            if created:
                self.stdout.write('  ✓ Compte créé')
            
            # Créer une dépense (génère un log CREATE)
            expense, created = Expense.objects.get_or_create(
                description='Test Expense',
                defaults={
                    'category': category,
                    'account': account,
                    'amount': Decimal('100.00'),
                    'created_by': user,
                }
            )
            if created:
                self.stdout.write(f'  ✓ Dépense créée: #{expense.id}')
            
            # Modifier la dépense (génère un log UPDATE)
            expense.amount = Decimal('150.00')
            expense.save()
            self.stdout.write(f'  ✓ Dépense modifiée: #{expense.id}')
            
            # Créer un client
            client, created = Client.objects.get_or_create(
                name='Test Client',
                defaults={
                    'client_type': 'RETAIL',
                    'phone': '123456789'
                }
            )
            if created:
                self.stdout.write('  ✓ Client créé')
            
            # Créer une facture
            invoice, created = Invoice.objects.get_or_create(
                number='INV-TEST-001',
                defaults={
                    'customer': client,
                    'created_by': user,
                    'issue_date': datetime.now(),
                    'total': Decimal('200.00'),
                }
            )
            if created:
                self.stdout.write(f'  ✓ Facture créée: {invoice.number}')
            
            # Créer un produit
            product, created = Product.objects.get_or_create(
                name='Test Product',
                defaults={
                    'sachets_per_pack': 10,
                    'default_sale_price': Decimal('50.00')
                }
            )
            if created:
                self.stdout.write('  ✓ Produit créé')
            
            # Créer un dépôt
            depot, created = Depot.objects.get_or_create(
                name='Test Depot',
                defaults={
                    'location': 'Test Location'
                }
            )
            if created:
                self.stdout.write('  ✓ Dépôt créé')
            
            # Créer un solde de stock
            balance, created = StockBalance.objects.get_or_create(
                product=product,
                depot=depot,
                defaults={'qty_packs': 100}
            )
            if created:
                self.stdout.write('  ✓ Balance de stock créée')
            
            # Modifier le stock (génère un log UPDATE)
            balance.qty_packs = 85
            balance.save()
            self.stdout.write('  ✓ Balance de stock modifiée')
        
        # Afficher les logs créés
        self.stdout.write(self.style.SUCCESS('\n📋 Logs d\'audit générés:'))
        logs = AuditLog.objects.order_by('-changed_at')[:10]
        
        for log in logs:
            action_colors = {
                'CREATE': self.style.SUCCESS,
                'UPDATE': self.style.WARNING,
                'DELETE': self.style.ERROR,
            }
            action_style = action_colors.get(log.action, lambda x: x)
            
            self.stdout.write(
                f"  {action_style(f'[{log.action}]')} "
                f"{log.content_type.model}#{log.object_id} "
                f"par {log.changed_by.username if log.changed_by else '(Système)'} "
                f"• {log.changed_at.strftime('%H:%M:%S')}"
            )
        
        self.stdout.write(self.style.SUCCESS(f'\n✓ {logs.count()} logs générés avec succès!'))
