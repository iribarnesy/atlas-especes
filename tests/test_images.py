#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Réduction des photos téléchargées (scripts/images.py).

Les fetchers appelaient `sips`, absent hors macOS : l'exception était avalée par leur
`except Exception` et il ne restait qu'un `.orig` orphelin, sans message. On vérifie donc
surtout les deux garanties qui manquaient — un échec bruyant, et rien qui traîne après.
"""
import io
import os

import pytest

from conftest import load_module

PIL = pytest.importorskip("PIL", reason="Pillow absent : réduction non testée")
from PIL import Image  # noqa: E402  (après importorskip)


@pytest.fixture
def images():
    return load_module("images")


def octets(taille=(1600, 1000), couleur=(90, 140, 60)):
    """Les octets d'un JPEG, tels que les rend une réponse HTTP."""
    buf = io.BytesIO()
    Image.new("RGB", taille, couleur).save(buf, "JPEG", quality=90)
    return buf.getvalue()


# ------------------------------------------------------------------ dimensions

def test_borne_la_plus_grande_dimension(images, tmp_path):
    dest = str(tmp_path / "p.jpg")
    images.reduire(octets((1600, 1000)), dest, largeur=420)
    assert Image.open(dest).size == (420, 263)


def test_une_photo_en_portrait_est_moins_large_que_la_consigne(images, tmp_path):
    """Comme `sips -Z`, c'est le plus grand côté qui est borné : d'où les extras en 315x420."""
    dest = str(tmp_path / "p.jpg")
    images.reduire(octets((1000, 1600)), dest, largeur=420)
    assert Image.open(dest).size == (262, 420)


def test_n_agrandit_pas_une_petite_image(images, tmp_path):
    dest = str(tmp_path / "p.jpg")
    images.reduire(octets((300, 200)), dest, largeur=1200)
    assert Image.open(dest).size == (300, 200)


def test_sortie_en_jpeg_meme_depuis_un_png(images, tmp_path):
    buf = io.BytesIO()
    Image.new("RGBA", (800, 600), (10, 20, 30, 255)).save(buf, "PNG")
    dest = str(tmp_path / "p.jpg")
    images.reduire(buf.getvalue(), dest, largeur=420)
    assert Image.open(dest).format == "JPEG"


# ----------------------------------------------------------------- robustesse

def test_un_contenu_illisible_leve_et_ne_laisse_rien(images, tmp_path):
    dest = str(tmp_path / "p.jpg")
    with pytest.raises(Exception):
        images.reduire(b"ceci n'est pas une image", dest)
    assert os.listdir(str(tmp_path)) == []


def test_sans_redimensionneur_le_message_est_explicite(images, tmp_path, monkeypatch):
    """Le silence d'hier : sans Pillow ni sips, on veut une erreur qui se lit."""
    monkeypatch.setattr(images, "redimensionneur", lambda: None)
    with pytest.raises(RuntimeError, match="Pillow"):
        images.reduire(octets(), str(tmp_path / "p.jpg"))


def test_pillow_est_prefere_a_sips(images):
    assert images.redimensionneur() == "pillow"


# ---------------------------------------------------------------- ligne de commande

def test_largeur_demandee(images):
    assert images.largeur_demandee(["--lot", "x.txt"], defaut=420) == 420
    assert images.largeur_demandee(["--largeur", "900"], defaut=420) == 900
