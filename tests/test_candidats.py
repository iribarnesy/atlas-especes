#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Récolte et promotion des candidats photo (scripts/candidats.py).

L'outil sert à ne rien verser dans l'atlas sans l'avoir regardé : on teste donc surtout
ce qui décide à ma place — le tri des titres, la répartition entre aspects — et les deux
garanties de la promotion : le crédit est écrit, et rien n'est écrasé en silence.
"""
import os

import pytest

from conftest import load_module


@pytest.fixture
def cd(repo, monkeypatch):
    """Le module, branché sur le faux dépôt."""
    module = load_module("candidats")
    cr = load_module("credits")
    monkeypatch.setattr(cr, "BASE", repo.root)
    monkeypatch.setattr(cr, "CREDITS", os.path.join(repo.root, "img", "CREDITS.tsv"))
    monkeypatch.setattr(cr, "atlas_data", repo.atlas_data)
    monkeypatch.setattr(module, "credits", cr)
    monkeypatch.setattr(module, "BASE", repo.root)
    monkeypatch.setattr(module, "EXTRA", repo.extra)
    monkeypatch.setattr(module, "DEST", os.path.join(repo.root, "candidats"))
    module.credits_module = cr
    return module


# --------------------------------------------------- ce qui se juge sur le titre

def test_les_mots_d_organe_sont_reconnus_en_plusieurs_langues(cd):
    assert cd.aspect_devine("File:Conium maculatum flowers.jpg") == "fleur"
    assert cd.aspect_devine("File:Aronstab Blüte.jpg") == "fleur"
    assert cd.aspect_devine("File:Alliaria petiolata leaves.jpg") == "feuille"
    assert cd.aspect_devine("File:Kopr owoc.jpg") == "fruit"
    assert cd.aspect_devine("File:Heracleum-sphondylium-habitus.jpg") == "port"


def test_l_ecorce_est_reconnue_et_prime_sur_le_port(cd):
    """L'aspect le plus déficitaire du dépôt : sans ces mots, toute écorce tombait dans
    « divers » et la répartition ne la sortait jamais en tête."""
    assert cd.aspect_devine("File:Carpinus betulus bark.jpg") == "ecorce"
    assert cd.aspect_devine("File:Olea europaea tronc.jpg") == "ecorce"
    assert cd.aspect_devine("File:Prunus avium Rinde.jpg") == "ecorce"
    # « trunk » parle du tronc, pas de la silhouette, même quand « tree » suit
    assert cd.aspect_devine("File:Ficus carica trunk of an old tree.jpg") == "ecorce"
    assert cd.aspect_devine("File:Ficus carica tree.jpg") == "port"


def test_un_titre_muet_reste_a_trier_a_l_oeil(cd, repo):
    assert cd.aspect_devine("File:Autumn flowers 01.jpg") == "fleur"
    assert cd.aspect_devine("File:20170410Artemisia absinthium3.jpg") == repo.atlas_data.DIVERS


@pytest.mark.parametrize("titre", [
    "File:Prof. Dr. Thomé's Flora von Deutschland (Pl. 381).jpg",   # planche botanique
    "File:Flora Danica Hft 27 Tab 1572.jpg",
    "File:Applied and economic botany for students.jpg",
    "File:Conium maculatum herbarium specimen.jpg",
    "File:A bowl of dill seed.jpg",                                  # photo de cuisine
    "File:Chilean salad ingredients cilantro tomatoes.jpg",
    "File:Farmer's Market - Chervil.jpg",
    "File:Anethum graveolens - Distribuzione.PNG",                   # carte
    "File:Anthriscus cerefolium distribution in Poland.svg",         # pas une photo
])
def test_titres_ecartes_avant_meme_le_telechargement(cd, titre):
    assert not cd.titre_utilisable(titre)


def test_une_photo_de_terrain_passe(cd):
    assert cd.titre_utilisable("File:Conium maculatum fruit (01).jpg")
    assert cd.titre_utilisable("File:Heracleum sphondylium flowering.JPEG")


# ------------------------------------------------------- répartition des aspects

def _titres(*noms):
    return list(noms)


def test_la_repartition_alterne_les_aspects(cd):
    """Neuf fleurs et une feuille ne font pas un lot exploitable : on veut de la variété."""
    titres = _titres(*["File:X flower %d.jpg" % i for i in range(9)],
                     "File:X leaf.jpg", "File:X fruit.jpg")
    pris = cd._repartir(titres, 4, cle=lambda t: t)
    assert sorted(a for a, _ in pris) == ["feuille", "fleur", "fleur", "fruit"]


def test_l_ecorce_passe_avant_le_reste_dans_la_repartition(cd):
    """Sur un lot de ligneux, une seule écorce disponible doit être prise au premier tour."""
    titres = _titres(*["File:X flower %d.jpg" % i for i in range(5)], "File:X bark.jpg")
    pris = cd._repartir(titres, 2, cle=lambda t: t)
    assert pris[0][0] == "ecorce"


def test_la_repartition_ne_reclame_pas_plus_que_disponible(cd):
    pris = cd._repartir(_titres("File:X leaf.jpg"), 5, cle=lambda t: t)
    assert len(pris) == 1


# -------------------------------------------------------- lecture des choix

def test_les_commentaires_et_les_lignes_vides_sont_ignores(cd, repo):
    p = repo.write("choix.tsv", "# un commentaire\n\ncandidats/cigue/01.jpg\tcigue-fleur-1.jpg\n")
    assert cd.lire_choix(p) == [("candidats/cigue/01.jpg", "cigue-fleur-1.jpg")]


def test_une_ligne_mal_formee_arrete_tout(cd, repo):
    p = repo.write("choix.tsv", "candidats/cigue/01.jpg cigue-fleur-1.jpg\n")
    with pytest.raises(SystemExit):
        cd.lire_choix(p)


# ------------------------------------------------------------------ promotion

def _candidat(repo, stem, nom, octets=b"\xff\xd8photo\xff\xd9", auteur="Alice Dupont"):
    d = os.path.join(repo.root, "candidats", stem)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, nom), "wb") as fh:
        fh.write(octets)
    with open(os.path.join(d, "candidats.tsv"), "w", encoding="utf-8") as fh:
        fh.write("fichier\taspect_devine\ttitre_commons\tauteur\tlicence\turl\n")
        fh.write("\t".join([nom, "fleur", "File:X.jpg", auteur, "CC BY-SA 4.0",
                            "https://commons.wikimedia.org/wiki/File:X.jpg"]) + "\n")
    return "candidats/%s/%s" % (stem, nom)


def test_la_promotion_ecrit_la_photo_et_son_credit(cd, repo):
    src = _candidat(repo, "cigue", "01.jpg")
    p = repo.write("choix.tsv", "%s\tcigue-fleur-1.jpg\n" % src)
    cd.promouvoir(p)
    assert os.path.exists(os.path.join(repo.extra, "cigue-fleur-1.jpg"))
    entree = cd.credits_module.charger()["cigue-fleur-1.jpg"]
    assert entree["auteur"] == "Alice Dupont"
    assert entree["licence"] == "CC BY-SA 4.0"
    assert cd.credits_module.connu(entree)


def test_une_photo_sans_credit_n_entre_pas_dans_l_atlas(cd, repo):
    src = _candidat(repo, "cigue", "01.jpg")
    # la fiche de crédits ne mentionne pas ce fichier-là
    open(os.path.join(repo.root, "candidats", "cigue", "candidats.tsv"), "w",
         encoding="utf-8").write("fichier\taspect_devine\ttitre_commons\tauteur\tlicence\turl\n")
    p = repo.write("choix.tsv", "%s\tcigue-fleur-1.jpg\n" % src)
    with pytest.raises(SystemExit):
        cd.promouvoir(p)
    assert not os.path.exists(os.path.join(repo.extra, "cigue-fleur-1.jpg"))


def test_rejouer_le_meme_fichier_de_choix_est_sans_effet(cd, repo):
    src = _candidat(repo, "cigue", "01.jpg")
    p = repo.write("choix.tsv", "%s\tcigue-fleur-1.jpg\n" % src)
    cd.promouvoir(p)
    cd.promouvoir(p)
    assert open(os.path.join(repo.extra, "cigue-fleur-1.jpg"), "rb").read() == b"\xff\xd8photo\xff\xd9"


def test_on_n_ecrase_pas_une_autre_photo_en_silence(cd, repo, monkeypatch):
    """Le piège du dossier à 300 fichiers : un nom déjà pris passerait inaperçu."""
    repo.extra_photo("cigue-fleur-1.jpg")
    src = _candidat(repo, "cigue", "01.jpg")
    p = repo.write("choix.tsv", "%s\tcigue-fleur-1.jpg\n" % src)
    monkeypatch.setattr(cd.sys, "argv", ["candidats.py"])
    with pytest.raises(SystemExit, match="existe déjà"):
        cd.promouvoir(p)
    assert open(os.path.join(repo.extra, "cigue-fleur-1.jpg"), "rb").read() == b"\xff\xd8\xff\xd9"


def test_remplacer_assume_l_ecrasement(cd, repo, monkeypatch):
    repo.extra_photo("cigue-fleur-1.jpg")
    src = _candidat(repo, "cigue", "01.jpg")
    p = repo.write("choix.tsv", "%s\tcigue-fleur-1.jpg\n" % src)
    monkeypatch.setattr(cd.sys, "argv", ["candidats.py", "--remplacer"])
    cd.promouvoir(p)
    assert open(os.path.join(repo.extra, "cigue-fleur-1.jpg"), "rb").read() == b"\xff\xd8photo\xff\xd9"


def test_un_chemin_complet_sort_de_quiz_extra(cd, repo):
    """Les vignettes vivent dans img/especes/ : le remplacement doit pouvoir les viser."""
    src = _candidat(repo, "oseille", "02.jpg")
    p = repo.write("choix.tsv", "%s\timg/especes/oseille.jpg\n" % src)
    cd.promouvoir(p)
    assert os.path.exists(os.path.join(repo.img, "oseille.jpg"))
