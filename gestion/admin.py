# gestion/admin.py
from django import forms
from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin
from django.utils.html import format_html
from django.urls import path
from django.shortcuts import render, redirect
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
    fichier = forms.FileField(
        label="Fichier Excel (.xlsx)",
        help_text="Fichiers JO + JS et JV — structure SETRAM",
    )
    remplacer = forms.BooleanField(
        required=False, initial=False,
        label="Remplacer tous les bulletins existants",
    )


class AffectationRapideForm(forms.Form):
    conducteur = forms.ModelChoiceField(
        queryset=Utilisateur.objects.filter(role='conducteur', is_active=True).order_by('nom'),
        label="Conducteur",
        empty_label="— Sélectionner —",
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
    list_display  = ['matricule', 'nom', 'prenom', 'role_badge', 'telephone', 'is_active']
    list_filter   = ['role', 'is_active']
    search_fields = ['matricule', 'nom', 'prenom']
    ordering      = ['role', 'nom']

    fieldsets = (
        (None,     {'fields': ('matricule', 'password')}),
        ('Infos',  {'fields': ('nom', 'prenom', 'role', 'telephone', 'fcm_token')}),
        ('Droits', {'fields': ('is_active', 'is_staff', 'is_superuser')}),
    )
    add_fieldsets = (
        (None, {'classes': ('wide',),
                'fields': ('matricule', 'password1', 'password2', 'nom', 'prenom', 'role')}),
    )

    def role_badge(self, obj):
        colors = {
            'admin': '#c0392b', 'ingenieur': '#27ae60',
            'superviseur': '#8e44ad', 'pcc': '#e67e22', 'conducteur': '#2980b9',
        }
        c = colors.get(obj.role, '#7f8c8d')
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;'
            'border-radius:3px;font-size:11px;font-weight:bold">{}</span>',
            c, obj.get_role_display()
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

    def etat_badge(self, obj):
        colors = {'disponible': '#27ae60', 'en_service': '#2980b9', 'maintenance': '#c0392b'}
        c = colors.get(obj.etat, '#7f8c8d')
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;'
            'border-radius:3px;font-size:11px">{}</span>',
            c, obj.get_etat_display()
        )
    etat_badge.short_description = 'État'


# ══════════════════════════════════════════
#  BULLETIN — inline courses
# ══════════════════════════════════════════

class CourseInline(admin.TabularInline):
    model  = Course
    extra  = 0
    fields = ['ordre', 'numero_course', 'origine', 'heure_depart_prev',
              'destination', 'heure_arrivee_prev']
    ordering = ['ordre']


