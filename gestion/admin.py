# gestion/admin.py
from django import forms
from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin
from django.utils.html import format_html
from django.urls import path
from django.shortcuts import render, redirect
from django.utils import timezone
import datetime

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
        queryset=Utilisateur.objects.filter(
            role='conducteur', is_active=True
        ).order_by('nom'),
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
                'fields': ('matricule', 'password1', 'password2',
                           'nom', 'prenom', 'role')}),
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
    role_badge.short_description = 'Role'


# ══════════════════════════════════════════
#  RAME
# ══════════════════════════════════════════

@admin.register(Rame)
class RameAdmin(admin.ModelAdmin):
    list_display  = ['numero', 'modele', 'etat_badge']
    list_filter   = ['etat']
    search_fields = ['numero', 'modele']

    def etat_badge(self, obj):
        colors = {
            'disponible': '#27ae60',
            'en_service': '#2980b9',
            'maintenance': '#c0392b'
        }
        c = colors.get(obj.etat, '#7f8c8d')
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;'
            'border-radius:3px;font-size:11px">{}</span>',
            c, obj.get_etat_display()
        )
    etat_badge.short_description = 'Etat'


# ══════════════════════════════════════════════════════════
#  UTILITAIRE PARTAGE — rendu bulletin HTML style Excel
#  Utilise par BulletinAdmin ET AffectationAdmin
# ══════════════════════════════════════════════════════════

