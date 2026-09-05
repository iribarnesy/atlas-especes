#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Récupération de photos **à valider à l'œil** avant d'entrer dans l'atlas.

fetch_aspects.py interroge Commons en plein texte et garde le premier résultat ; sur les
apiacées et les astéracées il se trompe, et une photo de ciguë qui n'en est pas est pire
que pas de photo. Ici on procède en deux temps :

  1. `--lot` télécharge une poignée de **candidats** par espèce dans candidats/<stem>/,
     avec un candidats.tsv qui porte déjà l'auteur, la licence et la page d'origine ;
  2. on **regarde** chaque image, on remplit un fichier de choix, et `--promouvoir` la
     range dans img/quiz-extra/ sous son nom définitif en écrivant son crédit.

Rien n'entre dans le dépôt sans être passé par l'étape 2 : c'est tout l'intérêt.

Les candidats viennent de la **catégorie Commons** de l'espèce (Category:<Nom latin>)
plutôt que d'une recherche plein texte : le classement y est fait par des humains, et
Commons n'héberge pas de licence non commerciale — donc pas de tri de licence à faire.

  python3 scripts/candidats.py --lot lots/lot-1-confusions.txt
  python3 scripts/candidats.py --especes cigue,berce --par-espece 8
  python3 scripts/candidats.py --promouvoir candidats/choix.tsv

