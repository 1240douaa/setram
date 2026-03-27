from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate
from django.utils import timezone
from django.db import transaction
import datetime

from .models import (
    Utilisateur, Bulletin, Course, Affectation,
    Rame, Permutation, Notification, HistoriqueModification
)
from .serializers import (
    LoginSerializer, UtilisateurSerializer, UtilisateurCreateSerializer,
    FCMTokenSerializer, BulletinListSerializer, BulletinDetailSerializer,
    AffectationSerializer, AffectationCreateSerializer, RameSerializer,
    PermutationSerializer, TraiterPermutationSerializer,
    NotificationSerializer, MonBulletinSerializer,
    SignalerAbsenceSerializer, HistoriqueSerializer
)
from .permissions import IsAdmin, IsIngenieur, IsSuperviseurOrIngenieur, IsPCC
from .utils import envoyer_notification, enregistrer_historique, importer_bulletins_excel


class AuthViewSet(viewsets.ViewSet):
    permission_classes = [permissions.AllowAny]

    @action(detail=False, methods=['post'])
    def login(self, request):
        s = LoginSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        user = authenticate(
            request,
            username=s.validated_data['matricule'],
            password=s.validated_data['mot_de_passe']
        )
        if not user:
            return Response({'detail': 'Matricule ou mot de passe incorrect.'}, status=401)
        refresh = RefreshToken.for_user(user)
        return Response({
            'access':      str(refresh.access_token),
            'refresh':     str(refresh),
            'utilisateur': UtilisateurSerializer(user).data,
        })

    @action(detail=False, methods=['post'])
    def refresh(self, request):
        try:
            refresh = RefreshToken(request.data.get('refresh'))
            return Response({'access': str(refresh.access_token)})
        except Exception:
            return Response({'detail': 'Token invalide.'}, status=401)

    @action(detail=False, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def logout(self, request):
        try:
            RefreshToken(request.data.get('refresh')).blacklist()
        except Exception:
            pass
        return Response({'detail': 'Déconnecté.'})

    @action(detail=False, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def update_fcm_token(self, request):
        """Flutter appelle cet endpoint au démarrage pour enregistrer son token FCM."""
        s = FCMTokenSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        request.user.fcm_token = s.validated_data['fcm_token']
        request.user.save(update_fields=['fcm_token'])
        return Response({'detail': 'Token FCM mis à jour.'})


class UtilisateurViewSet(viewsets.ModelViewSet):
    queryset           = Utilisateur.objects.all().order_by('role', 'nom')
    permission_classes = [permissions.IsAuthenticated, IsAdmin]

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return UtilisateurCreateSerializer
        return UtilisateurSerializer

    def perform_create(self, serializer):
        user = serializer.save()
        enregistrer_historique(self.request.user, 'Création compte',
                               'Utilisateur', user.id, {'matricule': user.matricule, 'role': user.role})

    def perform_destroy(self, instance):
        enregistrer_historique(self.request.user, 'Suppression compte',
                               'Utilisateur', instance.id, {'matricule': instance.matricule})
        instance.delete()

    @action(detail=True, methods=['patch'])
    def changer_role(self, request, pk=None):
        """Endpoint dédié modification de rôle — fiche 5.3."""
        user = self.get_object()
        nouveau_role = request.data.get('role')
        roles_valides = [r[0] for r in Utilisateur.ROLE_CHOICES]
        if nouveau_role not in roles_valides:
            return Response({'detail': 'Rôle invalide.'}, status=400)
        ancien_role = user.role
        user.role = nouveau_role
        user.save(update_fields=['role'])
        enregistrer_historique(request.user, 'Changement de rôle', 'Utilisateur', user.id,
                               {'ancien': ancien_role, 'nouveau': nouveau_role})
        return Response(UtilisateurSerializer(user).data)

    @action(detail=False, methods=['get'])
    def conducteurs(self, request):
        qs = Utilisateur.objects.filter(role=Utilisateur.CONDUCTEUR, is_active=True).order_by('nom')
        return Response(UtilisateurSerializer(qs, many=True).data)


class BulletinViewSet(viewsets.ModelViewSet):
    queryset = Bulletin.objects.all().order_by('type_jour', 'numero')

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [permissions.IsAuthenticated()]
        return [permissions.IsAuthenticated(), IsIngenieur()]

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return BulletinDetailSerializer
        return BulletinListSerializer

    @action(detail=False, methods=['post'])
    def importer(self, request):
        fichier = request.FILES.get('fichier')
        if not fichier:
            return Response({'detail': 'Aucun fichier fourni.'}, status=400)
        try:
            rapport = importer_bulletins_excel(fichier, request.user)
            enregistrer_historique(request.user, 'Import bulletins Excel', 'Bulletin', None,
                                   {'fichier': fichier.name, 'nb': rapport['total']})
            return Response(rapport, status=201)
        except Exception as e:
            return Response({'detail': f'Erreur import : {str(e)}'}, status=400)


class RameViewSet(viewsets.ModelViewSet):
    queryset         = Rame.objects.all().order_by('numero')
    serializer_class = RameSerializer

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [permissions.IsAuthenticated()]
        return [permissions.IsAuthenticated(), IsPCC()]

    def get_queryset(self):
        qs   = super().get_queryset()
        etat = self.request.query_params.get('etat')
        if etat:
            qs = qs.filter(etat=etat)
        return qs


class AffectationViewSet(viewsets.ModelViewSet):
    queryset = Affectation.objects.select_related('conducteur', 'bulletin', 'rame').all()

    def get_permissions(self):
        if self.action in ['confirmer', 'signaler_absence']:
            return [permissions.IsAuthenticated()]
        if self.action in ['list', 'retrieve']:
            return [permissions.IsAuthenticated()]
        return [permissions.IsAuthenticated(), IsPCC()]

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return AffectationCreateSerializer
        return AffectationSerializer

    def get_queryset(self):
        qs   = super().get_queryset()
        date = self.request.query_params.get('date')
        cid  = self.request.query_params.get('conducteur')
        if date:
            try:
                qs = qs.filter(date_service=datetime.date.fromisoformat(date))
            except ValueError:
                pass
        if cid:
            qs = qs.filter(conducteur_id=cid)
        return qs

    def perform_create(self, serializer):
        aff = serializer.save(affecte_par=self.request.user)
        envoyer_notification(
            aff.conducteur, Notification.AFFECTATION,
            'Nouveau bulletin affecté',
            f'Bulletin {aff.bulletin.numero} le {aff.date_service}.'
        )

    @action(detail=True, methods=['post'])
    def confirmer(self, request, pk=None):
        aff = self.get_object()
        if aff.conducteur != request.user:
            return Response({'detail': 'Non autorisé.'}, status=403)
        if aff.confirme:
            return Response({'detail': 'Déjà confirmé.'}, status=400)
        aff.confirme           = True
        aff.statut_service     = 'confirme'
        aff.heure_confirmation = timezone.now()
        aff.save()
        for sup in Utilisateur.objects.filter(role='superviseur', is_active=True):
            envoyer_notification(
                sup, Notification.PRISE_SERVICE,
                'Prise de service confirmée',
                f'{request.user.nom} {request.user.prenom} — Bulletin '
                f'{aff.bulletin.numero} à {aff.heure_confirmation.strftime("%H:%M")}.'
            )
        return Response({'detail': 'Confirmé.', 'heure': str(aff.heure_confirmation)})

    @action(detail=True, methods=['post'])
    def signaler_absence(self, request, pk=None):
        """✅ NOUVEAU — fiche 5.19 / exigence non-confirmation."""
        aff = self.get_object()
        # Le conducteur lui-même ou un superviseur peut signaler
        est_conducteur   = aff.conducteur == request.user
        est_superviseur  = request.user.role in ['superviseur', 'ingenieur', 'admin']
        if not (est_conducteur or est_superviseur):
            return Response({'detail': 'Non autorisé.'}, status=403)

        s = SignalerAbsenceSerializer(data=request.data)
        s.is_valid(raise_exception=True)

        aff.statut_service = s.validated_data['statut']
        aff.motif_absence  = s.validated_data.get('motif_absence', '')
        if s.validated_data['statut'] == 'retard':
            aff.heure_retard = timezone.now()
        aff.save()

        # Notifier superviseurs
        for sup in Utilisateur.objects.filter(role='superviseur', is_active=True):
            envoyer_notification(
                sup, Notification.ABSENCE,
                f'Conducteur {s.validated_data["statut"]}',
                f'{aff.conducteur.nom} {aff.conducteur.prenom} — '
                f'Bulletin {aff.bulletin.numero} le {aff.date_service}. '
                f'Motif : {aff.motif_absence or "non précisé"}'
            )
        enregistrer_historique(request.user, f'Signalement {aff.statut_service}',
                               'Affectation', aff.id,
                               {'conducteur': aff.conducteur.matricule})
        return Response(AffectationSerializer(aff).data)

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated, IsPCC])
    def affecter_rame(self, request, pk=None):
        aff    = self.get_object()
        rame_id = request.data.get('rame_id')
        if not rame_id:
            return Response({'detail': 'rame_id requis.'}, status=400)
        try:
            rame = Rame.objects.get(pk=rame_id, etat=Rame.DISPONIBLE)
        except Rame.DoesNotExist:
            return Response({'detail': 'Rame introuvable ou non disponible.'}, status=404)
        with transaction.atomic():
            if aff.rame:
                aff.rame.etat = Rame.DISPONIBLE
                aff.rame.save()
            rame.etat = Rame.EN_SERVICE
            rame.save()
            aff.rame = rame
            aff.save()
        envoyer_notification(
            aff.conducteur, Notification.AFFECTATION,
            'Rame affectée',
            f'Rame {rame.numero} pour le {aff.date_service}.'
        )
        return Response(AffectationSerializer(aff).data)


