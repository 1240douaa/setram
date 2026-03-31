from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin


class UtilisateurManager(BaseUserManager):
    def create_user(self, matricule, password=None, **extra_fields):
        if not matricule:
            raise ValueError("Le matricule est obligatoire")
        user = self.model(matricule=matricule, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, matricule, password=None, **extra_fields):
        extra_fields.setdefault('role', 'admin')
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(matricule, password, **extra_fields)


class Utilisateur(AbstractBaseUser, PermissionsMixin):
    ADMIN       = 'admin'
    INGENIEUR   = 'ingenieur'
    SUPERVISEUR = 'superviseur'
    PCC         = 'pcc'
    CONDUCTEUR  = 'conducteur'

    ROLE_CHOICES = [
        (ADMIN,       'Administrateur'),
        (INGENIEUR,   'Ingénieur de conception'),
        (SUPERVISEUR, 'Superviseur'),
        (PCC,         'PCC'),
        (CONDUCTEUR,  'Conducteur'),
    ]

    matricule     = models.CharField(max_length=20, unique=True)
    nom           = models.CharField(max_length=100)
    prenom        = models.CharField(max_length=100)
    role          = models.CharField(max_length=20, choices=ROLE_CHOICES, default=CONDUCTEUR)
    telephone     = models.CharField(max_length=20, blank=True)
    # ✅ AJOUT v2 : token Firebase pour push notifications Flutter
    fcm_token     = models.CharField(max_length=255, blank=True)
    is_active     = models.BooleanField(default=True)
    is_staff      = models.BooleanField(default=False)
    date_creation = models.DateTimeField(auto_now_add=True)

    objects = UtilisateurManager()

    USERNAME_FIELD  = 'matricule'
    REQUIRED_FIELDS = ['nom', 'prenom', 'role']

    def __str__(self):
        return f"{self.matricule} - {self.nom} {self.prenom} ({self.role})"

    class Meta:
        verbose_name = "Utilisateur"


class Rame(models.Model):
    DISPONIBLE  = 'disponible'
    EN_SERVICE  = 'en_service'
    MAINTENANCE = 'maintenance'

    ETAT_CHOICES = [
        (DISPONIBLE,  'Disponible'),
        (EN_SERVICE,  'En service'),
        (MAINTENANCE, 'En maintenance'),
    ]

    numero = models.CharField(max_length=20, unique=True)
    modele = models.CharField(max_length=100, blank=True)
    etat   = models.CharField(max_length=20, choices=ETAT_CHOICES, default=DISPONIBLE)
    notes  = models.TextField(blank=True)

    def __str__(self):
        return f"Rame {self.numero} ({self.etat})"


class Bulletin(models.Model):
    JO    = 'JO'
    JS_JV = 'JS_JV'
    TYPE_CHOICES = [(JO, 'Jour Ouvrable'), (JS_JV, 'Samedi/Vendredi')]

    numero         = models.IntegerField()
    type_jour      = models.CharField(max_length=10, choices=TYPE_CHOICES)
    heure_debut    = models.TimeField()
    heure_fin      = models.TimeField()
    date_import    = models.DateTimeField(auto_now_add=True)
    importe_par    = models.ForeignKey(
        Utilisateur, on_delete=models.SET_NULL, null=True,
        related_name='bulletins_importes'
    )
    fichier_source = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return f"Bulletin {self.numero} ({self.type_jour})"

    class Meta:
        unique_together = ('numero', 'type_jour')
        ordering = ['type_jour', 'numero']


class Course(models.Model):
    bulletin           = models.ForeignKey(Bulletin, on_delete=models.CASCADE, related_name='courses')
    numero_course      = models.CharField(max_length=20, blank=True)
    origine            = models.CharField(max_length=50)
    destination        = models.CharField(max_length=50)
    heure_depart_prev  = models.TimeField()
    heure_arrivee_prev = models.TimeField(null=True, blank=True)
    ordre              = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['ordre']