def render_bulletin_html(bulletin):
    """Retourne une chaine HTML brute representant le bulletin style Excel."""
    courses    = list(bulletin.courses.order_by('ordre'))
    hd         = str(bulletin.heure_debut)[:5] if bulletin.heure_debut else '--:--'
    hf         = str(bulletin.heure_fin)[:5]   if bulletin.heure_fin   else '--:--'
    type_label = 'JO' if bulletin.type_jour == Bulletin.JO else 'JS/JV'

    rows_html = ''
    if not courses:
        rows_html = (
            '<tr><td colspan="7" style="padding:14px;text-align:center;'
            'color:#999;font-style:italic;">Aucune course — bulletin vide</td></tr>'
        )
    else:
        prev_num = None
        for i, c in enumerate(courses):
            is_last = (i == len(courses) - 1)
            bg_row  = '#f9f9f9' if i % 2 == 0 else '#fff'

            if c.origine in ('ZOU1', 'ZOU2'):
                bg_orig, col_orig = '#ff0000', '#fff'
            else:
                bg_orig, col_orig = bg_row, '#000'

            bg_hd  = '#ff0000' if is_last else bg_row
            col_hd = '#fff'    if is_last else '#000'

            course_display = c.numero_course if c.numero_course != prev_num else ''
            if c.numero_course:
                prev_num = c.numero_course

            badge_style = (
                'background:#ffd700;font-weight:bold;color:#000;'
                if course_display else 'color:#ccc;'
            )
            dep = str(c.heure_depart_prev)[:5]  if c.heure_depart_prev  else '--'
            arr = str(c.heure_arrivee_prev)[:5] if c.heure_arrivee_prev else '--'

            rows_html += (
                '<tr style="background:{bg_row};border-top:1px solid #e0e0e0;">'
                '<td style="padding:5px 8px;font-size:11px;{badge}'
                'border-right:1px solid #ddd;text-align:center;">{course}</td>'
                '<td style="padding:5px 8px;border-right:1px solid #ddd;'
                'text-align:center;color:#ccc;font-size:11px;">-</td>'
                '<td style="padding:5px 8px;font-size:12px;font-weight:bold;'
                'background:{bg_orig};color:{col_orig};'
                'border-right:1px solid #ddd;text-align:center;">{orig}</td>'
                '<td style="padding:5px 8px;font-size:12px;font-weight:bold;'
                'background:{bg_hd};color:{col_hd};'
                'border-right:1px solid #ddd;text-align:center;">{dep}</td>'
                '<td style="padding:5px 8px;border-right:1px solid #ddd;'
                'text-align:center;color:#ccc;font-size:11px;">-</td>'
                '<td style="padding:5px 8px;font-size:12px;font-weight:bold;'
                'border-right:1px solid #ddd;text-align:center;color:#000;">{dest}</td>'
                '<td style="padding:5px 8px;font-size:11px;'
                'text-align:center;color:#555;">{arr}</td>'
                '</tr>'
            ).format(
                bg_row=bg_row,
                badge=badge_style,
                course=course_display,
                bg_orig=bg_orig, col_orig=col_orig, orig=c.origine,
                bg_hd=bg_hd, col_hd=col_hd, dep=dep,
                dest=c.destination,
                arr=arr,
            )

    html = (
        '<div style="font-family:Arial,sans-serif;border:2px solid #555;'
        'border-radius:2px;overflow:hidden;min-width:520px;'
        'box-shadow:2px 2px 8px rgba(0,0,0,.18);display:inline-block;">'

        '<div style="display:flex;align-items:stretch;">'

        '<div style="background:#ff0000;flex:1;display:flex;align-items:center;'
        'padding:6px 20px;min-height:68px;">'
        '<span style="color:#fff;font-size:36px;font-weight:900;letter-spacing:2px;">'
        'service {num:02d}</span></div>'

        '<div style="display:flex;flex-direction:column;min-width:130px;">'
        '<div style="background:#ffd700;display:flex;align-items:center;'
        'justify-content:space-between;padding:5px 12px;flex:1;'
        'border-left:2px solid #555;">'
        '<span style="font-size:22px;font-weight:900;color:#000;">{num:02d}</span>'
        '<span style="font-size:16px;font-weight:bold;color:#000;">{hd}</span></div>'

        '<div style="background:#00b0a0;display:flex;align-items:center;'
        'justify-content:space-between;padding:5px 12px;flex:1;'
        'border-left:2px solid #555;border-top:1px solid #555;">'
        '<span style="font-size:12px;font-weight:bold;color:#fff;">{tl}</span>'
        '<span style="font-size:16px;font-weight:bold;color:#fff;">{hf}</span>'
        '</div></div></div>'

        '<div style="background:#00b0a0;padding:4px 10px;border-top:1px solid #555;">'
        '<span style="color:#fff;font-size:11px;font-weight:bold;">'
        'Heures reelles de depart et d\'arrivee</span></div>'

        '<table style="width:100%;border-collapse:collapse;font-size:12px;">'
        '<thead><tr style="background:#00b0a0;">'
        '<th style="padding:5px 8px;color:#fff;font-size:10px;'
        'border-right:1px solid rgba(255,255,255,.3);width:80px;">Course</th>'
        '<th style="padding:5px 8px;color:#fff;font-size:10px;'
        'border-right:1px solid rgba(255,255,255,.3);width:85px;">N Rame</th>'
        '<th style="padding:5px 8px;color:#fff;font-size:10px;'
        'border-right:1px solid rgba(255,255,255,.3);width:95px;">Origine</th>'
        '<th style="padding:5px 8px;color:#fff;font-size:10px;'
        'border-right:1px solid rgba(255,255,255,.3);width:105px;">Heure depart</th>'
        '<th style="padding:5px 8px;color:#fff;font-size:10px;'
        'border-right:1px solid rgba(255,255,255,.3);width:55px;">Retard</th>'
        '<th style="padding:5px 8px;color:#fff;font-size:10px;'
        'border-right:1px solid rgba(255,255,255,.3);width:105px;">Destination</th>'
        '<th style="padding:5px 8px;color:#fff;font-size:10px;width:90px;">H. arrivee</th>'
        '</tr></thead>'
        '<tbody>{rows}</tbody></table>'

        '<div style="background:#f5f5f5;border-top:1px solid #ddd;padding:6px 12px;">'
        '<span style="font-size:11px;color:#666;">{nb} course(s)</span></div>'
        '</div>'
    ).format(
        num=bulletin.numero,
        hd=hd, hf=hf, tl=type_label,
        rows=rows_html,
        nb=len(courses),
    )
    return html


# ══════════════════════════════════════════
#  BULLETIN
# ══════════════════════════════════════════

class CourseInline(admin.TabularInline):
    model      = Course
    extra      = 0
    fields     = ['ordre', 'numero_course', 'origine', 'heure_depart_prev',
                  'destination', 'heure_arrivee_prev']
    ordering   = ['ordre']
    can_delete = True