class PermutationViewSet(viewsets.ModelViewSet):
    queryset         = Permutation.objects.select_related('demandeur', 'cible', 'traite_par').all()
    serializer_class = PermutationSerializer

    def get_queryset(self):
        qs   = super().get_queryset()
        user = self.request.user
        if user.role == 'conducteur':
            qs = qs.filter(demandeur=user) | qs.filter(cible=user)
        statut = self.request.query_params.get('statut')
        if statut:
            qs = qs.filter(statut=statut)
        return qs.distinct()

    def perform_create(self, serializer):
        d = serializer.save(demandeur=self.request.user)
        envoyer_notification(
            d.cible, Notification.PERMUTATION,
            'Demande de permutation',
            f'{d.demandeur.nom} vous demande une permutation le {d.date_service}.'
        )
        for sup in Utilisateur.objects.filter(role='superviseur', is_active=True):
            envoyer_notification(
                sup, Notification.PERMUTATION,
                'Nouvelle demande de permutation',
                f'{d.demandeur.nom} ↔ {d.cible.nom} le {d.date_service}.'
            )

    @action(detail=True, methods=['post'])
    def repondre_cible(self, request, pk=None):
        p = self.get_object()
        if p.cible != request.user:
            return Response({'detail': 'Non autorisé.'}, status=403)
        decision = request.data.get('decision')
        if decision not in ['accepter', 'refuser']:
            return Response({'detail': 'decision invalide.'}, status=400)
        p.cible_accepte = (decision == 'accepter')
        p.save()
        envoyer_notification(
            p.demandeur, Notification.PERMUTATION,
            'Réponse à votre demande',
            f'{request.user.nom} a {"accepté" if p.cible_accepte else "refusé"} '
            f'votre demande du {p.date_service}.'
        )
        return Response(PermutationSerializer(p).data)

    @action(detail=True, methods=['post'],
            permission_classes=[permissions.IsAuthenticated, IsSuperviseurOrIngenieur])
    def traiter(self, request, pk=None):
        p = self.get_object()
        if p.statut != Permutation.EN_ATTENTE:
            return Response({'detail': 'Déjà traitée.'}, status=400)
        s = TraiterPermutationSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        decision = s.validated_data['decision']

        with transaction.atomic():
            p.statut          = Permutation.ACCEPTEE if decision == 'accepter' else Permutation.REFUSEE
            p.traite_par      = request.user
            p.motif_refus     = s.validated_data.get('motif_refus', '')
            p.date_traitement = timezone.now()
            p.save()

            if decision == 'accepter':
                ad = Affectation.objects.filter(conducteur=p.demandeur, date_service=p.date_service).first()
                ac = Affectation.objects.filter(conducteur=p.cible,     date_service=p.date_service).first()
                if ad and ac:
                    ad.bulletin, ac.bulletin = ac.bulletin, ad.bulletin
                    ad.save(); ac.save()

        msg = 'acceptée' if decision == 'accepter' else f'refusée ({p.motif_refus})'
        for c in [p.demandeur, p.cible]:
            envoyer_notification(c, Notification.PERMUTATION,
                                 'Décision permutation',
                                 f'Votre permutation du {p.date_service} a été {msg}.')
        enregistrer_historique(request.user, f'Permutation {decision}e',
                               'Permutation', p.id, {'decision': decision})
        return Response(PermutationSerializer(p).data)


