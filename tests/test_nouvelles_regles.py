"""Horaires 08h-23h, 4 créneaux, distinction des fichiers, cerveau local, images."""
import datetime as dt

import appointments
import brain_local
import files_kind
import images_ia
import opening_hours


def test_ouvert_08h_ferme_23h():
    tz = opening_hours._tz()
    ouvert = dt.datetime(2026, 11, 28, 10, 0, tzinfo=tz)
    tot = dt.datetime(2026, 11, 28, 7, 59, tzinfo=tz)
    tard = dt.datetime(2026, 11, 28, 23, 0, tzinfo=tz)
    assert opening_hours.is_open(ouvert)
    assert not opening_hours.is_open(tot)
    assert not opening_hours.is_open(tard)


def test_hors_horaires_ne_prend_aucune_commande():
    texte = opening_hours.closed_reply("fr", "chatbot")
    assert "fermé" in texte.lower()
    assert "8h00" in texte
    assert "noté" in texte.lower()


def test_quatre_creneaux_par_jour_entre_8h_et_23h():
    assert appointments.HEURES == (8, 13, 18, 22)
    assert all(8 <= h < 23 for h in appointments.HEURES)


def test_distingue_image_pdf_tableau_lien_code():
    assert files_kind.classify("photo.jpg", "image/jpeg") == "image"
    assert files_kind.classify("devis.pdf", "application/pdf") == "pdf"
    assert files_kind.classify("prix.csv", "text/csv") == "tableau"
    assert files_kind.classify(text="regarde https://komara.agency") == "lien"
    assert files_kind.classify(text="CMD-2026-14") == "code"


def test_cerveau_local_sans_api_reste_sur_la_grille():
    reponse = brain_local.composer("je veux un logo", "boutique de vêtements", "Awa")
    assert "50 €" in reponse
    assert "devis" in reponse.lower()
    # aucun prix inventé
    assert "70" not in reponse and "90" not in reponse


def test_image_gratuite_sans_cle_api():
    prompt = images_ia.construire_prompt("boutique de tissus à Conakry", service="logo")
    assert "logo" in prompt
    assert "http" not in prompt
