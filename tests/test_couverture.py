#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""COUVERTURE.md : les manques comptés par aspect (scripts/couverture.py).

Le tableau sert à décider où contribuer. Il comptait l'écorce et le rameau sur les 191
plantes, alors que ces deux aspects ne concernent que les 77 ligneux : 114 « manques »
étaient donc des herbacées à qui on reprochait de n'avoir ni tronc ni bourgeon d'hiver.
"""
from conftest import load_module, vignette_cell


def test_l_ecorce_et_le_rameau_ne_concernent_que_les_ligneux(atlas_data):
    assert atlas_data.aspect_applicable("ecorce", "ligneux")
    assert not atlas_data.aspect_applicable("ecorce", "herbace")
    assert atlas_data.aspect_applicable("rameau", "ligneux")
    assert not atlas_data.aspect_applicable("rameau", "herbace")


def test_ni_un_sous_arbrisseau_ni_une_liane_n_a_de_tronc(atlas_data):
    """Un cran plus fin que la catégorie : reprocher une écorce à une callune n'a pas plus
    de sens qu'à une herbacée. La règle se dérive de la colonne « Type » de l'atlas."""
    for t in ("sous-arbrisseau", "liane", "Sous-arbrisseau", " liane "):
        assert not atlas_data.aspect_applicable("ecorce", "ligneux", t)
        assert not atlas_data.aspect_applicable("rameau", "ligneux", t)
        # les autres aspects restent attendus : une bruyère a bien feuille et fleur
        assert atlas_data.aspect_applicable("feuille", "ligneux", t)
        assert atlas_data.aspect_applicable("fleur", "ligneux", t)


def test_un_arbre_ou_un_arbuste_garde_tronc_et_rameau(atlas_data):
    for t in ("arbre", "arbuste", "arbre/arbuste", ""):
        assert atlas_data.aspect_applicable("ecorce", "ligneux", t)
        assert atlas_data.aspect_applicable("rameau", "ligneux", t)


def test_les_autres_aspects_s_appliquent_partout(atlas_data):
    for asp in ("feuille", "fleur", "fruit", "port"):
        assert atlas_data.aspect_applicable(asp, "ligneux")
        assert atlas_data.aspect_applicable(asp, "herbace")


def test_un_persistant_n_a_pas_de_rameau_d_hiver(atlas_data):
    """Le rameau est défini comme l'état où l'on identifie un ligneux SANS ses feuilles.
    Un olivier ou un chêne vert n'est jamais dans cet état : l'aspect n'a pas d'objet, et
    le lot 17 a cherché ces rameaux nus en vain parce qu'il n'y a rien à photographier."""
    for stem in ("olivier", "chene_vert", "chene_liege", "arbousier", "feijoa", "houx",
                 "pin_maritime", "epicea", "if"):
        assert not atlas_data.aspect_applicable("rameau", "ligneux", "arbre", stem)
        # l'écorce, elle, existe toujours
        assert atlas_data.aspect_applicable("ecorce", "ligneux", "arbre", stem)


def test_les_exclusions_volontaires_de_la_regle_des_persistants(atlas_data):
    """Trois cas qui ressemblent à des persistants sans en être, et gardent leur rameau :
    le mélèze est un conifère CADUC ; l'ajonc et le genêt perdent leurs feuilles et ce
    sont justement leurs rameaux verts qu'on regarde en hiver ; le troène est
    semi-persistant, donc nu par hiver froid."""
    for stem in ("meleze", "ajonc", "genet", "troene"):
        assert atlas_data.aspect_applicable("rameau", "ligneux", "arbuste", stem)


def test_la_regle_des_persistants_ne_touche_que_le_rameau(atlas_data):
    """On n'enlève pas la feuille à un olivier : c'est même par elle qu'on le reconnaît."""
    for asp in ("feuille", "fleur", "fruit", "port", "ecorce"):
        assert atlas_data.aspect_applicable(asp, "ligneux", "arbre", "olivier")


