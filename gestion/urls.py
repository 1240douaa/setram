from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    AuthViewSet, UtilisateurViewSet, BulletinViewSet,
    RameViewSet, AffectationViewSet, PermutationViewSet,
    ConducteurViewSet, SuperviseurViewSet
)

router = DefaultRouter()
router.register(r'auth',         AuthViewSet,         basename='auth')
router.register(r'utilisateurs', UtilisateurViewSet,  basename='utilisateur')
router.register(r'bulletins',    BulletinViewSet,     basename='bulletin')
router.register(r'rames',        RameViewSet,         basename='rame')
router.register(r'affectations', AffectationViewSet,  basename='affectation')
router.register(r'permutations', PermutationViewSet,  basename='permutation')
router.register(r'conducteur',   ConducteurViewSet,   basename='conducteur')
router.register(r'superviseur',  SuperviseurViewSet,  basename='superviseur')

urlpatterns = [
    path('api/v1/', include(router.urls)),
]