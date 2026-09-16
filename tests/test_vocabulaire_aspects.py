#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vocabulaire des aspects : source unique dans atlas_data.ASPECTS (cf. #8).

La liste était recopiée dans couverture.py, site_ui.py, generer_quiz.py, fetch_aspects.py et
la documentation — avec des copies divergentes (« rameau » connu du site, ignoré de
COUVERTURE.md et absent de CONTRIBUTING.md).
"""
import json

import pytest

from conftest import load_module, vignette_cell


# --------------------------------------------------------------- cohérence interne

def test_les_mots_cles_derivent_de_la_liste(atlas_data):
    for a in atlas_data.ASPECTS:
        assert atlas_data.ASPECT_KW[a.id] == a.id
        for syn in a.synonymes:
            assert atlas_data.ASPECT_KW[syn] == a.id, syn


def test_les_mots_cles_historiques_sont_tous_reconnus(atlas_data):
    # Ce que les noms de fichiers du dépôt utilisent déjà : rien ne doit disparaître.
    attendu = {"feuille": "feuille", "feuilles": "feuille", "ecorce": "ecorce",
               "fruit": "fruit", "fruits": "fruit", "fleur": "fleur", "fleurs": "fleur",
               "rameau": "rameau", "rameaux": "rameau", "bourgeon": "rameau",
               "hiver": "rameau", "port": "port", "silhouette": "port"}

    assert atlas_data.ASPECT_KW == attendu


def test_aucun_identifiant_ni_synonyme_en_double(atlas_data):
    mots = [kw for a in atlas_data.ASPECTS for kw in (a.id,) + a.synonymes]

    assert len(mots) == len(set(mots))


def test_le_vocabulaire_accepte_divers_et_planche(atlas_data):
    """_aspects.tsv accepte deux mots qui ne sont PAS des aspects : « divers » (photo sans
    aspect annoncé) et « planche » (gravure ancienne — cf. #30). Ni l'un ni l'autre ne doit
    se glisser dans ASPECT_IDS, sinon ils deviendraient une colonne de COUVERTURE.md et un
    filtre du quiz."""
    assert atlas_data.ASPECTS_VALIDES == (set(atlas_data.ASPECT_IDS)
                                          | {atlas_data.DIVERS, atlas_data.PLANCHE})
    assert atlas_data.DIVERS not in atlas_data.ASPECT_IDS
    assert atlas_data.PLANCHE not in atlas_data.ASPECT_IDS


def test_chaque_aspect_est_complet(atlas_data):
    for a in atlas_data.ASPECTS:
        assert a.id and a.id.islower() and a.id.isalpha(), a
        assert a.label and atlas_data.ASPECT_LABEL[a.id] == a.label
        assert a.emoji and a.terme_en, a
    assert atlas_data.ASPECT_LABEL[atlas_data.DIVERS]


def test_rameau_est_entre_dans_l_objectif_de_couverture(atlas_data):
    """La décision de #8 le gardait HORS objectif tant qu'aucune photo ne l'utilisait, pour
    ne pas ouvrir une colonne vide dans COUVERTURE.md. Le lot 8 a versé les premières et le
    tableau le compte depuis ; le drapeau a suivi. Sans lui, la fiche du site annoncerait
    des manques différents de ceux du tableau."""
    rameau = [a for a in atlas_data.ASPECTS if a.id == "rameau"]

    assert rameau and rameau[0].cible is True
    assert "rameau" in atlas_data.ASPECTS_VALIDES
    assert atlas_data.ASPECT_KW["bourgeon"] == "rameau"


def test_tout_aspect_de_l_objectif_est_un_aspect_valide(atlas_data):
    """Garde-fou : un aspect visé par la couverture doit pouvoir être écrit dans un nom de
    fichier, sinon on afficherait un manque que personne ne peut combler."""
    for a in atlas_data.ASPECTS:
        if a.cible:
            assert a.id in atlas_data.ASPECTS_VALIDES


# ------------------------------------------------------- les consommateurs en dérivent

def test_couverture_liste_les_aspects_de_l_objectif(repo, monkeypatch):
    couverture = load_module("couverture")
    monkeypatch.setattr(couverture, "atlas_data", repo.atlas_data)
    repo.vignette("chene.jpg")
    repo.extra_photo("chene-feuille-1.jpg")

    colonnes = couverture.aspects_du_tableau(
        [{"stem": "chene", "paths": [repo.extra + "/chene-feuille-1.jpg"]}])

    assert [k for k, _ in colonnes] == [a.id for a in repo.atlas_data.ASPECTS if a.cible]


def test_couverture_ajoute_une_colonne_des_la_premiere_photo(repo, monkeypatch):
    """Un aspect HORS objectif gagne sa colonne dès qu'une photo l'utilise. C'est ce qui
    est arrivé au rameau, entré dans l'objectif depuis ; la mécanique reste utile pour le
    prochain aspect qu'on ajoutera sans le viser tout de suite."""
    couverture = load_module("couverture")
    monkeypatch.setattr(couverture, "atlas_data", repo.atlas_data)
    repo.extra_photo("chene-rameau-1.jpg")

    colonnes = couverture.aspects_du_tableau(
        [{"stem": "chene", "paths": [repo.extra + "/chene-rameau-1.jpg"]}])

    assert "rameau" in [k for k, _ in colonnes]


def test_le_site_recoit_le_vocabulaire_dans_ses_donnees():
    build_web = load_module("build_web")
    atlas_data = load_module("atlas_data")

    envoye = build_web.aspects_web()

    assert [a["id"] for a in envoye] == list(atlas_data.ASPECT_IDS)
    for a in envoye:
        assert set(a) == {"id", "label", "emoji", "cible"}
    json.dumps(envoye)   # doit être sérialisable pour l'injection


def test_ajouter_un_aspect_suffit_pour_le_site(monkeypatch):
    """Preuve que le site n'a pas de copie en dur : un aspect ajouté à la source apparaît
    dans l'index.html généré."""
    atlas_data = load_module("atlas_data")
    build_web = load_module("build_web")
    monkeypatch.setattr(build_web, "atlas_data", atlas_data)
    monkeypatch.setattr(atlas_data, "ASPECTS", list(atlas_data.ASPECTS) + [
        atlas_data.Aspect("racine", "Racine", ("racines",), "🥕", True, "root")])

    html = build_web.assemble([])

    assert '"id": "racine"' in html or '"id":"racine"' in html
    assert "Racine" in html
    assert "__ASPECTS__" not in html


def test_le_generateur_local_utilise_la_meme_source():
    generer_quiz = load_module("generer_quiz")
    atlas_data = load_module("atlas_data")

    assert [a["id"] for a in generer_quiz.aspects_js()] == list(atlas_data.ASPECT_IDS)


def test_les_termes_de_recherche_viennent_du_vocabulaire():
    fetch_aspects = load_module("fetch_aspects")
    atlas_data = load_module("atlas_data")
    termes = {a.id: a.terme_en for a in atlas_data.ASPECTS}

    for aspect, terme in fetch_aspects.ASP_LIG + fetch_aspects.ASP_HERB:
        assert termes[aspect] == terme


# ------------------------------------------- les manques de couverture arrivent au site

def test_le_site_recoit_les_manques_de_chaque_espece(repo, monkeypatch):
    """Le champ « cible » partait déjà dans les données du site, mais rien ne le lisait :
    la fiche ne pouvait pas dire qu'il manque un fruit. Elle reçoit maintenant la liste."""
    build_web = load_module("build_web")
    monkeypatch.setattr(build_web, "atlas_data", repo.atlas_data)
    repo.vignette("sauge.jpg")
    repo.extra_photo("sauge-feuille-1.jpg")
    repo.write_atlas("Herbes - référence.md", [[vignette_cell("sauge.jpg"), "Sauge",
                                                "Salvia officinalis", "vivace", "Lamiacées",
                                                "oui", ""]])
    repo.use_atlases("Herbes - référence.md", cat="herbace")

    d = build_web.to_web_data(repo.parse("Herbes - référence.md", cat="herbace"))[0]

    assert d["gaps"] == ["fruit", "fleur", "port"]
    assert d["no"] == ["ecorce", "rameau"]
    json.dumps(d)   # doit rester sérialisable pour l'injection


def test_une_espece_complete_ne_porte_aucun_manque(repo, monkeypatch):
    """Pas de clé vide dans les données : une fiche complète ne doit rien afficher."""
    build_web = load_module("build_web")
    monkeypatch.setattr(build_web, "atlas_data", repo.atlas_data)
    repo.vignette("sauge.jpg")
    for a in ("feuille", "fruit", "fleur", "port"):
        repo.extra_photo("sauge-%s-1.jpg" % a)
    repo.write_atlas("Herbes - référence.md", [[vignette_cell("sauge.jpg"), "Sauge",
                                                "Salvia officinalis", "vivace", "Lamiacées",
                                                "oui", ""]])
    repo.use_atlases("Herbes - référence.md", cat="herbace")

    d = build_web.to_web_data(repo.parse("Herbes - référence.md", cat="herbace"))[0]

    assert "gaps" not in d
    assert d["no"] == ["ecorce", "rameau"]


def test_la_fiche_affiche_le_bloc_des_manques():
    """Le rendu : sans ces chaînes, les données arriveraient au site sans être montrées —
    exactement l'état dans lequel « cible » est resté depuis sa création."""
    site_ui = load_module("site_ui")

    assert "fHasGaps" in site_ui.JS and "fGaps" in site_ui.JS
    assert "Photo manquante" in site_ui.JS
    assert "Sans objet pour cette espèce" in site_ui.JS
    # le bloc doit être visuellement distinct de « Confusions fréquentes », qui partage
    # la même couleur d'alerte : le trait pointillé est ce qui les sépare
    assert "dashed var(--color-warning)" in site_ui.JS
