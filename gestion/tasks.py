from celery import shared_task
from django.utils import timezone
from .models import Affectation, Utilisateur, Notification
from .utils import envoyer_notification
import datetime


@shared_task
def verifier_prises_de_service():
    """
    Tâche planifiée toutes les 30 minutes.
    Si un conducteur n'a pas confirmé sa prise de service
    30 minutes après l'heure de début, on notifie les superviseurs.
    """
    maintenant  = timezone.now()
    aujourd_hui = maintenant.date()
    seuil       = maintenant - datetime.timedelta(minutes=30)

    affectations_en_attente = Affectation.objects.filter(
        date_service=aujourd_hui,
        confirme=False,
        statut_service='en_attente',
    ).select_related('conducteur', 'bulletin')

    for aff in affectations_en_attente:
        # Convertir heure_debut en datetime pour comparer
        heure_debut_dt = timezone.make_aware(
            datetime.datetime.combine(aujourd_hui, aff.bulletin.heure_debut)
        )
        if heure_debut_dt <= seuil:
            # Marquer comme absent automatiquement
            aff.statut_service = 'absent'
            aff.save()

            # Notifier tous les superviseurs
            superviseurs = Utilisateur.objects.filter(
                role=Utilisateur.SUPERVISEUR, is_active=True
            )
            for sup in superviseurs:
                envoyer_notification(
                    destinataire=sup,
                    type_notif=Notification.ABSENCE,
                    titre='Absence non confirmée',
                    message=(
                        f"{aff.conducteur.nom} {aff.conducteur.prenom} "
                        f"(Bulletin {aff.bulletin.numero}) n'a pas confirmé "
                        f"sa prise de service prévue à "
                        f"{aff.bulletin.heure_debut.strftime('%H:%M')}."
                    )
                )