@admin.register(Bulletin)
class BulletinAdmin(admin.ModelAdmin):
    list_display  = ['numero', 'type_jour_badge', 'heure_debut', 'heure_fin',
                     'nb_courses', 'nb_affectations', 'date_import']
    list_filter   = ['type_jour']
    search_fields = ['numero']
    ordering      = ['type_jour', 'numero']
    list_per_page = 25
    readonly_fields = ['date_import', 'importe_par', 'fichier_source', 'apercu_bulletin']
    inlines       = [CourseInline]
    actions       = ['affecter_conducteur_action']

    # ── Champ aperçu dans le formulaire de détail ─────────

    def apercu_bulletin(self, obj):
        """Affiche le bulletin style Excel dans la page de détail admin."""
        return self._render_bulletin_html(obj)
    apercu_bulletin.short_description = 'Aperçu bulletin (style Excel)'
    apercu_bulletin.allow_tags = True

    def _render_bulletin_html(self, bulletin):
        """Génère le HTML du bulletin style Excel."""
        courses = list(bulletin.courses.order_by('ordre'))
        type_label = 'n-service' if bulletin.type_jour == Bulletin.JS_JV else 'n-service'

        # En-tête
        html = f'''
        <div style="font-family:Arial,sans-serif;display:inline-block;
                    border:2px solid #555;min-width:560px;margin:8px 0">

          <!-- Ligne titre service -->
          <div style="display:flex;align-items:stretch">
            <div style="background:#ff0000;flex:1;display:flex;
                        align-items:center;justify-content:center;
                        padding:6px 16px;min-height:70px">
              <span style="color:#fff;font-size:38px;font-weight:900;
                           letter-spacing:2px">
                service {bulletin.numero:02d}
              </span>
            </div>
            <div style="display:flex;flex-direction:column;min-width:130px">
              <div style="background:#ffd700;display:flex;align-items:center;
                          justify-content:space-between;padding:4px 10px;flex:1;
                          border-left:2px solid #555">
                <span style="font-size:22px;font-weight:bold;color:#000">
                  {bulletin.numero:02d}
                </span>
                <span style="font-size:16px;font-weight:bold;color:#000">
                  {str(bulletin.heure_debut)[:5] if bulletin.heure_debut else '--:--'}
                </span>
              </div>
              <div style="background:#00b0a0;display:flex;align-items:center;
                          justify-content:space-between;padding:4px 10px;flex:1;
                          border-left:2px solid #555;border-top:1px solid #555">
                <span style="font-size:13px;font-weight:bold;color:#fff">
                  {type_label}
                </span>
                <span style="font-size:16px;font-weight:bold;color:#fff">
                  {str(bulletin.heure_fin)[:5] if bulletin.heure_fin else '--:--'}
                </span>
              </div>
            </div>
          </div>

          <!-- Bande "Heures réelles" -->
          <div style="background:#00b0a0;padding:4px 10px;
                      border-top:1px solid #555">
            <span style="color:#fff;font-size:12px;font-weight:bold">
              Heures réelles de départ et d'arrivée
            </span>
          </div>

          <!-- En-têtes colonnes -->
          <div style="display:grid;
                      grid-template-columns:70px 80px 90px 100px 70px 100px 100px;
                      background:#fff;border-top:1px solid #555">
        '''

        headers = ['Course', 'Numéro de rame', 'Origine et voie',
                   'Heure prévue de départ', 'Retard Oui', 'Destination et voie',
                   'Heure d\'arrivée prévue']

        for h in headers:
            html += f'''
            <div style="background:#00b0a0;color:#fff;padding:5px 4px;
                        font-size:10px;font-weight:bold;text-align:center;
                        border-right:1px solid #555;border-bottom:1px solid #555;
                        display:flex;align-items:center;justify-content:center">
              {h}
            </div>'''

        html += '</div>'

        # Lignes de courses
        if not courses:
            html += '''
            <div style="padding:16px;text-align:center;color:#999;
                        font-style:italic;border-top:1px solid #eee">
              Aucune course — bulletin vide (repos)
            </div>'''
        else:
            # Grouper les courses par numero_course pour affichage fusionné
            prev_course_num = None
            for i, c in enumerate(courses):
                bg_row = '#f9f9f9' if i % 2 == 0 else '#fff'

                # Couleur origine (rouge si ZOU1, comme dans l'image)
                stations_rouges = ['ZOU1', 'ZOU2']
                bg_orig = '#ff4444' if c.origine in stations_rouges else '#fff'
                color_orig = '#fff' if c.origine in stations_rouges else '#000'

                # Couleur heure (rouge si c'est la dernière course)
                is_last = (i == len(courses) - 1)
                bg_heure = '#ff4444' if is_last else '#fff'
                color_heure = '#fff' if is_last else '#000'

                # Afficher le numéro de course seulement si différent du précédent
                course_display = c.numero_course if c.numero_course != prev_course_num else ''
                if c.numero_course:
                    prev_course_num = c.numero_course

                heure_dep = str(c.heure_depart_prev)[:5] if c.heure_depart_prev else ''
                heure_arr = str(c.heure_arrivee_prev)[:5] if c.heure_arrivee_prev else ''

                html += f'''
                <div style="display:grid;
                            grid-template-columns:70px 80px 90px 100px 70px 100px 100px;
                            background:{bg_row};border-top:1px solid #ddd">
                  <div style="padding:5px 6px;font-size:12px;font-weight:bold;
                              color:#000;border-right:1px solid #ddd;
                              background:{'#ffd700' if course_display else bg_row}">
                    {course_display}
                  </div>
                  <div style="padding:5px 6px;font-size:12px;
                              border-right:1px solid #ddd;text-align:center"></div>
                  <div style="padding:5px 6px;font-size:12px;font-weight:bold;
                              background:{bg_orig};color:{color_orig};
                              border-right:1px solid #ddd;text-align:center">
                    {c.origine}
                  </div>
                  <div style="padding:5px 6px;font-size:12px;font-weight:bold;
                              background:{bg_heure};color:{color_heure};
                              border-right:1px solid #ddd;text-align:center">
                    {heure_dep}
                  </div>
                  <div style="padding:5px 6px;border-right:1px solid #ddd"></div>
                  <div style="padding:5px 6px;font-size:12px;font-weight:bold;
                              border-right:1px solid #ddd;text-align:center;color:#000">
                    {c.destination}
                  </div>
                  <div style="padding:5px 6px;font-size:12px;
                              text-align:center;color:#555">
                    {heure_arr}
                  </div>
                </div>'''

        html += '</div>'  # fermer le bloc principal
        return format_html(html)

    # ── URLs personnalisées ───────────────────────────────

    def get_urls(self):
        urls = super().get_urls()
        return [
            path('importer-excel/',
                 self.admin_site.admin_view(self.view_importer_excel),
                 name='gestion_bulletin_importer_excel'),
            path('affecter-conducteurs/',
                 self.admin_site.admin_view(self.view_affecter_conducteurs),
                 name='gestion_bulletin_affecter_conducteurs'),
        ] + urls

    # ── Vue import Excel ──────────────────────────────────

    def view_importer_excel(self, request):
        if request.method == 'POST':
            form = ImportExcelForm(request.POST, request.FILES)
            if form.is_valid():
                fichier   = form.cleaned_data['fichier']
                remplacer = form.cleaned_data['remplacer']

                if remplacer:
                    nb = Bulletin.objects.count()
                    Bulletin.objects.all().delete()
                    self.message_user(request, f"{nb} bulletins supprimés.", messages.WARNING)

                rapport = importer_bulletins_excel(fichier, request.user)
                enregistrer_historique(
                    request.user, 'Import bulletins Excel', 'Bulletin', None,
                    {'fichier': fichier.name, **rapport}
                )

                for e in rapport.get('erreurs', []):
                    self.message_user(request, f"Erreur : {e}", messages.ERROR)

                self.message_user(
                    request,
                    f"Import terminé — {rapport['crees']} créés, "
                    f"{rapport['mis_a_jour']} mis à jour, "
                    f"{rapport['vides']} vides, "
                    f"{rapport['total']} avec courses.",
                    messages.SUCCESS
                )
                return redirect('admin:gestion_bulletin_changelist')
        else:
            form = ImportExcelForm()

        context = {
            **self.admin_site.each_context(request),
            'title': 'Importer les bulletins depuis Excel',
            'form':  form,
            'opts':  self.model._meta,
        }
        return render(request, 'admin/gestion/bulletin/import_excel.html', context)

    # ── Vue affectation conducteurs ───────────────────────

    def view_affecter_conducteurs(self, request):
        ids_str   = request.GET.get('bulletins', '') or request.POST.get('bulletins', '')
        ids       = [int(i) for i in ids_str.split(',') if i.strip().isdigit()]
        bulletins = Bulletin.objects.filter(id__in=ids).order_by('type_jour', 'numero')

        if request.method == 'POST':
            form = AffectationRapideForm(request.POST)
            if form.is_valid():
                conducteur   = form.cleaned_data['conducteur']
                date_service = form.cleaned_data['date_service']

                if Affectation.objects.filter(conducteur=conducteur, date_service=date_service).exists():
                    self.message_user(
                        request,
                        f"{conducteur.nom} est déjà affecté le {date_service}.",
                        messages.ERROR
                    )
                else:
                    for bulletin in bulletins:
                        aff, _ = Affectation.objects.update_or_create(
                            conducteur=conducteur,
                            date_service=date_service,
                            defaults={
                                'bulletin':       bulletin,
                                'affecte_par':    request.user,
                                'statut_service': 'en_attente',
                            }
                        )
                        enregistrer_historique(
                            request.user, 'Affectation (admin)', 'Affectation', aff.id,
                            {'conducteur': conducteur.matricule,
                             'bulletin':   bulletin.numero, 'date': str(date_service)}
                        )
                    self.message_user(
                        request,
                        f"{conducteur.nom} {conducteur.prenom} affecté(e) à "
                        f"{len(bulletins)} bulletin(s) pour le {date_service}.",
                        messages.SUCCESS
                    )
                    return redirect('admin:gestion_bulletin_changelist')
        else:
            form = AffectationRapideForm()

        context = {
            **self.admin_site.each_context(request),
            'title':     'Affecter un conducteur aux bulletins',
            'form':      form,
            'bulletins': bulletins,
            'ids_str':   ids_str,
            'opts':      self.model._meta,
        }
        return render(request, 'admin/gestion/bulletin/affecter_conducteurs.html', context)

    # ── Action affecter ───────────────────────────────────

    def affecter_conducteur_action(self, request, queryset):
        ids = ','.join(str(b.id) for b in queryset)
        from django.http import HttpResponseRedirect
        return HttpResponseRedirect(f'../affecter-conducteurs/?bulletins={ids}')
    affecter_conducteur_action.short_description = "Affecter un conducteur à ces bulletins"

    # ── Bouton import dans la liste ───────────────────────

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['import_excel_url'] = 'importer-excel/'
        return super().changelist_view(request, extra_context=extra_context)

    # ── Colonnes calculées ────────────────────────────────

    def nb_courses(self, obj):
        n = obj.courses.count()
        return format_html(
            '<span style="background:#e8f4f8;padding:1px 8px;'
            'border-radius:10px;font-size:12px">{}</span>', n
        )
    nb_courses.short_description = 'Courses'

    def nb_affectations(self, obj):
        return obj.affectations.count()
    nb_affectations.short_description = 'Affectations'

    def type_jour_badge(self, obj):
        if obj.type_jour == Bulletin.JO:
            return format_html(
                '<span style="background:#1565c0;color:#fff;padding:2px 8px;'
                'border-radius:3px;font-size:11px;font-weight:bold">JO</span>'
            )
        return format_html(
            '<span style="background:#6a1b9a;color:#fff;padding:2px 8px;'
            'border-radius:3px;font-size:11px;font-weight:bold">JS/JV</span>'
        )
    type_jour_badge.short_description = 'Type'


