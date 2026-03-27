# gestion/admin.py
# ══════════════════════════════════════════════════════════
#  SETRAM — Administration Django
#  - Import bulletins depuis Excel
#  - Affectation conducteurs aux bulletins
#  - Gestion complète de tous les modèles
# ══════════════════════════════════════════════════════════

from django import forms
from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin
from django.utils.html import format_html
from django.urls import path
from django.shortcuts import render, redirect
from django.http import HttpResponseRedirect
from django.utils import timezone

from .models import (
    Utilisateur, Rame, Bulletin, Course,
    Affectation, Permutation, Notification, HistoriqueModification
)
from .utils import importer_bulletins_excel, enregistrer_historique


# ══════════════════════════════════════════
#  FORMULAIRES
# ══════════════════════════════════════════

class ImportExcelForm(forms.Form):
    """Formulaire d'import du fichier Excel dans l'admin."""
    fichier = forms.FileField(
        label="Fichier Excel (.xlsx)",
        help_text="Fichier des bulletins de conduite SETRAM (JO + JS et JV)",
    )
    remplacer = forms.BooleanField(
        required=False,
        initial=False,
        label="Remplacer les bulletins existants",
        help_text="Si coché, supprime et recrée tous les bulletins. "
                  "Sinon, met à jour uniquement.",
    )


class AffectationRapideForm(forms.Form):
    """Formulaire pour affecter un conducteur à un bulletin depuis l'admin."""
    conducteur = forms.ModelChoiceField(
        queryset=Utilisateur.objects.filter(role='conducteur', is_active=True).order_by('nom'),
        label="Conducteur",
        empty_label="— Sélectionner un conducteur —",
    )
    date_service = forms.DateField(
        label="Date du service",
        widget=forms.DateInput(attrs={'type': 'date'}),
        initial=timezone.now().date,
    )


# ══════════════════════════════════════════
#  UTILISATEUR
# ══════════════════════════════════════════

@admin.register(Utilisateur)
class UtilisateurAdmin(UserAdmin):
    list_display   = ['matricule', 'nom', 'prenom', 'role_badge', 'telephone', 'is_active', 'date_creation']
    list_filter    = ['role', 'is_active']
    search_fields  = ['matricule', 'nom', 'prenom', 'telephone']
    ordering       = ['role', 'nom']
    list_per_page  = 25

    fieldsets = (
        (None,      {'fields': ('matricule', 'password')}),
        ('Infos',   {'fields': ('nom', 'prenom', 'role', 'telephone', 'fcm_token')}),
        ('Droits',  {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields':  ('matricule', 'password1', 'password2', 'nom', 'prenom', 'role', 'telephone'),
        }),
    )

    def role_badge(self, obj):
        colors = {
            'admin':       '#e74c3c',
            'ingenieur':   '#2ecc71',
            'superviseur': '#9b59b6',
            'pcc':         '#f39c12',
            'conducteur':  '#3498db',
        }
        color = colors.get(obj.role, '#95a5a6')
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;'
            'border-radius:4px;font-size:11px;font-weight:bold">{}</span>',
            color, obj.get_role_display()
        )
    role_badge.short_description = 'Rôle'


# ══════════════════════════════════════════
#  RAME
# ══════════════════════════════════════════

@admin.register(Rame)
class RameAdmin(admin.ModelAdmin):
    list_display  = ['numero', 'modele', 'etat_badge']
    list_filter   = ['etat']
    search_fields = ['numero', 'modele']
    ordering      = ['numero']

    def etat_badge(self, obj):
        colors = {
            'disponible':  '#2ecc71',
            'en_service':  '#3498db',
            'maintenance': '#e74c3c',
        }
        color = colors.get(obj.etat, '#95a5a6')
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;'
            'border-radius:4px;font-size:11px">{}</span>',
            color, obj.get_etat_display()
        )
    etat_badge.short_description = 'État'


# ══════════════════════════════════════════
#  COURSE (inline dans Bulletin)
# ══════════════════════════════════════════

class CourseInline(admin.TabularInline):
    model         = Course
    extra         = 0
    fields        = ['ordre', 'numero_course', 'origine', 'heure_depart_prev', 'destination', 'heure_arrivee_prev']
    ordering      = ['ordre']
    show_change_link = False
    can_delete    = True
    max_num       = 20


# ══════════════════════════════════════════
#  BULLETIN
# ══════════════════════════════════════════

