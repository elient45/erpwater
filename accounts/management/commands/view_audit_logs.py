from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
import json

from accounts.models import AuditLog


class Command(BaseCommand):
    help = 'Affiche les logs d\'audit de manière lisible'

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit',
            type=int,
            default=50,
            help='Nombre de logs à afficher (défaut: 50)'
        )
        parser.add_argument(
            '--action',
            type=str,
            choices=['CREATE', 'UPDATE', 'DELETE', 'LOGIN', 'LOGOUT'],
            help='Filtrer par type d\'action'
        )
        parser.add_argument(
            '--user',
            type=str,
            help='Filtrer par utilisateur (username)'
        )
        parser.add_argument(
            '--model',
            type=str,
            help='Filtrer par modèle (ex: Invoice, Expense, Product)'
        )
        parser.add_argument(
            '--last-hours',
            type=int,
            help='Logs des X dernières heures'
        )
        parser.add_argument(
            '--object-id',
            type=int,
            help='Filtrer par objet ID'
        )
        parser.add_argument(
            '--json',
            action='store_true',
            help='Afficher en JSON'
        )

    def handle(self, *args, **options):
        queryset = AuditLog.objects.all()
        
        # Appliquer les filtres
        if options['action']:
            queryset = queryset.filter(action=options['action'])
        
        if options['user']:
            queryset = queryset.filter(changed_by__username__icontains=options['user'])
        
        if options['model']:
            queryset = queryset.filter(content_type__model__icontains=options['model'].lower())
        
        if options['object_id']:
            queryset = queryset.filter(object_id=options['object_id'])
        
        if options['last_hours']:
            since = timezone.now() - timedelta(hours=options['last_hours'])
            queryset = queryset.filter(changed_at__gte=since)
        
        # Limiter et ordonner
        queryset = queryset.order_by('-changed_at')[:options['limit']]
        
        if not queryset.exists():
            self.stdout.write(self.style.WARNING('❌ Aucun log d\'audit trouvé'))
            return
        
        # Affichage JSON
        if options['json']:
            logs_data = []
            for log in queryset:
                logs_data.append({
                    'id': log.id,
                    'action': log.action,
                    'model': log.content_type.model,
                    'object_id': log.object_id,
                    'user': log.changed_by.username if log.changed_by else 'Système',
                    'timestamp': log.changed_at.isoformat(),
                    'ip_address': log.ip_address,
                    'old_values': log.old_values,
                    'new_values': log.new_values,
                })
            self.stdout.write(json.dumps(logs_data, indent=2, ensure_ascii=False, default=str))
            return
        
        # Affichage lisible
        self.stdout.write(self.style.SUCCESS(f'\n📋 Logs d\'audit ({queryset.count()} entrées):'))
        self.stdout.write('─' * 120)
        
        for log in queryset:
            # En-tête
            action_colors = {
                'CREATE': self.style.SUCCESS,
                'UPDATE': self.style.WARNING,
                'DELETE': self.style.ERROR,
                'LOGIN': self.style.SUCCESS,
                'LOGOUT': self.style.WARNING,
            }
            action_style = action_colors.get(log.action, lambda x: x)
            
            self.stdout.write(
                f"\n🔹 {action_style(f'[{log.action}]')} "
                f"{log.content_type.model}#{log.object_id} "
                f"par {log.changed_by.username if log.changed_by else '(Système)'} "
                f"• {log.changed_at.strftime('%Y-%m-%d %H:%M:%S')}"
            )
            
            # Adresse IP
            if log.ip_address:
                self.stdout.write(f"   📍 IP: {log.ip_address}")
            
            # Raison si présente
            if log.reason:
                self.stdout.write(f"   📝 Raison: {log.reason}")
            
            # Anciennes valeurs
            if log.old_values and log.action == 'UPDATE':
                self.stdout.write(f"   ❌ Avant: {json.dumps(log.old_values, indent=6, ensure_ascii=False)}")
            
            # Nouvelles valeurs
            if log.new_values:
                self.stdout.write(f"   ✅ Après: {json.dumps(log.new_values, indent=6, ensure_ascii=False)}")
        
        self.stdout.write('\n' + '─' * 120)
        self.stdout.write(self.style.SUCCESS(f'✓ Total: {queryset.count()} logs affichés'))
