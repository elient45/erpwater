from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from django.db import models


class UserProfile(models.Model):
    ROLE_ADMIN = "ADMIN"
    ROLE_STAFF = "STAFF"

    ROLE_CHOICES = [
        (ROLE_ADMIN, "Administrateur"),
        (ROLE_STAFF, "Personnel"),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    phone = models.CharField(max_length=30, blank=True, null=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_STAFF)

    class Meta:
        db_table = "user_profiles"

    def __str__(self):
        return f"{self.user.username} - {self.role}"


class AuditLog(models.Model):
    """Trace complète de chaque changement métier pour audit et sécurité"""

    ACTION_CREATE = "CREATE"
    ACTION_UPDATE = "UPDATE"
    ACTION_DELETE = "DELETE"
    ACTION_LOGIN = "LOGIN"
    ACTION_LOGOUT = "LOGOUT"

    ACTION_CHOICES = [
        (ACTION_CREATE, "Création"),
        (ACTION_UPDATE, "Modification"),
        (ACTION_DELETE, "Suppression"),
        (ACTION_LOGIN, "Connexion"),
        (ACTION_LOGOUT, "Déconnexion"),
    ]

    # Référence générique vers n'importe quel modèle
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        verbose_name="Type d'objet"
    )
    object_id = models.PositiveBigIntegerField(verbose_name="ID de l'objet")
    content_object = GenericForeignKey('content_type', 'object_id')

    # Détails du changement
    action = models.CharField(
        max_length=20,
        choices=ACTION_CHOICES,
        verbose_name="Action"
    )
    old_values = models.JSONField(
        blank=True,
        null=True,
        verbose_name="Valeurs anciennes"
    )
    new_values = models.JSONField(
        blank=True,
        null=True,
        verbose_name="Valeurs nouvelles"
    )

    # Métadonnées
    reason = models.TextField(
        blank=True,
        verbose_name="Raison du changement"
    )
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
        verbose_name="Modifié par"
    )
    changed_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Date du changement"
    )

    # Informations supplémentaires
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        verbose_name="Adresse IP"
    )
    user_agent = models.TextField(
        blank=True,
        null=True,
        verbose_name="Navigateur"
    )

    class Meta:
        db_table = "audit_logs"
        ordering = ["-changed_at"]
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['changed_by', '-changed_at']),
            models.Index(fields=['action', '-changed_at']),
        ]
        verbose_name = "Log d'audit"
        verbose_name_plural = "Logs d'audit"

    def __str__(self):
        return f"{self.action} {self.content_type}#{self.object_id} par {self.changed_by} le {self.changed_at}"