from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin
from django.shortcuts import render, redirect
from django.urls import path
from django.utils.html import format_html
from .models import (
    Utilisateur, Rame, Bulletin, Course,
    Affectation, Permutation, Notification, HistoriqueModification
)
from .utils import importer_bulletins_excel


@admin.register(Utilisateur)
class UtilisateurAdmin(UserAdmin):
    list_display   = ['matricule', 'nom', 'prenom', 'role', 'is_active']
    list_filter    = ['role', 'is_active']
    search_fields  = ['matricule', 'nom', 'prenom']
    ordering       = ['role', 'nom']
    fieldsets = (
        (None, {'fields': ('matricule', 'password')}),
        ('Informations personnelles', {
            'fields': ('nom', 'prenom', 'role', 'telephone', 'fcm_token')
        }),
        ('Permissions', {
            'fields': ('is_active', 'is_staff', 'is_superuser')
        }),
    )
    add_fieldsets = (
        (None, {
            'fields': (
                'matricule', 'password1', 'password2',
                'nom', 'prenom', 'role'
            )
        }),
    )


class CourseInline(admin.TabularInline):
    model    = Course
    extra    = 0
    fields   = ['ordre', 'numero_course', 'origine', 'destination',
                'heure_depart_prev', 'heure_arrivee_prev']
    ordering = ['ordre']
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Bulletin)
class BulletinAdmin(admin.ModelAdmin):
    list_display    = ['numero', 'type_jour', 'heure_debut',
                       'heure_fin', 'date_import', 'importe_par',
                       'nb_courses']
    list_filter     = ['type_jour']
    search_fields   = ['numero']
    ordering        = ['type_jour', 'numero']
    readonly_fields = ['date_import', 'importe_par', 'fichier_source']
    inlines         = [CourseInline]

    def nb_courses(self, obj):
        n = obj.courses.count()
        return format_html('<span style="color:#417690;font-weight:bold;">{}</span>', n)
    nb_courses.short_description = 'Courses'

    def get_urls(self):
        urls = super().get_urls()
        extra = [
            path(
                'import-excel/',
                self.admin_site.admin_view(self.import_excel_view),
                name='gestion_bulletin_import_excel',
            ),
        ]
        return extra + urls

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['show_import_button'] = True
        return super().changelist_view(request, extra_context=extra_context)

    def import_excel_view(self, request):
        rapport = None
        if request.method == 'POST':
            fichier = request.FILES.get('fichier')
            if not fichier:
                messages.error(request, 'Aucun fichier sélectionné.')
            elif not fichier.name.endswith('.xlsx'):
                messages.error(request, 'Format invalide — fichier .xlsx requis.')
            else:
                try:
                    rapport = importer_bulletins_excel(fichier, request.user)
                    if rapport['erreurs']:
                        messages.warning(
                            request,
                            f"Import terminé avec {len(rapport['erreurs'])} erreur(s). "
                            f"{rapport['crees']} créé(s), {rapport['mis_a_jour']} mis à jour."
                        )
                    else:
                        messages.success(
                            request,
                            f"Import réussi : {rapport['crees']} bulletin(s) créé(s), "
                            f"{rapport['mis_a_jour']} mis à jour, "
                            f"{rapport['total']} traités au total."
                        )
                except Exception as e:
                    messages.error(request, f"Erreur lors de l'import : {str(e)}")

        context = {
            **self.admin_site.each_context(request),
            'rapport': rapport,
            'title': 'Importer des bulletins Excel',
            'opts': self.model._meta,
        }
        return render(request, 'admin/gestion/bulletin/import_excel.html', context)