class ConducteurViewSet(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=False, methods=['get'])
    def mon_bulletin(self, request):
        date_str = request.query_params.get('date', str(timezone.now().date()))
        try:
            date = datetime.date.fromisoformat(date_str)
        except ValueError:
            return Response({'detail': 'Format date invalide (YYYY-MM-DD).'}, status=400)
        aff = Affectation.objects.filter(
            conducteur=request.user, date_service=date
        ).select_related('bulletin', 'rame').first()
        if not aff:
            return Response({'detail': 'Aucun bulletin pour cette date.'}, status=404)
        return Response({
            'affectation_id':    aff.id,
            'date_service':      str(date),
            'statut_service':    aff.statut_service,
            'confirme':          aff.confirme,
            'heure_confirmation': str(aff.heure_confirmation) if aff.heure_confirmation else None,
            'rame':              aff.rame.numero if aff.rame else None,
            'bulletin':          MonBulletinSerializer(aff.bulletin).data,
        })

    @action(detail=False, methods=['get'])
    def mes_notifications(self, request):
        notifs = Notification.objects.filter(
            destinataire=request.user
        ).order_by('lu', '-date_envoi')[:50]
        return Response(NotificationSerializer(notifs, many=True).data)

    @action(detail=False, methods=['post'],
            url_path='notifications/(?P<notif_id>[^/.]+)/lire')
    def marquer_lu(self, request, notif_id=None):
        try:
            n = Notification.objects.get(pk=notif_id, destinataire=request.user)
            n.lu = True; n.date_lecture = timezone.now(); n.save()
            return Response({'detail': 'Lu.'})
        except Notification.DoesNotExist:
            return Response({'detail': 'Introuvable.'}, status=404)

    @action(detail=False, methods=['get'])
    def mes_permutations(self, request):
        qs = (Permutation.objects.filter(demandeur=request.user) |
              Permutation.objects.filter(cible=request.user))
        return Response(PermutationSerializer(qs.distinct().order_by('-date_demande'), many=True).data)


