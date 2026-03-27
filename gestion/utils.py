from django.utils import timezone
from .models import Notification, HistoriqueModification, Bulletin, Course
import openpyxl, re, datetime


def envoyer_notification(destinataire, type_notif, titre, message):
    Notification.objects.create(
        destinataire=destinataire,
        type_notif=type_notif,
        titre=titre,
        message=message,
    )
    # Push Firebase — activé si fcm_token présent
    if destinataire.fcm_token:
        envoyer_push_firebase(destinataire.fcm_token, titre, message)


def envoyer_push_firebase(fcm_token, titre, message):
    """
    Envoie une notification push via Firebase FCM.
    Installe : pip install firebase-admin
    Configure GOOGLE_APPLICATION_CREDENTIALS dans settings.py
    """
    try:
        import firebase_admin
        from firebase_admin import messaging, credentials
        if not firebase_admin._apps:
            cred = credentials.Certificate('chemin/vers/serviceAccountKey.json')
            firebase_admin.initialize_app(cred)
        msg = messaging.Message(
            notification=messaging.Notification(title=titre, body=message),
            token=fcm_token,
        )
        messaging.send(msg)
    except Exception as e:
        print(f"Erreur FCM : {e}")


def enregistrer_historique(utilisateur, action, table, objet_id, details=None):
    HistoriqueModification.objects.create(
        utilisateur=utilisateur,
        action=action,
        table_ciblee=table,
        objet_id=objet_id,
        details=details or {},
    )


def importer_bulletins_excel(fichier, importeur):
    wb      = openpyxl.load_workbook(fichier, data_only=True)
    rapport = {'total': 0, 'crees': 0, 'mis_a_jour': 0, 'erreurs': []}

    SHEET_TYPE = {'JO': Bulletin.JO, 'JS et JV': Bulletin.JS_JV}
    BLOCK_COLS, BLOCK_ROWS = 11, 20

    def get_origin(n):
        idx = n - 1
        return (idx % 10) * BLOCK_ROWS + 1, (idx // 10) * BLOCK_COLS + 1

    def fmt_time(v):
        if isinstance(v, datetime.time):     return v
        if isinstance(v, datetime.datetime): return v.time()
        return None

    for sheet_name, type_jour in SHEET_TYPE.items():
        if sheet_name not in wb.sheetnames:
            continue
        ws = wb[sheet_name]
        for n in range(1, 71):
            sr, sc = get_origin(n)
            val = ws.cell(sr, sc).value
            if not (val and isinstance(val, str) and re.match(r'service\s+\d+', val.lower())):
                continue
            hd = fmt_time(ws.cell(sr,     sc + 9).value)
            hf = fmt_time(ws.cell(sr + 2, sc + 9).value)
            if not hd:
                rapport['erreurs'].append(f'{sheet_name} service {n}: heure manquante')
                continue
            bulletin, created = Bulletin.objects.update_or_create(
                numero=n, type_jour=type_jour,
                defaults={'heure_debut': hd, 'heure_fin': hf or hd,
                          'importe_par': importeur,
                          'fichier_source': getattr(fichier, 'name', '')}
            )
            if created: rapport['crees'] += 1
            else:
                rapport['mis_a_jour'] += 1
                bulletin.courses.all().delete()
            ordre = 0
            for ro in range(6, BLOCK_ROWS - 1):
                origine  = ws.cell(sr + ro, sc + 3).value
                dep      = fmt_time(ws.cell(sr + ro, sc + 4).value)
                dest     = ws.cell(sr + ro, sc + 6).value
                arr      = fmt_time(ws.cell(sr + ro, sc + 7).value)
                if not (origine and dep): continue
                cv = ws.cell(sr + ro, sc).value
                Course.objects.create(
                    bulletin=bulletin,
                    numero_course=str(cv).strip() if cv else '',
                    origine=str(origine).strip(),
                    destination=str(dest).strip() if dest else '',
                    heure_depart_prev=dep,
                    heure_arrivee_prev=arr,
                    ordre=ordre,
                )
                ordre += 1
            rapport['total'] += 1
    return rapport