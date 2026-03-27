from rest_framework import serializers
from django.utils import timezone
from .models import (
    Utilisateur, Bulletin, Course, Affectation,
    Rame, Permutation, Notification, HistoriqueModification
)




class LoginSerializer(serializers.Serializer):
    matricule = serializers.CharField()
    mot_de_passe = serializers.CharField()

class UtilisateurSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Utilisateur
        fields = ['id', 'matricule', 'nom', 'prenom', 'role', 'telephone', 'is_active']


class UtilisateurCreateSerializer(serializers.ModelSerializer):
    mot_de_passe = serializers.CharField(write_only=True)

    class Meta:
        model  = Utilisateur
        fields = ['matricule', 'nom', 'prenom', 'role', 'telephone', 'mot_de_passe']

    def create(self, validated_data):
        pwd  = validated_data.pop('mot_de_passe')
        user = Utilisateur(**validated_data)
        user.set_password(pwd)
        user.save()
        return user


class FCMTokenSerializer(serializers.Serializer):
    fcm_token = serializers.CharField()


class RameSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Rame
        fields = ['id', 'numero', 'modele', 'etat', 'notes']


class CourseSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Course
        fields = ['id', 'numero_course', 'origine', 'destination',
                  'heure_depart_prev', 'heure_arrivee_prev', 'ordre']


class BulletinListSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Bulletin
        fields = ['id', 'numero', 'type_jour', 'heure_debut', 'heure_fin', 'date_import']


class BulletinDetailSerializer(serializers.ModelSerializer):
    courses     = CourseSerializer(many=True, read_only=True)
    importe_par = serializers.StringRelatedField()

    class Meta:
        model  = Bulletin
        fields = ['id', 'numero', 'type_jour', 'heure_debut', 'heure_fin',
                  'date_import', 'importe_par', 'fichier_source', 'courses']


class AffectationSerializer(serializers.ModelSerializer):
    conducteur_nom = serializers.SerializerMethodField()
    bulletin_info  = BulletinListSerializer(source='bulletin', read_only=True)
    rame_numero    = serializers.SerializerMethodField()

    class Meta:
        model  = Affectation
        fields = ['id', 'conducteur', 'conducteur_nom', 'bulletin', 'bulletin_info',
                  'rame', 'rame_numero', 'date_service', 'confirme',
                  'heure_confirmation', 'statut_service', 'motif_absence']
        read_only_fields = ['date_affectation', 'heure_confirmation']

    def get_conducteur_nom(self, obj):
        return f"{obj.conducteur.nom} {obj.conducteur.prenom}"

    def get_rame_numero(self, obj):
        return obj.rame.numero if obj.rame else None


class AffectationCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Affectation
        fields = ['conducteur', 'bulletin', 'rame', 'date_service']

    def validate(self, data):
        qs = Affectation.objects.filter(
            conducteur=data['conducteur'], date_service=data['date_service']
        )
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                "Ce conducteur a déjà un bulletin pour ce jour."
            )
        return data


class PermutationSerializer(serializers.ModelSerializer):
    demandeur_nom  = serializers.SerializerMethodField()
    cible_nom      = serializers.SerializerMethodField()
    traite_par_nom = serializers.SerializerMethodField()

    class Meta:
        model  = Permutation
        fields = ['id', 'demandeur', 'demandeur_nom', 'cible', 'cible_nom',
                  'date_service', 'motif', 'statut', 'traite_par', 'traite_par_nom',
                  'motif_refus', 'cible_accepte', 'date_demande', 'date_traitement']
        read_only_fields = ['statut', 'traite_par', 'date_demande', 'date_traitement']

    def get_demandeur_nom(self, obj):
        return f"{obj.demandeur.nom} {obj.demandeur.prenom}"

    def get_cible_nom(self, obj):
        return f"{obj.cible.nom} {obj.cible.prenom}"

    def get_traite_par_nom(self, obj):
        return f"{obj.traite_par.nom} {obj.traite_par.prenom}" if obj.traite_par else None


class TraiterPermutationSerializer(serializers.Serializer):
    decision    = serializers.ChoiceField(choices=['accepter', 'refuser'])
    motif_refus = serializers.CharField(required=False, allow_blank=True)


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Notification
        fields = ['id', 'type_notif', 'titre', 'message', 'lu', 'date_envoi', 'date_lecture']


class MonBulletinSerializer(serializers.ModelSerializer):
    courses = CourseSerializer(many=True, read_only=True)

    class Meta:
        model  = Bulletin
        fields = ['id', 'numero', 'type_jour', 'heure_debut', 'heure_fin', 'courses']


class SignalerAbsenceSerializer(serializers.Serializer):
    statut       = serializers.ChoiceField(choices=['absent', 'retard'])
    motif_absence = serializers.CharField(required=False, allow_blank=True)


class HistoriqueSerializer(serializers.ModelSerializer):
    utilisateur_nom = serializers.SerializerMethodField()

    class Meta:
        model  = HistoriqueModification
        fields = ['id', 'utilisateur', 'utilisateur_nom', 'action',
                  'table_ciblee', 'objet_id', 'details', 'date_action']

    def get_utilisateur_nom(self, obj):
        if obj.utilisateur:
            return f"{obj.utilisateur.nom} {obj.utilisateur.prenom}"
        return "Système"