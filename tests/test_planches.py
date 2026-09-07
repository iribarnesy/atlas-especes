#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Planches anciennes : comptées dans « Divers » et dans « Tout », jamais dans un aspect.

Une planche montre souvent tous les organes d'un coup, mais IDÉALISÉS : port redressé,
couleurs franches. On y reconnaît une plante qu'on connaît déjà ; on n'y apprend pas ce
qu'on verra dans un fossé au mois d'août. D'où la décision de #30 : elle n'entre pas dans
les filtres d'aspect.
"""
from conftest import load_module, vignette_cell


def test_une_planche_n_a_aucun_aspect(atlas_data):
    assert atlas_data.aspect_of("muguet-planche-2.jpg", "muguet") == ["divers"]
    assert atlas_data.est_planche("muguet-planche-2.jpg", "muguet")


def test_une_photo_ordinaire_garde_ses_aspects(atlas_data):
    assert atlas_data.aspect_of("muguet-feuille_fleur-1.jpg", "muguet") == ["feuille", "fleur"]
    assert not atlas_data.est_planche("muguet-feuille_fleur-1.jpg", "muguet")


def test_le_jeton_planche_ecrase_les_aspects_du_nom(atlas_data):
    """Si les deux sont là, la planche gagne : on ne veut pas d'un dessin dans un filtre."""
    assert atlas_data.aspect_of("hysope-planche_feuille-1.jpg", "hysope") == ["divers"]


def test_gravure_est_accepte_comme_synonyme(atlas_data):
    assert atlas_data.est_planche("melisse-gravure-1.jpg", "melisse")


def test_le_sidecar_peut_marquer_une_planche(repo):
    repo.vignette("sauge.jpg")
    repo.extra_photo("sauge-2.jpg")
    repo.sidecar("fichier\taspects\nsauge-2.jpg\tplanche\n")
    assert repo.atlas_data.aspect_of("sauge-2.jpg", "sauge") == ["divers"]
    assert repo.atlas_data.est_planche("sauge-2.jpg", "sauge")


def test_planche_est_accepte_dans_le_vocabulaire_du_sidecar(atlas_data):
    """verifier_atlas.py refuse ce qui n'est pas dans ASPECTS_VALIDES."""
    assert "planche" in atlas_data.ASPECTS_VALIDES


def test_planche_n_est_pas_un_aspect_de_l_atlas(atlas_data):
    """Garde-fou : le marqueur ne doit pas se glisser parmi les aspects.

    Il ne doit donc apparaître ni dans ASPECT_IDS, ni comme colonne de COUVERTURE.md.
    """
    assert atlas_data.PLANCHE not in atlas_data.ASPECT_IDS
    assert atlas_data.PLANCHE not in atlas_data.ASPECT_KW


def test_le_verificateur_ne_se_plaint_pas_du_jeton_planche(repo):
    va = load_module("verifier_atlas")
    repo.vignette("sauge.jpg")
    repo.extra_photo("sauge-planche-1.jpg")
    repo.write_atlas("Herbes - référence.md", [[vignette_cell("sauge.jpg"), "Sauge",
                                                "Salvia officinalis", "vivace", "Lamiacées",
                                                "oui", ""]])
    repo.use_atlases("Herbes - référence.md", cat="herbace")
    va.atlas_data = repo.atlas_data
    errs, warns = va.verifier_photos_extra({"sauge"})
    assert not [w for w in warns if "planche" in w], warns