@admin.register(Bulletin)
class BulletinAdmin(admin.ModelAdmin):
    list_display  = ['numero', 'type_jour', 'heure_debut', 'heure_fin',
                     'nb_courses', 'nb_affectations', 'importe_par', 'date_import']
    list_filter   = ['type_jour']
    search_fields = ['numero']
    ordering      = ['type_jour', 'numero']
    list_per_page = 25
    readonly_fields = ['date_import', 'importe_par', 'fichier_source']
    inlines       = [CourseInline]

    # ── Actions ──────────────────────────────────────────

    actions = ['affecter_conducteur_action']

    def affecter_conducteur_action(self, request, queryset):
        """Action admin : rediriger vers le formulaire d'affectation rapide."""
        ids = ','.join(str(b.id) for b in queryset)
        return HttpResponseRedirect(
            f'../affecter-conducteurs/?bulletins={ids}'
        )
    affecter_conducteur_action.short_description = "Affecter un conducteur à ces bulletins"

    # ── URLs personnalisées ───────────────────────────────

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path('importer-excel/',
                 self.admin_site.admin_view(self.view_importer_excel),
                 name='gestion_bulletin_importer_excel'),
            path('affecter-conducteurs/',
                 self.admin_site.admin_view(self.view_affecter_conducteurs),
                 name='gestion_bulletin_affecter_conducteurs'),
        ]
        return custom + urls

    # ── Vue import Excel ──────────────────────────────────

    def view_importer_excel(self, request):
        """
        Page admin : importer les bulletins depuis un fichier Excel.
        Accessible via le bouton "Importer Excel" dans la liste des bulletins.
        """
        if request.method == 'POST':
            form = ImportExcelForm(request.POST, request.FILES)
            if form.is_valid():
                fichier   = form.cleaned_data['fichier']
                remplacer = form.cleaned_data['remplacer']

                if remplacer:
                    nb_supp = Bulletin.objects.count()
                    Bulletin.objects.all().delete()
                    self.message_user(
                        request,
                        f"{nb_supp} bulletins supprimés avant réimport.",
                        level=messages.WARNING,
                    )

                rapport = importer_bulletins_excel(fichier, request.user)
                enregistrer_historique(
                    request.user, 'Import bulletins Excel', 'Bulletin', None,
                    {'fichier': fichier.name, **rapport}
                )

                if rapport['erreurs']:
                    for e in rapport['erreurs']:
                        self.message_user(request, f"Erreur : {e}", level=messages.ERROR)

                self.message_user(
                    request,
                    f"Import terminé : {rapport['crees']} créés, "
                    f"{rapport['mis_a_jour']} mis à jour, "
                    f"{rapport['vides']} vides (repos), "
                    f"{rapport['total']} avec courses.",
                    level=messages.SUCCESS,
                )
                return redirect('admin:gestion_bulletin_changelist')
        else:
            form = ImportExcelForm()

        context = {
            **self.admin_site.each_context(request),
            'title':      'Importer les bulletins depuis Excel',
            'form':       form,
            'opts':       self.model._meta,
        }
        return render(request, 'admin/gestion/bulletin/import_excel.html', context)

    # ── Vue affectation conducteurs ───────────────────────

    def view_affecter_conducteurs(self, request):
        """
        Page admin : affecter un ou plusieurs conducteurs à des bulletins.
        Accessible via l'action sur la liste des bulletins.
        """
        ids_str   = request.GET.get('bulletins', '') or request.POST.get('bulletins', '')
        ids       = [int(i) for i in ids_str.split(',') if i.strip().isdigit()]
        bulletins = Bulletin.objects.filter(id__in=ids).order_by('type_jour', 'numero')

        erreurs = []
        if request.method == 'POST':
            form = AffectationRapideForm(request.POST)
            if form.is_valid():
                conducteur   = form.cleaned_data['conducteur']
                date_service = form.cleaned_data['date_service']
                crees = 0
                for bulletin in bulletins:
                    # Vérifier conflit
                    if Affectation.objects.filter(
                        conducteur=conducteur, date_service=date_service
                    ).exclude(bulletin=bulletin).exists():
                        erreurs.append(
                            f"Conducteur déjà affecté pour le {date_service}."
                        )
                        break

                    aff, created = Affectation.objects.update_or_create(
                        conducteur=conducteur,
                        date_service=date_service,
                        defaults={
                            'bulletin':    bulletin,
                            'affecte_par': request.user,
                            'statut_service': 'en_attente',
                        }
                    )
                    if created:
                        crees += 1

                    enregistrer_historique(
                        request.user, 'Affectation conducteur (admin)',
                        'Affectation', aff.id,
                        {
                            'conducteur':  conducteur.matricule,
                            'bulletin':    bulletin.numero,
                            'date':        str(date_service),
                        }
                    )

                if not erreurs:
                    self.message_user(
                        request,
                        f"{conducteur.nom} {conducteur.prenom} affecté(e) à "
                        f"{len(bulletins)} bulletin(s) pour le {date_service}.",
                        level=messages.SUCCESS,
                    )
                    return redirect('admin:gestion_bulletin_changelist')
                else:
                    for e in erreurs:
                        self.message_user(request, e, level=messages.ERROR)
        else:
            form = AffectationRapideForm()

        context = {
            **self.admin_site.each_context(request),
            'title':      'Affecter un conducteur aux bulletins',
            'form':       form,
            'bulletins':  bulletins,
            'ids_str':    ids_str,
            'opts':       self.model._meta,
        }
        return render(request, 'admin/gestion/bulletin/affecter_conducteurs.html', context)

    # ── Colonnes calculées ────────────────────────────────

    def nb_courses(self, obj):
        return obj.courses.count()
    nb_courses.short_description = 'Courses'

    def nb_affectations(self, obj):
        return obj.affectations.count()
    nb_affectations.short_description = 'Affectations'

    # ── Bouton import dans la liste ───────────────────────

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['import_excel_url'] = 'importer-excel/'
        return super().changelist_view(request, extra_context=extra_context)