@admin.register(Bulletin)
class BulletinAdmin(admin.ModelAdmin):
    list_display    = ['numero', 'type_jour_badge', 'heure_debut', 'heure_fin',
                       'nb_courses', 'nb_affectations', 'date_import']
    list_filter     = ['type_jour']
    search_fields   = ['numero']
    ordering        = ['type_jour', 'numero']
    list_per_page   = 25
    readonly_fields = ['date_import', 'importe_par', 'fichier_source', 'apercu_bulletin']
    inlines         = [CourseInline]
    actions         = ['affecter_conducteur_action']

    def apercu_bulletin(self, obj):
        return format_html(render_bulletin_html(obj))
    apercu_bulletin.short_description = 'Apercu bulletin (style Excel)'

    def get_urls(self):
        urls = super().get_urls()
        return [
            path(
                'importer-excel/',
                self.admin_site.admin_view(self.view_importer_excel),
                name='gestion_bulletin_importer_excel',
            ),
            path(
                'affecter-conducteurs/',
                self.admin_site.admin_view(self.view_affecter_conducteurs),
                name='gestion_bulletin_affecter_conducteurs',
            ),
        ] + urls

    def view_importer_excel(self, request):
        if request.method == 'POST':
            form = ImportExcelForm(request.POST, request.FILES)
            if form.is_valid():
                fichier   = form.cleaned_data['fichier']
                remplacer = form.cleaned_data['remplacer']
                if remplacer:
                    nb = Bulletin.objects.count()
                    Bulletin.objects.all().delete()
                    self.message_user(request, f"{nb} bulletins supprimes avant import.", messages.WARNING)
                rapport = importer_bulletins_excel(fichier, request.user)
                enregistrer_historique(
                    request.user, 'Import bulletins Excel', 'Bulletin', None,
                    {'fichier': fichier.name, **rapport}
                )
                for e in rapport.get('erreurs', []):
                    self.message_user(request, f"Erreur : {e}", messages.ERROR)
                self.message_user(
                    request,
                    f"Import termine - {rapport['crees']} crees, "
                    f"{rapport['mis_a_jour']} mis a jour, "
                    f"{rapport['vides']} vides, {rapport['total']} avec courses.",
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
                    self.message_user(request, f"{conducteur.nom} est deja affecte le {date_service}.", messages.ERROR)
                else:
                    for bulletin in bulletins:
                        aff, _ = Affectation.objects.update_or_create(
                            conducteur=conducteur, date_service=date_service,
                            defaults={'bulletin': bulletin, 'affecte_par': request.user, 'statut_service': 'en_attente'}
                        )
                        enregistrer_historique(
                            request.user, 'Affectation (admin)', 'Affectation', aff.id,
                            {'conducteur': conducteur.matricule, 'bulletin': bulletin.numero, 'date': str(date_service)}
                        )
                    self.message_user(
                        request,
                        f"{conducteur.nom} {conducteur.prenom} affecte(e) a {len(bulletins)} bulletin(s) pour le {date_service}.",
                        messages.SUCCESS
                    )
                    return redirect('admin:gestion_bulletin_changelist')
        else:
            form = AffectationRapideForm()

        context = {
            **self.admin_site.each_context(request),
            'title': 'Affecter un conducteur aux bulletins',
            'form': form, 'bulletins': bulletins,
            'ids_str': ids_str, 'opts': self.model._meta,
        }
        return render(request, 'admin/gestion/bulletin/affecter_conducteurs.html', context)

    def affecter_conducteur_action(self, request, queryset):
        ids = ','.join(str(b.id) for b in queryset)
        from django.http import HttpResponseRedirect
        return HttpResponseRedirect(f'../affecter-conducteurs/?bulletins={ids}')
    affecter_conducteur_action.short_description = "Affecter un conducteur a ces bulletins"

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['import_excel_url'] = 'importer-excel/'
        type_jour = request.GET.get('type_jour', '')
        qs = Bulletin.objects.prefetch_related('courses').order_by('type_jour', 'numero')
        if type_jour in ('JO', 'JS_JV'):
            qs = qs.filter(type_jour=type_jour)
        extra_context['bulletins'] = qs
        extra_context['is_paginated'] = False
        extra_context['headers'] = [
            'Course', 'N Rame', 'Origine', 'Heure depart', 'Retard', 'Destination', 'H. arrivee'
        ]
        return super().changelist_view(request, extra_context=extra_context)

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
    list_display    = ['conducteur_nom', 'bulletin_info', 'date_service',
                       'statut_badge', 'rame', 'confirme']
    list_filter     = ['statut_service', 'confirme', 'date_service']
    search_fields   = ['conducteur__nom', 'conducteur__matricule']
    ordering        = ['-date_service']
    date_hierarchy  = 'date_service'
    raw_id_fields   = ['conducteur', 'bulletin', 'rame', 'affecte_par']
    readonly_fields = ['date_affectation', 'heure_confirmation', 'apercu_bulletin_affecte']

    # Affiche le bulletin style Excel dans la page de detail d'une affectation
    fieldsets = (
        ('Conducteur et Service', {
            'fields': ('conducteur', 'bulletin', 'date_service', 'rame', 'affecte_par'),
        }),
        ('Statut', {
            'fields': ('statut_service', 'confirme', 'heure_confirmation',
                       'motif_absence', 'heure_retard', 'date_affectation'),
        }),
        ('Bulletin du conducteur - Apercu style Excel', {
            'fields': ('apercu_bulletin_affecte',),
            'classes': ('wide',),
        }),
    )

    def get_urls(self):
        urls = super().get_urls()
        return [
            path(
                'affecter/',
                self.admin_site.admin_view(self.view_affecter),
                name='gestion_affectation_affecter',
            ),
        ] + urls

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['show_affecter_button'] = True

        # Recuperer toutes les affectations avec bulletin + courses precharges
        qs = (
            Affectation.objects
            .select_related('conducteur', 'bulletin', 'rame')
            .prefetch_related('bulletin__courses')
            .order_by('-date_service', 'conducteur__nom')
        )

        # Filtrer par date si date_hierarchy actif
        date_str = request.GET.get('date_service__date', '')
        if date_str:
            try:
                qs = qs.filter(date_service=datetime.date.fromisoformat(date_str))
            except ValueError:
                pass

        statut_colors = {
            'en_attente': ('#f39c12', 'En attente'),
            'confirme':   ('#27ae60', 'Confirme'),
            'absent':     ('#c0392b', 'Absent'),
            'retard':     ('#e67e22', 'En retard'),
        }

        affectations_data = []
        for aff in qs[:200]:
            color, label = statut_colors.get(aff.statut_service, ('#7f8c8d', aff.statut_service))
            affectations_data.append({
                'aff':           aff,
                'statut_color':  color,
                'statut_label':  label,
                'bulletin_html': render_bulletin_html(aff.bulletin),
            })

        extra_context['affectations_data'] = affectations_data
        return super().changelist_view(request, extra_context=extra_context)

    def view_affecter(self, request):
        rapport        = None
        conducteurs    = Utilisateur.objects.filter(role='conducteur', is_active=True).order_by('nom', 'prenom')
        bulletins_jo   = Bulletin.objects.filter(type_jour=Bulletin.JO).order_by('numero')
        bulletins_jsjv = Bulletin.objects.filter(type_jour=Bulletin.JS_JV).order_by('numero')

        if request.method == 'POST':
            date_str = request.POST.get('date_service')
            if not date_str:
                messages.error(request, 'Veuillez choisir une date.')
            else:
                try:
                    date_service = datetime.date.fromisoformat(date_str)
                    nb_ok = nb_skip = 0
                    erreurs = []
                    for conducteur in conducteurs:
                        bulletin_id = request.POST.get(f'bulletin_{conducteur.id}')
                        if not bulletin_id:
                            nb_skip += 1
                            continue
                        try:
                            bulletin = Bulletin.objects.get(pk=bulletin_id)
                            Affectation.objects.update_or_create(
                                conducteur=conducteur,
                                date_service=date_service,
                                defaults={
                                    'bulletin': bulletin,
                                    'affecte_par': request.user,
                                    'statut_service': 'en_attente',
                                    'confirme': False,
                                }
                            )
                            nb_ok += 1
                        except Exception as e:
                            erreurs.append(f"{conducteur.nom} {conducteur.prenom} : {e}")
                    rapport = {'date': date_str, 'nb_ok': nb_ok, 'nb_skip': nb_skip, 'erreurs': erreurs}
                    if erreurs:
                        messages.warning(request, f"{nb_ok} affectation(s) enregistree(s), {len(erreurs)} erreur(s).")
                    else:
                        messages.success(request, f"{nb_ok} affectation(s) enregistree(s) pour le {date_str}.")
                except ValueError:
                    messages.error(request, 'Date invalide.')

        context = {
            **self.admin_site.each_context(request),
            'title': 'Affecter les conducteurs aux services',
            'opts': self.model._meta,
            'conducteurs': conducteurs,
            'bulletins_jo': bulletins_jo,
            'bulletins_jsjv': bulletins_jsjv,
            'rapport': rapport,
            'today': datetime.date.today().isoformat(),
        }
        return render(request, 'admin/gestion/affectation/affecter.html', context)

    def conducteur_nom(self, obj):
        return f"{obj.conducteur.nom} {obj.conducteur.prenom} ({obj.conducteur.matricule})"
    conducteur_nom.short_description = 'Conducteur'

    def bulletin_info(self, obj):
        return format_html(
            'Bulletin <strong>{}</strong> <span style="color:#666">({})</span> {} -> {}',
            obj.bulletin.numero,
            obj.bulletin.type_jour,
            str(obj.bulletin.heure_debut)[:5] if obj.bulletin.heure_debut else '--',
            str(obj.bulletin.heure_fin)[:5]   if obj.bulletin.heure_fin   else '--',
        )
    bulletin_info.short_description = 'Bulletin'

    def statut_badge(self, obj):
        colors = {
            'en_attente': '#f39c12', 'confirme':  '#27ae60',
            'absent':     '#c0392b', 'retard':    '#e67e22',
        }
        c = colors.get(obj.statut_service, '#7f8c8d')
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;'
            'border-radius:3px;font-size:11px">{}</span>',
            c, obj.get_statut_service_display()
        )
    statut_badge.short_description = 'Statut'

    def apercu_bulletin_affecte(self, obj):
        """Apercu style Excel du bulletin - affiche dans la page detail de l'affectation."""
        return format_html(render_bulletin_html(obj.bulletin))
    apercu_bulletin_affecte.short_description = 'Bulletin du conducteur'

    def save_model(self, request, obj, form, change):
        if not obj.affecte_par_id:
            obj.affecte_par = request.user
        super().save_model(request, obj, form, change)


