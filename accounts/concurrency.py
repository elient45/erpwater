"""
Mixins pour les vues Django supportant concurrent updates et optimistic locking
"""
from django.core.exceptions import ValidationError
from django.http import HttpResponseConflict
from django.views.generic import UpdateView
from django.db import transaction


class OptimisticLockingMixin(UpdateView):
    """
    Mixin pour supporter optimistic locking sur les modèles avec version_number.
    
    Utilisation:
    - Le form doit inclure un champ caché 'version_number'
    - Le template doit passer la version actuelle
    """
    
    def form_valid(self, form):
        """Vérifie le version_number avant de sauvegarder"""
        
        # Récupérer la version du formulaire
        form_version = form.cleaned_data.get('version_number')
        
        if form_version is None:
            return super().form_valid(form)
        
        # Récupérer la version actuelle de la base de données
        with transaction.atomic():
            # Récupérer l'objet actuel pour vérifier la version
            db_version = self.object.__class__.objects.select_for_update().get(pk=self.object.pk).version_number
            
            if int(form_version) != int(db_version):
                # Conflit détecté - conflicting update
                self.object = form.instance
                return self.form_invalid(form)
        
        return super().form_valid(form)
    
    def form_invalid(self, form):
        """Gérer le conflit de version"""
        if 'version_number' in form.errors:
            # C'est un conflit de version
            response = HttpResponseConflict()
            response.content = b'Conflict: Object has been modified by another user'
            return response
        
        return super().form_invalid(form)


class ConcurrencyControlMixin:
    """
    Mixin pour ajouter des contrôles de concurrence sur les objets avec version_number.
    Peut être utilisé dans n'importe quelle vue.
    """
    
    @staticmethod
    def check_version(model, object_id, expected_version):
        """Vérifier si la version actuelle correspond à celle attendue"""
        try:
            obj = model.objects.get(pk=object_id)
            return obj.version_number == expected_version
        except model.DoesNotExist:
            return False
    
    @staticmethod
    def ensure_update(model, object_id, expected_version, update_data):
        """
        Effectuer une mise à jour sécurisée avec vérification de version.
        Lève une exception si le version_number ne correspond pas.
        """
        with transaction.atomic():
            # Acquérir un lock pessimiste
            obj = model.objects.select_for_update().get(pk=object_id)
            
            if obj.version_number != expected_version:
                raise ValidationError(
                    f'Conflict: Object version mismatch. '
                    f'Expected {expected_version}, but found {obj.version_number}. '
                    f'The object may have been modified by another user.'
                )
            
            # Mettre à jour
            for key, value in update_data.items():
                setattr(obj, key, value)
            
            # Le signal pre_save incrémentera automatiquement version_number
            obj.save()
            
            return obj