# ══════════════════════════════════════════
#  AFFECTATION
# ══════════════════════════════════════════

@admin.register(Affectation)
class AffectationAdmin(admin.ModelAdmin):
    list_display  = ['conducteur_nom', 'bulletin_num', 'date_service',
                     'statut_badge', 'rame', 'confirme', 'heure_confirmation']
    list_filter   = ['statut_service', 'confirme', 'date_service']
    search_fields = ['conducteur__nom', 'conducteur__matricule', 'bulletin__numero']
    ordering      = ['-date_service', 'conducteur__nom']
    date_hierarchy = 'date_service'
    list_per_page  = 30
    readonly_fields = ['date_affectation', 'heure_confirmation', 'affecte_par']

    raw_id_fields = ['conducteur', 'bulletin', 'rame', 'affecte_par']

    def conducteur_nom(self, obj):
        return f"{obj.conducteur.nom} {obj.conducteur.prenom} ({obj.conducteur.matricule})"
    conducteur_nom.short_description = 'Conducteur'

    def bulletin_num(self, obj):
        return f"Bulletin {obj.bulletin.numero} ({obj.bulletin.type_jour})"
    bulletin_num.short_description = 'Bulletin'

    def statut_badge(self, obj):
        colors = {
            'en_attente': '#f39c12',
            'confirme':   '#2ecc71',
            'absent':     '#e74c3c',
            'retard':     '#e67e22',
        }
        color = colors.get(obj.statut_service, '#95a5a6')
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;'
            'border-radius:4px;font-size:11px">{}</span>',
            color, obj.get_statut_service_display()
        )
    statut_badge.short_description = 'Statut'

    def save_model(self, request, obj, form, change):
        if not obj.affecte_par_id:
            obj.affecte_par = request.user
        super().save_model(request, obj, form, change)


# ══════════════════════════════════════════
#  PERMUTATION
# ══════════════════════════════════════════

@admin.register(Permutation)
class PermutationAdmin(admin.ModelAdmin):
    list_display  = ['demandeur', 'cible', 'date_service', 'statut_badge',
                     'cible_accepte', 'traite_par', 'date_demande']
    list_filter   = ['statut', 'cible_accepte']
    search_fields = ['demandeur__matricule', 'cible__matricule']
    ordering      = ['-date_demande']
    readonly_fields = ['date_demande', 'date_traitement']

    def statut_badge(self, obj):
        colors = {
            'en_attente': '#f39c12',
            'acceptee':   '#2ecc71',
            'refusee':    '#e74c3c',
        }
        color = colors.get(obj.statut, '#95a5a6')
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;'
            'border-radius:4px;font-size:11px">{}</span>',
            color, obj.get_statut_display()
        )
    statut_badge.short_description = 'Statut'


# ══════════════════════════════════════════
#  NOTIFICATION
# ══════════════════════════════════════════

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display  = ['destinataire', 'type_notif', 'titre', 'lu', 'date_envoi']
    list_filter   = ['type_notif', 'lu']
    search_fields = ['destinataire__matricule', 'titre']
    ordering      = ['-date_envoi']
    readonly_fields = ['date_envoi', 'date_lecture']


# ══════════════════════════════════════════
#  HISTORIQUE
# ══════════════════════════════════════════

@admin.register(HistoriqueModification)
class HistoriqueAdmin(admin.ModelAdmin):
    list_display  = ['date_action', 'utilisateur', 'action', 'table_ciblee', 'objet_id']
    list_filter   = ['action', 'table_ciblee']
    search_fields = ['utilisateur__matricule', 'action']
    ordering      = ['-date_action']
    readonly_fields = ['date_action', 'utilisateur', 'action', 'table_ciblee', 'objet_id', 'details']

    def has_add_permission(self, request):    return False
    def has_change_permission(self, request, obj=None): return False


# ══════════════════════════════════════════
#  TITRE ADMIN
# ══════════════════════════════════════════

admin.site.site_header = "SETRAM Constantine — Administration"
admin.site.site_title  = "SETRAM"
admin.site.index_title = "Tableau de bord administrateur"