# ══════════════════════════════════════════
#  PERMUTATION
# ══════════════════════════════════════════

@admin.register(Permutation)
class PermutationAdmin(admin.ModelAdmin):
    list_display    = ['demandeur', 'cible', 'date_service', 'motif_tronque',
                       'statut_badge', 'cible_accepte', 'traite_par', 'actions_admin']
    list_filter     = ['statut', 'cible_accepte']
    search_fields   = ['demandeur__matricule', 'cible__matricule']
    ordering        = ['-date_demande']
    readonly_fields = ['date_demande', 'date_traitement']
    actions         = ['traiter_permutations_selectionnees']

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if obj.statut == Permutation.ACCEPTEE and obj.cible_accepte and not obj.bulletins_echanges:
            if obj.appliquer_echange_bulletins():
                messages.success(request, 'Permutation acceptée enregistrée et bulletins échangés.')
            else:
                messages.warning(request, 'Permutation acceptée enregistrée, mais pas d’affectations prêtes pour échange.')

    def traiter_permutations_selectionnees(self, request, queryset):
        from django.db import transaction
        traite = 0
        with transaction.atomic():
            for p in queryset.filter(cible_accepte=True, statut__in=[Permutation.EN_ATTENTE, Permutation.ACCEPTEE]):
                if p.statut == Permutation.EN_ATTENTE:
                    p.statut = Permutation.ACCEPTEE
                p.traite_par = request.user
                p.date_traitement = timezone.now()
                p.save()

                if p.appliquer_echange_bulletins():
                    traite += 1
                else:
                    messages.warning(request, f"Permutation #{p.id} acceptée mais affectations manquantes ou déjà échangées.")

        messages.success(request, f"{traite} permutation(s) traitée(s) de la sélection.")

        messages.success(request, f"{traite} permutation(s) traitée(s) de la sélection.")
    traiter_permutations_selectionnees.short_description = 'Traiter les permutations sélectionnées (acceptees)'

    fieldsets = (
        ('Demandeurs et Date', {
            'fields': ('demandeur', 'cible', 'date_service'),
        }),
        ('Motif et Décision', {
            'fields': ('motif', 'statut', 'cible_accepte', 'motif_refus'),
        }),
        ('Traitement', {
            'fields': ('traite_par', 'date_demande', 'date_traitement'),
        }),
    )

    def statut_badge(self, obj):
        colors = {
            'en_attente': '#f39c12',
            'acceptee':   '#27ae60',
            'refusee':    '#c0392b'
        }
        c = colors.get(obj.statut, '#7f8c8d')
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;'
            'border-radius:3px;font-size:11px">{}</span>',
            c, obj.get_statut_display()
        )
    statut_badge.short_description = 'Statut'

    def motif_tronque(self, obj):
        if obj.motif:
            return obj.motif[:50] + '...' if len(obj.motif) > 50 else obj.motif
        return '-'
    motif_tronque.short_description = 'Motif'

    def actions_admin(self, obj):
        if obj.statut == 'en_attente':
            return format_html(
                '<a href="{}" style="background:#27ae60;color:#fff;padding:2px 8px;'
                'border-radius:3px;text-decoration:none;font-size:11px;margin-right:4px">Accepter</a>'
                '<a href="{}" style="background:#c0392b;color:#fff;padding:2px 8px;'
                'border-radius:3px;text-decoration:none;font-size:11px">Refuser</a>',
                f'/admin/gestion/permutation/{obj.id}/accepter/',
                f'/admin/gestion/permutation/{obj.id}/refuser/'
            )
        return '-'
    actions_admin.short_description = 'Actions'

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('<int:pk>/accepter/', self.accepter_permutation, name='permutation_accepter'),
            path('<int:pk>/refuser/', self.refuser_permutation, name='permutation_refuser'),
        ]
        return custom_urls + urls

    def accepter_permutation(self, request, pk):
        from django.shortcuts import get_object_or_404, redirect
        from django.contrib import messages
        from django.db import transaction
        from .models import Affectation
        from .utils import envoyer_notification, enregistrer_historique

        p = get_object_or_404(Permutation, pk=pk)
        if p.statut != 'en_attente':
            messages.error(request, 'Cette permutation a déjà été traitée.')
            return redirect('/admin/gestion/permutation/')

        with transaction.atomic():
            p.statut = Permutation.ACCEPTEE
            p.cible_accepte = True
            p.traite_par = request.user
            p.date_traitement = timezone.now()
            p.save()

            if p.appliquer_echange_bulletins():
                messages.success(request, f'Permutation acceptée et bulletins échangés.')
            else:
                messages.warning(request, 'Permutation acceptée mais affectations manquantes pour échanger les bulletins.')

        # Notifications
        for c in [p.demandeur, p.cible]:
            envoyer_notification(c, Notification.PERMUTATION,
                                 'Décision permutation',
                                 f'Votre permutation du {p.date_service} a été acceptée.')
        enregistrer_historique(request.user, 'Permutation acceptée',
                               'Permutation', p.id, {'decision': 'accepter'})

        return redirect('/admin/gestion/permutation/')

    def refuser_permutation(self, request, pk):
        from django.shortcuts import get_object_or_404, redirect
        from django.contrib import messages
        from django.db import transaction
        from .utils import envoyer_notification, enregistrer_historique

        p = get_object_or_404(Permutation, pk=pk)
        if p.statut != 'en_attente':
            messages.error(request, 'Cette permutation a déjà été traitée.')
            return redirect('/admin/gestion/permutation/')

        motif = request.GET.get('motif', 'Refusée par l\'administrateur')

        with transaction.atomic():
            p.statut = Permutation.REFUSEE
            p.cible_accepte = False
            p.traite_par = request.user
            p.motif_refus = motif
            p.date_traitement = timezone.now()
            p.save()

        # Notifications
        for c in [p.demandeur, p.cible]:
            envoyer_notification(c, Notification.PERMUTATION,
                                 'Décision permutation',
                                 f'Votre permutation du {p.date_service} a été refusée.')
        enregistrer_historique(request.user, 'Permutation refusée',
                               'Permutation', p.id, {'decision': 'refuser'})

        messages.success(request, f'Permutation refusée.')
        return redirect('/admin/gestion/permutation/')


# ══════════════════════════════════════════
#  NOTIFICATION
# ══════════════════════════════════════════

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display    = ['destinataire', 'type_notif', 'titre', 'lu', 'date_envoi']
    list_filter     = ['type_notif', 'lu']
    search_fields   = ['destinataire__matricule', 'titre']
    ordering        = ['-date_envoi']
    readonly_fields = ['date_envoi', 'date_lecture']


# ══════════════════════════════════════════
#  HISTORIQUE
# ══════════════════════════════════════════

@admin.register(HistoriqueModification)
class HistoriqueAdmin(admin.ModelAdmin):
    list_display    = ['date_action', 'utilisateur', 'action', 'table_ciblee']
    list_filter     = ['action', 'table_ciblee']
    search_fields   = ['utilisateur__matricule', 'action']
    ordering        = ['-date_action']
    readonly_fields = ['date_action', 'utilisateur', 'action',
                       'table_ciblee', 'objet_id', 'details']

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


# ══════════════════════════════════════════
#  TITRE ADMIN
# ══════════════════════════════════════════

admin.site.site_header = "SETRAM Constantine - Administration"
admin.site.site_title  = "SETRAM"
admin.site.index_title = "Tableau de bord"