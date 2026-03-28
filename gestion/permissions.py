from rest_framework.permissions import BasePermission


class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'admin'


class IsIngenieur(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in ['ingenieur', 'admin']


class IsSuperviseurOrIngenieur(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in [
            'superviseur', 'ingenieur', 'admin'
        ]


class IsPCC(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in ['pcc', 'admin']


# ✅ AJOUT — manquait dans la version originale
class IsConducteur(BasePermission):
    """Réservé aux conducteurs (et admins)."""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in ['conducteur', 'admin']


class IsOwnerOrSuperviseur(BasePermission):
    """
    Utilisé sur les objets Affectation :
    - Le conducteur concerné peut accéder à sa propre affectation.
    - Un superviseur/ingénieur/admin peut tout voir.
    """
    def has_object_permission(self, request, view, obj):
        if request.user.role in ['superviseur', 'ingenieur', 'admin']:
            return True
        # obj est une Affectation
        return hasattr(obj, 'conducteur') and obj.conducteur == request.user