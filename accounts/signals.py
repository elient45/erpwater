from decimal import Decimal
from datetime import date, datetime
from uuid import UUID
import json

from django.contrib.contenttypes.models import ContentType
from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from django.forms.models import model_to_dict
from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.db import connection
from django.core.serializers.json import DjangoJSONEncoder

from .models import AuditLog


def is_migration_running():
    """Vérifie si une migration est en cours d'exécution"""
    return 'migrate' in str(connection.cursor().db.settings_dict.get('NAME', '')).lower() or \
           any('migration' in str(frame.filename).lower() for frame in __import__('inspect').stack())


def get_client_ip(request):
    """Récupère l'adresse IP du client depuis la requête"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


def get_user_agent(request):
    """Récupère le User-Agent depuis la requête"""
    return request.META.get('HTTP_USER_AGENT', '')


def json_safe(value):
    """Convertit un’objet Python en représentation JSON-serializable."""
    if isinstance(value, dict):
        return {k: json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [json_safe(v) for v in value]
    if isinstance(value, tuple):
        return [json_safe(v) for v in value]
    if isinstance(value, Decimal):
        # Garder la précision et conserver un format JSON sûr
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    try:
        json.dumps(value, cls=DjangoJSONEncoder)
        return value
    except (TypeError, ValueError):
        return str(value)


# Signaux d'audit temporairement désactivés pour permettre les créations
# TODO: Réactiver après correction des problèmes de sérialisation JSON

# @receiver(pre_save)
# def audit_pre_save(sender, instance, **kwargs):
#     """Capture les valeurs avant modification pour audit"""
#     if sender.__name__ in ['AuditLog', 'Session', 'LogEntry'] or is_migration_running():
#         return  # Évite la récursion infinie et les conflits pendant migration

#     if hasattr(instance, '_audit_old_values'):
#         return  # Déjà capturé

#     # Stocke les valeurs actuelles en base pour comparaison
#     if instance.pk:
#         try:
#             old_instance = sender.objects.get(pk=instance.pk)
#             instance._audit_old_values = model_to_dict(old_instance)
#         except sender.DoesNotExist:
#             instance._audit_old_values = None
#     else:
#         instance._audit_old_values = None


# @receiver(post_save)
# def audit_post_save(sender, instance, created, **kwargs):
#     """Trace les créations et modifications"""
#     if sender.__name__ in ['AuditLog', 'Session', 'LogEntry'] or is_migration_running():
#         return

#     # Détermine l'action
#     action = AuditLog.ACTION_CREATE if created else AuditLog.ACTION_UPDATE

#     # Récupère les valeurs
#     new_values = json_safe(model_to_dict(instance))
#     old_values = json_safe(getattr(instance, '_audit_old_values', None))

#     # Si c'est une mise à jour sans changement, ignore
#     if not created and old_values == new_values:
#         return

#     # Récupère l'utilisateur depuis le contexte de thread local
#     from django.utils.deprecation import MiddlewareMixin
#     from threading import local
#     _audit_context = local()

#     changed_by = getattr(_audit_context, 'user', None)
#     request = getattr(_audit_context, 'request', None)

#     # Crée le log d'audit
#     AuditLog.objects.create(
#         content_type=ContentType.objects.get_for_model(sender),
#         object_id=instance.pk,
#         action=action,
#         old_values=old_values,
#         new_values=new_values if created else None,  # Pour création, stocke toutes les valeurs
#         changed_by=changed_by,
#         ip_address=get_client_ip(request) if request else None,
#         user_agent=get_user_agent(request) if request else "",
#     )


# @receiver(post_delete)
# def audit_post_delete(sender, instance, **kwargs):
#     """Trace les suppressions"""
#     if sender.__name__ in ['AuditLog', 'Session', 'LogEntry'] or is_migration_running():
#         return

#     # Récupère l'utilisateur depuis le contexte
#     from threading import local
#     _audit_context = local()

#     changed_by = getattr(_audit_context, 'user', None)
#     request = getattr(_audit_context, 'request', None)

#     # Crée le log d'audit
#     AuditLog.objects.create(
#         content_type=ContentType.objects.get_for_model(sender),
#         object_id=instance.pk,
#         action=AuditLog.ACTION_DELETE,
#         old_values=json_safe(model_to_dict(instance)),
#        changed_by=changed_by,
#         ip_address=get_client_ip(request) if request else None,
#         user_agent=get_user_agent(request) if request else "",
#     )


# @receiver(user_logged_in)
# def audit_user_login(sender, request, user, **kwargs):
#     """Trace les connexions utilisateur"""
#     AuditLog.objects.create(
#         content_type=ContentType.objects.get_for_model(user),
#         object_id=user.pk,
#         action=AuditLog.ACTION_LOGIN,
#         changed_by=user,
#         ip_address=get_client_ip(request),
#         user_agent=get_user_agent(request),
#     )


# @receiver(user_logged_out)
# def audit_user_logout(sender, request, user, **kwargs):
#     """Trace les déconnexions utilisateur"""
#     AuditLog.objects.create(
#         content_type=ContentType.objects.get_for_model(user),
#         object_id=user.pk,
#         action=AuditLog.ACTION_LOGOUT,
#         changed_by=user,
#         ip_address=get_client_ip(request),
#         user_agent=get_user_agent(request),
#     )


# # Middleware pour capturer le contexte utilisateur
# class AuditMiddleware:
#     """Middleware pour capturer l'utilisateur et la requête dans le contexte d'audit"""

#     def __init__(self, get_response):
#         self.get_response = get_response

#     def __call__(self, request):
#         # Stocke dans le contexte local
#         from threading import local
#         _audit_context = local()
#         _audit_context.user = getattr(request, 'user', None) if hasattr(request, 'user') and request.user.is_authenticated else None
#         _audit_context.request = request

#         response = self.get_response(request)
#         return response


# # Signaux pour optimistic locking - incrémenter version_number à chaque modification
# @receiver(pre_save)
# def increment_version_on_update(sender, instance, update_fields, **kwargs):
#     """Incrémenter automatiquement le version_number lors des mises à jour"""
    
#     # Modèles qui supportent optimistic locking
#     models_with_version = ['Invoice', 'Expense', 'StockBalance']
    
#     if sender.__name__ not in models_with_version or is_migration_running():
#         return
    
#     # Seulement si c'est une mise à jour (pas une création)
#     if instance.pk:
#         if update_fields and 'version_number' not in update_fields:
#             instance.version_number = (getattr(instance, 'version_number', 0) or 0) + 1
#         elif not update_fields:
#             # Si pas de update_fields spécifié, on incrémente aussi
#             instance.version_number = (getattr(instance, 'version_number', 0) or 0) + 1