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