# ══════════════════════════════════════════
#  AFFECTATION
# ══════════════════════════════════════════

@admin.register(Affectation)
class AffectationAdmin(admin.ModelAdmin):
    list_display  = ['conducteur_nom', 'bulletin_info', 'date_service',
                     'statut_badge', 'rame', 'confirme']
    list_filter   = ['statut_service', 'confirme', 'date_service']
    search_fields = ['conducteur__nom', 'conducteur__matricule']
    ordering      = ['-date_service']
    date_hierarchy = 'date_service'
    raw_id_fields = ['conducteur', 'bulletin', 'rame', 'affecte_par']
    readonly_fields = ['date_affectation', 'heure_confirmation', 'apercu_bulletin_affecte']

    def conducteur_nom(self, obj):
        return f"{obj.conducteur.nom} {obj.conducteur.prenom} ({obj.conducteur.matricule})"
    conducteur_nom.short_description = 'Conducteur'

    def bulletin_info(self, obj):
        return format_html(
            'Bulletin <strong>{}</strong> <span style="color:#666">({})</span> '
            '{} → {}',
            obj.bulletin.numero,
            obj.bulletin.type_jour,
            str(obj.bulletin.heure_debut)[:5] if obj.bulletin.heure_debut else '--',
            str(obj.bulletin.heure_fin)[:5] if obj.bulletin.heure_fin else '--',
        )
    bulletin_info.short_description = 'Bulletin'

    def statut_badge(self, obj):
        colors = {
            'en_attente': '#f39c12', 'confirme': '#27ae60',
            'absent': '#c0392b', 'retard': '#e67e22',
        }
        c = colors.get(obj.statut_service, '#7f8c8d')
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;'
            'border-radius:3px;font-size:11px">{}</span>',
            c, obj.get_statut_service_display()
        )
    statut_badge.short_description = 'Statut'

    def apercu_bulletin_affecte(self, obj):
        """Aperçu du bulletin dans la fiche d'affectation."""
        ba = BulletinAdmin(Bulletin, admin.site)
        return ba._render_bulletin_html(obj.bulletin)
    apercu_bulletin_affecte.short_description = 'Aperçu du bulletin assigné'

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
                     'cible_accepte', 'traite_par']
    list_filter   = ['statut', 'cible_accepte']
    search_fields = ['demandeur__matricule', 'cible__matricule']
    ordering      = ['-date_demande']
    readonly_fields = ['date_demande', 'date_traitement']

    def statut_badge(self, obj):
        colors = {'en_attente': '#f39c12', 'acceptee': '#27ae60', 'refusee': '#c0392b'}
        c = colors.get(obj.statut, '#7f8c8d')
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;'
            'border-radius:3px;font-size:11px">{}</span>',
            c, obj.get_statut_display()
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
    list_display  = ['date_action', 'utilisateur', 'action', 'table_ciblee']
    list_filter   = ['action', 'table_ciblee']
    search_fields = ['utilisateur__matricule', 'action']
    ordering      = ['-date_action']
    readonly_fields = ['date_action', 'utilisateur', 'action',
                       'table_ciblee', 'objet_id', 'details']

    def has_add_permission(self, request):       return False
    def has_change_permission(self, request, obj=None): return False


# ══════════════════════════════════════════
#  TITRE ADMIN
# ══════════════════════════════════════════

admin.site.site_header = "SETRAM Constantine — Administration"
admin.site.site_title  = "SETRAM"
admin.site.index_title = "Tableau de bord"