#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Réduction des photos téléchargées par les fetchers.

Historiquement les deux fetchers appelaient `sips`, qui n'existe que sur macOS. Ailleurs
l'appel levait FileNotFoundError, l'exception était avalée par le `except Exception` du
fetcher, et il ne restait qu'un fichier `.orig` orphelin et aucune photo — sans message.
On essaie donc Pillow d'abord (portable, déjà utilisé par le build), `sips` ensuite, et à
défaut on lève : une erreur franche coûte moins cher à diagnostiquer qu'un silence.

Comme `sips -Z` et `Image.thumbnail()`, LARGEUR borne la **plus grande** dimension : une
photo en portrait est donc moins large que LARGEUR. L'image n'est jamais agrandie.
"""
import io
import os
import shutil
import subprocess
import tempfile

LARGEUR = 420
QUALITE = 70

try:
    from PIL import Image
    PILLOW = True
except ImportError:                                          # pragma: no cover
    PILLOW = False


def redimensionneur():
    """'pillow', 'sips' ou None — ce qui est disponible ici, dans l'ordre de préférence."""
    if PILLOW:
        return "pillow"
    if shutil.which("sips"):
        return "sips"
    return None


def _via_pillow(buf, dest, largeur, qualite):
    im = Image.open(io.BytesIO(buf))
    im.load()
    if im.mode not in ("RGB", "L"):
        im = im.convert("RGB")
    im.thumbnail((largeur, largeur), Image.LANCZOS)
    im.save(dest, "JPEG", quality=qualite, optimize=True, progressive=True)


def _via_sips(buf, dest, largeur, qualite):
    fd, tmp = tempfile.mkstemp(suffix=".orig", dir=os.path.dirname(dest) or ".")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(buf)
        r = subprocess.run(
            ["sips", "-Z", str(largeur), "-s", "format", "jpeg",
             "-s", "formatOptions", str(qualite), tmp, "--out", dest],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        if r.returncode != 0 or not os.path.exists(dest):
            raise RuntimeError("sips a échoué : %s" % r.stderr.decode("utf-8", "replace").strip())
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def reduire(buf, dest, largeur=LARGEUR, qualite=QUALITE):
    """Écrit `buf` (octets d'une image) en JPEG réduit dans `dest`.

    Ne laisse pas de fichier derrière elle en cas d'échec, et lève une exception explicite
    si aucun outil de redimensionnement n'est disponible.
    """
    outil = redimensionneur()
    if outil is None:
        raise RuntimeError(
            "aucun redimensionneur : installez Pillow (pip install Pillow) — "
            "`sips` n'existe que sur macOS")
    try:
        (_via_pillow if outil == "pillow" else _via_sips)(buf, dest, largeur, qualite)
    except Exception:
        if os.path.exists(dest):
            os.remove(dest)
        raise


def largeur_demandee(argv, defaut=LARGEUR):
    """Valeur de --largeur dans argv, sinon `defaut`."""
    for i, a in enumerate(argv):
        if a == "--largeur" and i + 1 < len(argv):
            return int(argv[i + 1])
    return defaut