def test_une_herbacee_sans_ecorce_n_est_pas_comptee_comme_incomplete(repo):
    """Le cas qui faussait le compte : une herbacée avec feuille, fleur, fruit et port
    est complète, même sans écorce ni rameau."""
    cv = load_module("couverture")
    repo.vignette("sauge.jpg")
    for nom in ("sauge-feuille-1.jpg", "sauge-fleur-1.jpg", "sauge-fruit-1.jpg",
                "sauge-port-1.jpg"):
        repo.extra_photo(nom)
    repo.write_atlas("Herbes - référence.md", [[vignette_cell("sauge.jpg"), "Sauge",
                                                "Salvia officinalis", "vivace", "Lamiacées",
                                                "oui", ""]])
    repo.use_atlases("Herbes - référence.md", cat="herbace")
    sp = repo.parse("Herbes - référence.md", cat="herbace")
    assert len(sp) == 1
    present = cv.aspects_present(sp[0])
    assert {"feuille", "fleur", "fruit", "port"} <= present
    assert "ecorce" not in present
    attendus = {a for a in ("feuille", "ecorce", "fruit", "fleur", "port", "rameau")
                if repo.atlas_data.aspect_applicable(a, "herbace")}
    assert attendus <= present, "une herbacée complète ne doit rien devoir à l'écorce"


# ----------------------------------------- le même calcul pour le tableau ET pour la fiche

def test_bilan_separe_les_manques_des_sans_objet(repo):
    """Source unique du calcul : avant, COUVERTURE.md savait qu'il manquait un port au
    noyer et la fiche du site l'ignorait — un lecteur ne pouvait donc pas voir où une
    photo serait utile."""
    repo.vignette("sauge.jpg")
    for nom in ("sauge-feuille-1.jpg", "sauge-fleur-1.jpg"):
        repo.extra_photo(nom)
    repo.write_atlas("Herbes - référence.md", [[vignette_cell("sauge.jpg"), "Sauge",
                                                "Salvia officinalis", "vivace", "Lamiacées",
                                                "oui", ""]])
    repo.use_atlases("Herbes - référence.md", cat="herbace")
    sp = repo.parse("Herbes - référence.md", cat="herbace")[0]

    manquants, sans_objet = repo.atlas_data.bilan_aspects(sp)

    assert manquants == ["fruit", "port"]          # dans l'ordre de ASPECTS
    assert sans_objet == ["ecorce", "rameau"]      # une herbacée n'a ni l'un ni l'autre
    assert "feuille" not in manquants and "fleur" not in manquants


def test_une_photo_divers_ne_comble_aucun_manque(repo):
    """« divers » n'est pas un aspect : une vue d'ensemble sans aspect annoncé ne doit pas
    faire disparaître un manque de la fiche."""
    repo.vignette("sauge.jpg")
    repo.extra_photo("sauge-1.jpg")
    repo.write_atlas("Herbes - référence.md", [[vignette_cell("sauge.jpg"), "Sauge",
                                                "Salvia officinalis", "vivace", "Lamiacées",
                                                "oui", ""]])
    repo.use_atlases("Herbes - référence.md", cat="herbace")
    sp = repo.parse("Herbes - référence.md", cat="herbace")[0]

    manquants, _ = repo.atlas_data.bilan_aspects(sp)

    assert manquants == ["feuille", "fruit", "fleur", "port"]


def test_un_champignon_ne_se_voit_reprocher_aucun_manque(atlas_data):
    """Les aspects ne décrivent que des plantes. Reprocher une feuille à un cèpe afficherait
    sur sa fiche un manque que personne ne pourra jamais combler."""
    for cat in ("champignon", "faune", "divers"):
        sp = {"stem": "x", "cat": cat, "fields": {}, "paths": []}
        assert atlas_data.bilan_aspects(sp) == ([], [])