class SuperviseurViewSet(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated, IsSuperviseurOrIngenieur]

    @action(detail=False, methods=['get'])
    def conducteurs_en_service(self, request):
        date_str = request.query_params.get('date', str(timezone.now().date()))
        try:
            date = datetime.date.fromisoformat(date_str)
        except ValueError:
            return Response({'detail': 'Date invalide.'}, status=400)
        affs = Affectation.objects.filter(date_service=date).select_related(
            'conducteur', 'bulletin', 'rame'
        ).order_by('conducteur__nom')
        data = [{
            'conducteur':         UtilisateurSerializer(a.conducteur).data,
            'bulletin':           a.bulletin.numero,
            'heure_debut':        str(a.bulletin.heure_debut),
            'heure_fin':          str(a.bulletin.heure_fin),
            'rame':               a.rame.numero if a.rame else None,
            'statut_service':     a.statut_service,
            'confirme':           a.confirme,
            'heure_confirmation': str(a.heure_confirmation) if a.heure_confirmation else None,
        } for a in affs]
        return Response({'date': str(date), 'total': len(data), 'conducteurs': data})

    @action(detail=False, methods=['get'])
    def statistiques(self, request):
        from django.db.models import Count, Q
        cid = self.request.query_params.get('conducteur')
        qs  = Affectation.objects.all()
        if cid:
            qs = qs.filter(conducteur_id=cid)
        return Response(qs.aggregate(
            total=Count('id'),
            confirmes=Count('id', filter=Q(statut_service='confirme')),
            absents=Count('id',   filter=Q(statut_service='absent')),
            retards=Count('id',   filter=Q(statut_service='retard')),
        ))

    @action(detail=False, methods=['get'])
    def historique(self, request):
        qs  = HistoriqueModification.objects.all()
        cid = self.request.query_params.get('conducteur')
        if cid:
            qs = qs.filter(utilisateur_id=cid)
        return Response(HistoriqueSerializer(qs[:100], many=True).data)