@admin.register(Affectation)
class AffectationAdmin(admin.ModelAdmin):
    list_display    = ['conducteur', 'numero_service', 'type_jour',
                       'date_service', 'rame', 'confirme', 'statut_service']
    list_filter     = ['date_service', 'statut_service', 'confirme',
                       'bulletin__type_jour']
    search_fields   = ['conducteur__matricule', 'conducteur__nom',
                       'bulletin__numero']
    date_hierarchy  = 'date_service'
    ordering        = ['-date_service', 'bulletin__numero']
    readonly_fields = ['date_affectation', 'heure_confirmation']

    # Affiche le numéro de service dans la liste
    def numero_service(self, obj):
        return format_html(
            '<span style="background:#417690;color:white;padding:2px 8px;'
            'border-radius:4px;font-weight:bold;">Service {}</span>',
            obj.bulletin.numero
        )
    numero_service.short_description = 'N° Service'
    numero_service.admin_order_field = 'bulletin__numero'

    def type_jour(self, obj):
        couleur = '#27ae60' if obj.bulletin.type_jour == 'JO' else '#e67e22'
        return format_html(
            '<span style="color:{};font-weight:bold;">{}</span>',
            couleur, obj.bulletin.get_type_jour_display()
        )
    type_jour.short_description = 'Type jour'
    type_jour.admin_order_field = 'bulletin__type_jour'

    def get_urls(self):
        urls = super().get_urls()
        extra = [
            path(
                'affecter/',
                self.admin_site.admin_view(self.affecter_view),
                name='gestion_affectation_affecter',
            ),
        ]
        return extra + urls

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['show_affecter_button'] = True
        return super().changelist_view(request, extra_context=extra_context)

    def affecter_view(self, request):
        """
        Page d'affectation : choisir une date, un type de jour,
        puis affecter chaque conducteur à un numéro de service.
        """
        import datetime

        rapport   = None
        conducteurs = Utilisateur.objects.filter(
            role='conducteur', is_active=True
        ).order_by('nom', 'prenom')

        # Bulletins disponibles groupés par type
        bulletins_jo    = Bulletin.objects.filter(
            type_jour=Bulletin.JO
        ).order_by('numero')
        bulletins_jsjv  = Bulletin.objects.filter(
            type_jour=Bulletin.JS_JV
        ).order_by('numero')

        if request.method == 'POST':
            date_str  = request.POST.get('date_service')
            type_jour = request.POST.get('type_jour')

            if not date_str:
                messages.error(request, 'Veuillez choisir une date.')
            else:
                try:
                    date_service = datetime.date.fromisoformat(date_str)
                    nb_ok = 0
                    nb_skip = 0
                    erreurs = []

                    for conducteur in conducteurs:
                        bulletin_id = request.POST.get(f'bulletin_{conducteur.id}')
                        if not bulletin_id or bulletin_id == '':
                            nb_skip += 1
                            continue

                        try:
                            bulletin = Bulletin.objects.get(pk=bulletin_id)
                            Affectation.objects.update_or_create(
                                conducteur=conducteur,
                                date_service=date_service,
                                defaults={
                                    'bulletin':     bulletin,
                                    'affecte_par':  request.user,
                                    'statut_service': 'en_attente',
                                    'confirme':     False,
                                }
                            )
                            nb_ok += 1
                        except Exception as e:
                            erreurs.append(
                                f"{conducteur.nom} {conducteur.prenom} : {str(e)}"
                            )

                    rapport = {
                        'date': date_str,
                        'nb_ok': nb_ok,
                        'nb_skip': nb_skip,
                        'erreurs': erreurs,
                    }

                    if erreurs:
                        messages.warning(
                            request,
                            f"{nb_ok} affectation(s) enregistrée(s), "
                            f"{len(erreurs)} erreur(s)."
                        )
                    else:
                        messages.success(
                            request,
                            f"{nb_ok} affectation(s) enregistrée(s) pour le {date_str}."
                        )

                except ValueError:
                    messages.error(request, 'Date invalide.')

        context = {
            **self.admin_site.each_context(request),
            'title':          "Affecter les conducteurs aux services",
            'opts':           self.model._meta,
            'conducteurs':    conducteurs,
            'bulletins_jo':   bulletins_jo,
            'bulletins_jsjv': bulletins_jsjv,
            'rapport':        rapport,
            'today':          datetime.date.today().isoformat(),
        }
        return render(
            request,
            'admin/gestion/affectation/affecter.html',
            context
        )


@admin.register(Rame)
class RameAdmin(admin.ModelAdmin):
    list_display  = ['numero', 'modele', 'etat']
    list_filter   = ['etat']
    search_fields = ['numero']


@admin.register(Permutation)
class PermutationAdmin(admin.ModelAdmin):
    list_display    = ['demandeur', 'cible', 'date_service', 'statut', 'date_demande']
    list_filter     = ['statut']
    search_fields   = ['demandeur__matricule', 'cible__matricule']
    ordering        = ['-date_demande']
    readonly_fields = ['date_demande', 'date_traitement']


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display    = ['destinataire', 'type_notif', 'titre', 'lu', 'date_envoi']
    list_filter     = ['type_notif', 'lu']
    search_fields   = ['destinataire__matricule', 'titre']
    ordering        = ['-date_envoi']
    readonly_fields = ['date_envoi', 'date_lecture']


@admin.register(HistoriqueModification)
class HistoriqueAdmin(admin.ModelAdmin):
    list_display    = ['utilisateur', 'action', 'table_ciblee', 'date_action']
    list_filter     = ['table_ciblee']
    search_fields   = ['utilisateur__matricule', 'action']
    ordering        = ['-date_action']
    readonly_fields = ['utilisateur', 'action', 'table_ciblee',
                       'objet_id', 'details', 'date_action']

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
