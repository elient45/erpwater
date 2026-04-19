from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User

from .models import UserProfile, AuditLog


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name_plural = "Profil"


class CustomUserAdmin(UserAdmin):
    inlines = (UserProfileInline,)
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_staff', 'get_role')
    list_filter = ('is_staff', 'is_superuser', 'is_active', 'groups', 'profile__role')

    def get_role(self, obj):
        return obj.profile.role if hasattr(obj, 'profile') else '-'
    get_role.short_description = 'Rôle'


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "phone")
    list_filter = ("role",)
    search_fields = ("user__username", "user__first_name", "user__last_name")


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('id', 'action', 'content_type', 'object_id', 'changed_by', 'changed_at', 'ip_address')
    list_filter = ('action', 'content_type', 'changed_at', 'changed_by')
    search_fields = ('object_id', 'changed_by__username', 'ip_address')
    readonly_fields = ('content_type', 'object_id', 'action', 'old_values', 'new_values', 
                      'changed_by', 'changed_at', 'ip_address', 'user_agent', 'reason')
    date_hierarchy = 'changed_at'
    ordering = ['-changed_at']
    
    def has_add_permission(self, request):
        # Les logs d'audit ne peuvent pas être créés manuellement
        return False
    
    def has_delete_permission(self, request, obj=None):
        # Les logs d'audit ne peuvent pas être supprimés (traçabilité)
        return False


# Réenregistrer User avec notre admin personnalisé
admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)