class Affectation(models.Model):
    conducteur         = models.ForeignKey(
        Utilisateur, on_delete=models.CASCADE,
        related_name='affectations',
        limit_choices_to={'role': 'conducteur'}
    )
    bulletin           = models.ForeignKey(Bulletin, on_delete=models.CASCADE, related_name='affectations')
    rame               = models.ForeignKey(Rame, on_delete=models.SET_NULL, null=True, blank=True)
    date_service       = models.DateField()
    affecte_par        = models.ForeignKey(
        Utilisateur, on_delete=models.SET_NULL, null=True,
        related_name='affectations_effectuees'
    )
    date_affectation   = models.DateTimeField(auto_now_add=True)
    confirme           = models.BooleanField(default=False)
    heure_confirmation = models.DateTimeField(null=True, blank=True)

    # ✅ AJOUT v2 : signalement explicite absence/retard
    STATUT_SERVICE_CHOICES = [
        ('en_attente',  'En attente'),
        ('confirme',    'Confirmé'),
        ('absent',      'Absent'),
        ('retard',      'En retard'),
    ]
    statut_service     = models.CharField(
        max_length=20, choices=STATUT_SERVICE_CHOICES, default='en_attente'
    )
    motif_absence      = models.TextField(blank=True)
    heure_retard       = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('conducteur', 'date_service')
        ordering = ['-date_service']


class Permutation(models.Model):
    EN_ATTENTE = 'en_attente'
    ACCEPTEE   = 'acceptee'
    REFUSEE    = 'refusee'

    STATUT_CHOICES = [
        (EN_ATTENTE, 'En attente'),
        (ACCEPTEE,   'Acceptée'),
        (REFUSEE,    'Refusée'),
    ]

    demandeur       = models.ForeignKey(
        Utilisateur, on_delete=models.CASCADE,
        related_name='permutations_demandees',
        limit_choices_to={'role': 'conducteur'}
    )
    cible           = models.ForeignKey(
        Utilisateur, on_delete=models.CASCADE,
        related_name='permutations_recues',
        limit_choices_to={'role': 'conducteur'}
    )
    date_service    = models.DateField()
    motif           = models.TextField()
    statut          = models.CharField(max_length=20, choices=STATUT_CHOICES, default=EN_ATTENTE)
    traite_par      = models.ForeignKey(
        Utilisateur, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='permutations_traitees'
    )
    motif_refus       = models.TextField(blank=True)
    cible_accepte     = models.BooleanField(null=True)
    bulletins_echanges = models.BooleanField(default=False)
    date_demande      = models.DateTimeField(auto_now_add=True)
    date_traitement   = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-date_demande']

    def appliquer_echange_bulletins(self):
        """Échange les bulletins des deux affectations liées à cette permutation."""
        if self.statut != self.ACCEPTEE or not self.cible_accepte or self.bulletins_echanges:
            return False

        ad = Affectation.objects.filter(
            conducteur=self.demandeur,
            date_service=self.date_service
        ).first()
        ac = Affectation.objects.filter(
            conducteur=self.cible,
            date_service=self.date_service
        ).first()

        if not ad or not ac:
            return False

        ad.bulletin, ac.bulletin = ac.bulletin, ad.bulletin
        ad.save()
        ac.save()

        self.bulletins_echanges = True
        self.save(update_fields=['bulletins_echanges'])
        return True


class Notification(models.Model):
    BULLETIN      = 'bulletin'
    PERMUTATION   = 'permutation'
    AFFECTATION   = 'affectation'
    PRISE_SERVICE = 'prise_service'
    ABSENCE       = 'absence'
    GENERAL       = 'general'

    TYPE_CHOICES = [
        (BULLETIN,      'Bulletin'),
        (PERMUTATION,   'Permutation'),
        (AFFECTATION,   'Affectation rame'),
        (PRISE_SERVICE, 'Prise de service'),
        (ABSENCE,       'Absence'),
        (GENERAL,       'Général'),
    ]

    destinataire = models.ForeignKey(Utilisateur, on_delete=models.CASCADE, related_name='notifications')
    type_notif   = models.CharField(max_length=20, choices=TYPE_CHOICES)
    titre        = models.CharField(max_length=200)
    message      = models.TextField()
    lu           = models.BooleanField(default=False)
    date_envoi   = models.DateTimeField(auto_now_add=True)
    date_lecture = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-date_envoi']


class HistoriqueModification(models.Model):
    utilisateur  = models.ForeignKey(Utilisateur, on_delete=models.SET_NULL, null=True)
    action       = models.CharField(max_length=200)
    table_ciblee = models.CharField(max_length=100)
    objet_id     = models.IntegerField(null=True)
    details      = models.JSONField(default=dict)
    date_action  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date_action']