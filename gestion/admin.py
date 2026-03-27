from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import (
    Utilisateur, Rame, Bulletin, Course,
    Affectation, Permutation, Notification, HistoriqueModification
)

@admin.register(Utilisateur)
class UtilisateurAdmin(UserAdmin):
    list_display  = ['matricule', 'nom', 'prenom', 'role', 'is_active']
    list_filter   = ['role', 'is_active']
    search_fields = ['matricule', 'nom', 'prenom']
    ordering      = ['role', 'nom']
    fieldsets     = (
        (None, {'fields': ('matricule', 'password')}),
        ('Infos', {'fields': ('nom', 'prenom', 'role', 'telephone', 'fcm_token')}),
        ('Droits', {'fields': ('is_active', 'is_staff', 'is_superuser')}),
    )
    add_fieldsets = (
        (None, {'fields': ('matricule', 'password1', 'password2', 'nom', 'prenom', 'role')}),
    )

admin.register(Rame)(admin.ModelAdmin)
admin.register(Bulletin)(admin.ModelAdmin)
admin.register(Affectation)(admin.ModelAdmin)
admin.register(Permutation)(admin.ModelAdmin)
admin.register(Notification)(admin.ModelAdmin)
admin.register(HistoriqueModification)(admin.ModelAdmin)