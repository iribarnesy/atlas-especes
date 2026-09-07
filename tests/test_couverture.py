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