Format de candidats/choix.tsv (tabulations, « # » en commentaire) :

  candidats/cigue/03.jpg⇥cigue-feuille_port-1.jpg
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

import atlas_data
import credits
import images

BASE = atlas_data.BASE
EXTRA = atlas_data.EXTRA
DEST = os.path.join(BASE, "candidats")
UA = "ForestryQuiz/1.0 (personal educational use)"
API = "https://commons.wikimedia.org/w/api.php?"
PAR_ESPECE = 7

# Ce qui n'est pas une photo de terrain exploitable pour un quiz : planches botaniques,
# herbiers, coupes au microscope, cartes de répartition, œuvres d'art.
REJET = ("herbari", "illustration", "drawing", "dessin", "plate", "engraving", "gravure",
         "specimen", "microscop", "epidermis", "chromosom", "map", "range", "distribution",
         "locator", "icon", "logo", "diagram", "chart", "signature", "stamp", "coin",
         " art", "painting", "sketch", "botanicus", "flora batava", "kohler", "köhler",
         "thome", "sturm", "lindman", "masclef", "bilder ur nordens flora")
SOUS_CAT_REJET = ("herbarium", "art", "seedling", "animals", "by country", "cultivated",
                  "stamps", "philately", "maps")

# Mots d'organe dans les noms de fichiers Commons, toutes langues confondues : ils servent
# à répartir les candidats entre aspects, pas à décider — le tri définitif se fait à l'œil.
MOTS = {
    "fleur": ("flower", "fleur", "blüte", "blute", "bloem", "inflorescen", "umbel",
              "ombelle", "blomma", "kwiat", "flor", "fiore", "bloom", "capitul"),
    "feuille": ("leaf", "leaves", "feuille", "blatt", "blad", "foliage", "liść", "lisc",
                "hoja", "foglia", "rosette", "rosett"),
    "fruit": ("fruit", "seed", "graine", "frucht", "mericarp", "achene", "akene",
              "samen", "owoc", "semilla", "capsule", "gousse"),
    "port": ("habit", "plant", "port", "habitus", "whole", "pflanze", "stand",
             "population", "growing", "stem", "tige", "stengel"),
}
ORDRE = ("feuille", "fleur", "fruit", "port")


# ------------------------------------------------------------------- API Commons

def api(**kw):
    kw.setdefault("format", "json")
    kw.setdefault("action", "query")
    req = urllib.request.Request(API + urllib.parse.urlencode(kw), headers={"User-Agent": UA})
    for essai in range(4):
        try:
            with urllib.request.urlopen(req, timeout=40) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(8 + essai * 8)
                continue
            raise
    return {}


def _pages(d):
    return list((d.get("query") or {}).get("pages", {}).values())


def fichiers_categorie(titre, largeur):
    d = api(generator="categorymembers", gcmtitle=titre, gcmtype="file", gcmlimit="500",
            prop="imageinfo", iiprop="url|size|mime|extmetadata", iiurlwidth=str(largeur))
    return _pages(d)


def sous_categories(titre):
    noms = [p["title"] for p in _pages(api(generator="categorymembers", gcmtitle=titre,
                                           gcmtype="subcat", gcmlimit="200"))]
    return [n for n in noms if not any(m in n.lower() for m in SOUS_CAT_REJET)]


def aspect_devine(titre):
    t = titre.lower()
    for asp in ORDRE:
        if any(m in t for m in MOTS[asp]):
            return asp
    return atlas_data.DIVERS


def utilisable(page):
    titre = page.get("title", "").lower()
    if any(b in titre for b in REJET) or titre.endswith(".svg"):
        return False
    ii = (page.get("imageinfo") or [{}])[0]
    if ii.get("mime") not in ("image/jpeg", "image/png"):
        return False
    if not ii.get("thumburl"):
        return False
    # une image plus petite que la cible n'a pas d'intérêt : la fiche montre l'original
    return (ii.get("width") or ii.get("thumbwidth") or 0) >= 800


def candidats(latin, n, largeur):
    """n pages Commons de l'espèce, réparties entre aspects (les plus déficitaires d'abord)."""
    vus, retenus = set(), []
    pages = fichiers_categorie("Category:" + latin, largeur)
    for sc in sous_categories("Category:" + latin)[:4]:
        time.sleep(0.6)
        pages += fichiers_categorie(sc, largeur)
    pages = [p for p in pages if utilisable(p) and not (p["title"] in vus or vus.add(p["title"]))]
    par_aspect = {}
    for p in pages:
        par_aspect.setdefault(aspect_devine(p["title"]), []).append(p)
    # un tour par aspect tant qu'il reste de la place : on veut de la variété, pas dix fleurs
    tour = 0
    while len(retenus) < n and any(par_aspect.get(a) for a in ORDRE + (atlas_data.DIVERS,)):
        vide = True
        for asp in ORDRE + (atlas_data.DIVERS,):
            lot = par_aspect.get(asp) or []
            if tour < len(lot) and len(retenus) < n:
                retenus.append((asp, lot[tour]))
                vide = False
        if vide:
            break
        tour += 1
    return retenus


# --------------------------------------------------------------- téléchargement

def telecharger(url, dest, largeur):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        buf = r.read()
    if len(buf) < 1500:
        raise IOError("fichier trop petit")
    images.reduire(buf, dest, largeur)


def recolter(especes, n, largeur):
    for i, (stem, latin) in enumerate(especes, 1):
        dossier = os.path.join(DEST, stem)
        os.makedirs(dossier, exist_ok=True)
        lignes, k = [], 0
        try:
            trouves = candidats(latin, n, largeur)
        except Exception as e:
            print("[%d/%d] %-12s ÉCHEC %s" % (i, len(especes), stem, e))
            continue
        for asp, page in trouves:
            ii = (page.get("imageinfo") or [{}])[0]
            k += 1
            nom = "%02d.jpg" % k
            try:
                telecharger(ii["thumburl"], os.path.join(dossier, nom), largeur)
            except Exception as e:
                print("   %s/%s : %s" % (stem, nom, e))
                continue
            c = credits.credit_commons(ii)
            lignes.append("\t".join([nom, asp, page["title"], c["auteur"], c["licence"], c["url"]]))
            time.sleep(0.4)
        with open(os.path.join(dossier, "candidats.tsv"), "w", encoding="utf-8") as fh:
            fh.write("fichier\taspect_devine\ttitre_commons\tauteur\tlicence\turl\n")
            fh.write("\n".join(lignes) + ("\n" if lignes else ""))
        print("[%d/%d] %-12s (%s) : %d candidat(s)" % (i, len(especes), stem, latin, len(lignes)))
        time.sleep(0.8)


# ------------------------------------------------------------------- promotion

def lire_choix(chemin):
    out = []
    for ln in open(chemin, encoding="utf-8"):
        ln = ln.split("#")[0].strip()
        if not ln:
            continue
        cells = [c.strip() for c in ln.split("\t") if c.strip()]
        if len(cells) != 2:
            raise SystemExit("ligne mal formée dans %s : %r" % (chemin, ln))
        out.append(tuple(cells))
    return out


def promouvoir(chemin):
    """Copie les candidats choisis dans img/quiz-extra/ et écrit leur crédit."""
    n = 0
    for source, final in lire_choix(chemin):
        src = source if os.path.isabs(source) else os.path.join(BASE, source)
        if not os.path.exists(src):
            raise SystemExit("candidat introuvable : %s" % src)
        meta = {}
        tsv = os.path.join(os.path.dirname(src), "candidats.tsv")
        for ln in open(tsv, encoding="utf-8"):
            c = ln.rstrip("\n").split("\t")
            if c[0] == os.path.basename(src) and len(c) >= 6:
                meta = {"auteur": c[3], "licence": c[4], "url": c[5]}
        if not meta:
            raise SystemExit("pas de crédit pour %s dans %s" % (src, tsv))
        dest = os.path.join(EXTRA, final)
        with open(src, "rb") as a, open(dest, "wb") as b:
            b.write(a.read())
        credits.noter(dest, source="wikimedia", **meta)
        n += 1
    print("%d photo(s) promue(s) dans img/quiz-extra/, créditées dans img/CREDITS.tsv." % n)


# ------------------------------------------------------------------------- main

def especes_du_lot(argv):
    """[(stem, nom latin)] pour le lot demandé, dans l'ordre du lot."""
    toutes = []
    for nom, cat in atlas_data.ATLASES:
        for e in atlas_data.parse_atlas(nom, cat, set()):
            toutes.append((e["stem"], e.get("latin") or ""))
    arg = None
    for i, a in enumerate(argv):
        if a in ("--lot", "--especes") and i + 1 < len(argv):
            arg = argv[i + 1]
    if not arg:
        raise SystemExit("précisez --lot <fichier> ou --especes a,b,c")
    retenus, inconnus = atlas_data.selection([s for s, _ in toutes], atlas_data.lire_lot(arg))
    if inconnus:
        raise SystemExit("stem(s) inconnu(s) : %s" % ", ".join(inconnus))
    ordre = {s: i for i, s in enumerate(retenus)}
    vus = set()
    sel = [(s, l) for s, l in toutes if s in ordre and not (s in vus or vus.add(s))]
    return sorted(sel, key=lambda x: ordre[x[0]])


def latin_court(l):
    l = l.split("/")[0].strip()
    l = re.sub(r"\bsp\.?$", "", l).strip()
    return " ".join(l.split()[:2])


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    for i, a in enumerate(argv):
        if a == "--promouvoir" and i + 1 < len(argv):
            return promouvoir(argv[i + 1])
    n = PAR_ESPECE
    for i, a in enumerate(argv):
        if a == "--par-espece" and i + 1 < len(argv):
            n = int(argv[i + 1])
    especes = [(s, latin_court(l)) for s, l in especes_du_lot(argv)]
    print("%d espèce(s), %d candidats chacune → candidats/" % (len(especes), n))
    recolter(especes, n, images.largeur_demandee(argv))


if __name__ == "__main__":
    main()
