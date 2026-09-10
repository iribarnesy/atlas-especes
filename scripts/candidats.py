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
  python3 scripts/candidats.py --especes aneth --motcle flower   combler un aspect manquant
  python3 scripts/candidats.py --especes groseillier --categorie "Ribes rubrum"
  python3 scripts/candidats.py --lot lots/lot-4-faune.txt --faune   varier larve/dégâts
  python3 scripts/candidats.py --especes muguet --planches   garder les planches anciennes
  python3 scripts/candidats.py --promouvoir candidats/choix.tsv

Format de candidats/choix.tsv (tabulations, « # » en commentaire) :

  candidats/cigue/03.jpg⇥cigue-feuille_port-1.jpg
  candidats/oseille/02.jpg⇥img/especes/oseille.jpg      (chemin complet : hors quiz-extra)
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

# Wikimedia ne met en cache qu'un petit nombre de largeurs de vignettes. Demander 1000 px
# force un rendu à chaque appel, et l'API finit par répondre 429 en renvoyant justement à
# la liste des tailles servies depuis le cache. On demande donc la première largeur
# standard au-dessus de celle qu'on veut, et images.reduire() ramène au format voulu.
LARGEURS_CACHE = (320, 640, 800, 1024, 1280, 1920, 2560)


def largeur_cachee(largeur):
    """Première largeur standard ≥ `largeur`, pour être servi depuis le cache Wikimedia."""
    for w in LARGEURS_CACHE:
        if w >= largeur:
            return w
    return LARGEURS_CACHE[-1]
PAR_ESPECE = 7
SOUS_CATS = 6      # sous-catégories explorées par espèce

# Ce qui n'est pas une photo de terrain exploitable pour un quiz : planches botaniques,
# herbiers, coupes au microscope, cartes de répartition, œuvres d'art.
# Recueils de planches et d'illustrations anciennes. Elles sont écartées par défaut
# — une gravure n'apprend pas à reconnaître une plante sur le terrain — mais ce sont de
# belles pièces, souvent plus lisibles qu'une photo pour montrer tous les organes d'un
# coup : --planches les garde (cf. #30).
REJET_PLANCHES = (
    "herbari", "illustration", "drawing", "dessin", "plate", "(pl.", "engraving", "gravure",
    "specimen", "botanicus", "flora batava", "florabatava", "flora danica", "floradanica",
    "flora von", "flore des", "botanical register", "cyclopedia", "wellcome", "bhl",
    "annual report", "flora agaricina", "giftpflanze", "bresadola", "atlas des champignons",
    "planche", "tab.", "krombholz", "sowerby", "britzelmayr", "iconograph",
    "kohler", "köhler", "thome", "thomé", "sturm", "lindman", "masclef", "prof. dr",
    "bilder ur nordens flora", "text-book", "textbook", "traité", "economic botany",
    "pflanzendecke", "atlas des plantes",
)

# Ce qui n'est de toute façon pas une image d'espèce exploitable.
REJET = (
    "microscop", "epidermis", "chromosom", "map", "range", "distribu", "repartition",
    "locator", "icon", "logo", "diagram", "chart", "signature", "stamp", "coin",
    " art", "painting", "sketch",
    # photos de cuisine et d'étal : le sujet n'est plus la plante sur pied
    "bowl", "salad", "salade", "market", "spice", "recipe", "dish ", "soup", "grocery",
    "supermarket", "packet", "jar ", "chutney", "curry", "smoothie", "garnish",
)
SOUS_CAT_REJET = ("herbarium", "art", "seedling", "animals", "by country", "cultivated",
                  "stamps", "philately", "maps")

# Mots d'organe dans les noms de fichiers Commons, toutes langues confondues : ils servent
# à répartir les candidats entre aspects, pas à décider — le tri définitif se fait à l'œil.
MOTS = {
    "fleur": ("flower", "fleur", "blüte", "blute", "bloem", "inflorescen", "umbel",
              "ombelle", "blomma", "kwiat", "flor", "fiore", "bloom", "capitul"),
    "feuille": ("leaf", "leaves", "feuille", "blatt", "blad", "foliage", "liść", "lisc",
                "hoja", "foglia", "rosette", "rosett",
                # chez un conifère, les aiguilles SONT les feuilles
                "needle", "aiguille", "nadel", "acicula"),
    "fruit": ("fruit", "seed", "graine", "frucht", "mericarp", "achene", "akene",
              "samen", "owoc", "semilla", "capsule", "gousse"),
    # L'écorce est l'aspect le plus déficitaire du dépôt et ne concerne que les ligneux.
    # Elle passe avant « port » dans ORDRE : un titre qui dit « trunk » parle du tronc,
    # pas de la silhouette, alors que les deux mots se croisent souvent.
    "ecorce": ("bark", "écorce", "ecorce", "rinde", "corteza", "corteccia", "kora",
               "trunk", "tronc", "stamm", "bole", "schors", "bast", "borke"),
    # Le rameau d'hiver — bourgeons, cicatrices foliaires, moelle — est la seule façon
    # d'identifier un feuillu hors saison, et c'était le dernier aspect qu'aucun lot
    # n'avait visé : faute d'être ici, tout bourgeon tombait dans « divers » et la
    # répartition ne le sortait jamais. Il passe en tête, comme l'écorce au lot 2.
    "rameau": ("twig", "rameau", "ramille", "bourgeon", "knospe", "buds", " bud", "bud-",
               "winter shoot", "winterknospe", "leaf scar", "cicatrice", "moelle", "pith",
               "dormant", "knop", "gemma", "yema", "hiver", "invierno", "winter twig",
               # conifères : c'est le rameau et l'insertion des aiguilles qui déterminent
               "shoot", "branchlet", "sprig", "rameaux", "zweig"),
    "port": ("habit", "plant", "port", "habitus", "whole", "pflanze", "stand",
             "population", "growing", "stem", "tige", "stengel", "silhouette", "arbre",
             "tree", "baum", "shrub", "strauch", "buisson"),
}
ORDRE = ("rameau", "ecorce", "feuille", "fleur", "fruit", "port")

# Mots qui contiennent par accident un mot-clé d'aspect. « Budapest » contient « bud »,
# « Portugal » contient « port » : sans les retirer d'abord, un sureau photographié à
# Budapest passait pour un rameau d'hiver et une vigne photographiée au Portugal pour un
# port. On les gomme du titre avant de chercher les mots-clés.
FAUX_AMIS = ("budapest", "buddleja", "buddleia", "portugal", "porto", "portland",
             "important", "portrait de", "leafless")

# Vocabulaire de RÉPARTITION pour la faune. Ce ne sont PAS des aspects de l'atlas — aucun
# des aspects (feuille, écorce…) ne s'applique à un animal, et les photos de faune entrent
# sans aspect. Ces mots ne servent qu'à éviter de rapporter dix fois le même adulte de
# trois quarts. « jeune » et « degats » passent devant parce que ce sont eux qu'on
# rencontre vraiment : une larve de coccinelle ne ressemble pas à une coccinelle, et d'un
# scolyte on voit les galeries bien avant l'insecte.
MOTS_FAUNE = {
    "jeune": ("larva", "larvae", "larve", "nymph", "nymphe", "caterpillar", "chenille",
              "juvenile", "juvénile", "pupa", "chrysalide", "cocon", "instar", "immature",
              "egg", "oeuf", "œuf", "ponte"),
    "degats": ("damage", "dégât", "degat", "galer", "gallery", "galleries", "mine",
               "infestation", "attack", "frass", "trace", "empreinte", "nid", "nest",
               "toile", "web"),
    "detail": ("head", "tête", "tete", "close-up", "closeup", "macro", "detail", "détail",
               "wing", "aile", "elytra", "élytre", "antenna", "portrait"),
    "action": ("flight", "flying", "vol ", "feeding", "mating", "accouplement", "pollen",
               "foraging", "butin", "hunting", "swimming"),
    "groupe": ("colony", "colonie", "group", "groupe", "swarm", "essaim", "cluster",
               "aggregation", "several", "plusieurs"),
}
ORDRE_FAUNE = ("jeune", "degats", "detail", "action", "groupe")

VOCABULAIRES = {"plante": (ORDRE, MOTS), "faune": (ORDRE_FAUNE, MOTS_FAUNE)}


# ------------------------------------------------------------------- API Commons

def api(**kw):
    kw.setdefault("format", "json")
    kw.setdefault("action", "query")
    req = urllib.request.Request(API + urllib.parse.urlencode(kw), headers={"User-Agent": UA})
    for essai in range(5):
        try:
            with urllib.request.urlopen(req, timeout=40) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(8 + essai * 8)
                continue
            raise
        except (urllib.error.URLError, TimeoutError, OSError):
            # Coupure réseau, DNS qui bafouille, connexion coupée : c'est passager, mais
            # sans ce filet un seul hoquet fait échouer toutes les espèces suivantes du
            # lot, chacune avec un « ÉCHEC » laconique. telecharger() avait déjà son
            # rattrapage ; api() ne l'avait pas, et c'est elle qu'on appelle en premier.
            if essai == 4:
                raise
            time.sleep(3 + essai * 5)
    return {}


def _pages(d):
    return list((d.get("query") or {}).get("pages", {}).values())


def titres_categorie(titre):
    """Tous les noms de fichiers d'une catégorie, continuation comprise.

    On récupère les titres seuls, sans imageinfo : `prop=imageinfo` posé sur un generator
    n'est servi que pour 50 pages, quel que soit gcmlimit. Une catégorie de 200 fichiers
    n'était donc vue que sur sa première tranche alphabétique — d'où des planches de livres
    en tête de liste et des photos de fleurs jamais atteintes.
    """
    titres, cont = [], {}
    while True:
        d = api(list="categorymembers", cmtitle=titre, cmtype="file", cmlimit="500", **cont)
        titres += [m["title"] for m in (d.get("query") or {}).get("categorymembers", [])]
        if "continue" not in d:
            return titres
        cont = d["continue"]


_REDIRECT = re.compile(r"\{\{\s*category redirect\s*\|\s*([^}|]+?)\s*\}\}", re.I)


def redirection_categorie(titre):
    """Cible d'un {{category redirect}} posé sur la catégorie, ou None."""
    d = api(titles=titre, prop="revisions", rvprop="content", rvslots="main")
    pages = list((d.get("query") or {}).get("pages", {}).values())
    revs = (pages[0].get("revisions") if pages else None) or []
    if not revs:
        return None
    txt = ((revs[0].get("slots") or {}).get("main") or {}).get("*") or ""
    m = _REDIRECT.search(txt)
    if not m:
        return None
    cible = m.group(1).strip()
    return cible if cible.lower().startswith("category:") else "Category:" + cible


def titres_categorie_suivie(titre):
    """(titres, catégorie effective), en suivant les {{category redirect}}.

    Une catégorie vide n'est souvent qu'un renvoi vers le synonyme sous lequel les
    fichiers sont réellement classés — Acca sellowiana renvoie à Feijoa sellowiana,
    Mespilus germanica à Crataegus germanica. Sans suivre le renvoi, l'espèce revient
    sans le moindre candidat, et sans le moindre message.
    """
    vus = set()
    for _ in range(3):
        trouves = titres_categorie(titre)
        if trouves or titre in vus:
            return trouves, titre
        vus.add(titre)
        cible = redirection_categorie(titre)
        if not cible:
            return trouves, titre
        titre = cible
    return [], titre


def sous_categories(titre):
    noms = [p["title"] for p in _pages(api(generator="categorymembers", gcmtitle=titre,
                                           gcmtype="subcat", gcmlimit="200"))]
    return [n for n in noms if not any(m in n.lower() for m in SOUS_CAT_REJET)]


def imageinfo_par_lots(titres, largeur):
    """imageinfo de chaque titre, par paquets de 50 (la limite de l'API)."""
    pages = []
    for i in range(0, len(titres), 50):
        pages += _pages(api(titles="|".join(titres[i:i + 50]), prop="imageinfo",
                            iiprop="url|size|user|mime|extmetadata",
                            iiurlwidth=str(largeur_cachee(largeur))))
        time.sleep(0.3)
    return pages


def aspect_devine(titre, ordre=ORDRE, mots=MOTS):
    t = titre.lower()
    for faux in FAUX_AMIS:
        t = t.replace(faux, " ")
    for asp in ordre:
        if any(m in t for m in mots[asp]):
            return asp
    return atlas_data.DIVERS


def titre_utilisable(titre, planches=False):
    """Ce qui se juge sur le seul nom du fichier, avant de payer une requête imageinfo."""
    t = titre.lower()
    if not t.endswith((".jpg", ".jpeg", ".png")) or any(b in t for b in REJET):
        return False
    return planches or not any(b in t for b in REJET_PLANCHES)


def utilisable(page, planches=False):
    if not titre_utilisable(page.get("title", ""), planches):
        return False
    ii = (page.get("imageinfo") or [{}])[0]
    if ii.get("mime") not in ("image/jpeg", "image/png"):
        return False
    if not ii.get("thumburl"):
        return False
    # une image plus petite que la cible n'a pas d'intérêt : la fiche montre l'original
    return (ii.get("width") or ii.get("thumbwidth") or 0) >= 800


def _repartir(pages, n, cle=lambda p: p["title"], vocabulaire="plante"):
    """Round-robin entre thèmes : on veut de la variété, pas dix fleurs de la même plante."""
    ordre, mots = VOCABULAIRES[vocabulaire]
    par_aspect = {}
    for p in pages:
        par_aspect.setdefault(aspect_devine(cle(p), ordre, mots), []).append(p)
    retenus, tour = [], 0
    while len(retenus) < n:
        vide = True
        for asp in ordre + (atlas_data.DIVERS,):
            lot = par_aspect.get(asp) or []
            if tour < len(lot) and len(retenus) < n:
                retenus.append((asp, lot[tour]))
                vide = False
        if vide:
            return retenus
        tour += 1
    return retenus


def candidats(latin, n, largeur, motcle=None, deja=(), categorie=None,
              vocabulaire="plante", planches=False):
    """n pages Commons de l'espèce, réparties entre aspects.

    `categorie` force la catégorie de départ : une entrée d'atlas au nom de genre
    (« Ribes sp. ») ramènerait sinon tout le genre, groseilliers américains compris.
    """
    titres, categorie = titres_categorie_suivie("Category:" + (categorie or latin))
    scs = sous_categories(categorie)
    # Priorité d'exploration. Une sous-catégorie qui nomme un aspect (« (buds) »,
    # « (bark) ») vaut mieux qu'une générique (« Famous … », « by country »). Et quand
    # --planches est posé, les gravures valent mieux qu'une générique aussi — mais PAS
    # mieux qu'un aspect : sans ce rang commun, « - botanical illustrations » prenait la
    # première place et éjectait « buds » des quatre explorées, ce qui a fait rentrer le
    # lot 8 sans un seul rameau de charme.
    _ordre, _mots = VOCABULAIRES[vocabulaire]
    _kw = tuple(m for asp in _ordre for m in _mots[asp])

    def _rang(c):
        bas = c.lower()
        if any(m in bas for m in _kw):
            return 0
        if planches and "illustration" in bas:
            return 1
        return 2

    scs.sort(key=_rang)
    for sc in scs[:SOUS_CATS]:
        time.sleep(0.4)
        titres += titres_categorie(sc)
    vus = set(deja)
    titres = [t for t in titres if titre_utilisable(t, planches) and not (t in vus or vus.add(t))]
    if motcle:
        titres = [t for t in titres if motcle.lower() in t.lower()]

    # Un fichier qui nomme l'espèce dans son titre a été versé là exprès ; un titre vague
    # (« Autumn flowers 01 ») n'y est peut-être que par ricochet. On garde les deux, mais
    # les premiers passent devant.
    genre, _, espece = latin.partition(" ")
    titres.sort(key=lambda t: (0 if espece and espece.lower() in t.lower()
                               else 1 if genre.lower() in t.lower() else 2))

    # On ne paie l'imageinfo que d'une présélection large : certaines seront écartées
    # ensuite (image trop petite, mime inattendu), d'où la marge.
    presel = [t for _asp, t in _repartir(titres, n * 4, cle=lambda t: t,
                                         vocabulaire=vocabulaire)]
    pages = [p for p in imageinfo_par_lots(presel, largeur) if utilisable(p, planches)]
    rang = {t: i for i, t in enumerate(presel)}
    pages.sort(key=lambda p: rang.get(p["title"], 999))
    return _repartir(pages, n, vocabulaire=vocabulaire)


# --------------------------------------------------------------- téléchargement

def telecharger(url, dest, largeur):
    """Télécharge et réduit, en réessayant : un 429 ou une panne de résolution passagère
    ne doit pas faire perdre le candidat (dix espèces d'affilée ont été perdues ainsi)."""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    buf = None
    for essai in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                buf = r.read()
            break
        except urllib.error.HTTPError as e:
            if e.code not in (429, 503) or essai == 3:
                raise
            time.sleep(10 + essai * 20)
        except urllib.error.URLError:
            if essai == 3:
                raise
            time.sleep(10 + essai * 20)
    if buf is None or len(buf) < 1500:
        raise IOError("fichier trop petit")
    images.reduire(buf, dest, largeur)


def recolter(especes, n, largeur, motcle=None, categorie=None, vocabulaire="plante",
             planches=False):
    """Complète candidats/<stem>/ sans rien écraser : la numérotation reprend où elle en
    est et candidats.tsv s'allonge. On peut donc revenir combler un aspect manquant
    (--motcle flower) sans perdre les choix déjà faits sur les candidats précédents."""
    for i, (stem, latin) in enumerate(especes, 1):
        dossier = os.path.join(DEST, stem)
        os.makedirs(dossier, exist_ok=True)
        tsv = os.path.join(dossier, "candidats.tsv")
        anciennes = []
        if os.path.exists(tsv):
            anciennes = [l.rstrip("\n").split("\t") for l in open(tsv, encoding="utf-8")][1:]
        deja = {l[2] for l in anciennes if len(l) > 2}
        # le plus grand numéro déjà pris, pas le nombre de fichiers : un téléchargement
        # raté laisse un trou dans la numérotation, et repartir du compte écraserait
        # un candidat existant
        numeros = [int(f[:-4]) for f in os.listdir(dossier)
                   if f.endswith(".jpg") and f[:-4].isdigit()]
        k = max(numeros) if numeros else 0
        lignes, ajoutes = [], 0
        try:
            trouves = candidats(latin, n, largeur, motcle, deja, categorie, vocabulaire,
                                planches)
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
                k -= 1
                continue
            c = credits.credit_commons(ii)
            lignes.append("\t".join([nom, asp, page["title"], c["auteur"], c["licence"], c["url"]]))
            ajoutes += 1
            time.sleep(0.4)
        with open(tsv, "w", encoding="utf-8") as fh:
            fh.write("fichier\taspect_devine\ttitre_commons\tauteur\tlicence\turl\n")
            for l in anciennes:
                fh.write("\t".join(l) + "\n")
            fh.write("\n".join(lignes) + ("\n" if lignes else ""))
        print("[%d/%d] %-12s (%s) : +%d candidat(s), %d au total"
              % (i, len(especes), stem, latin, ajoutes, len(anciennes) + ajoutes))
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
        # un nom simple va dans img/quiz-extra/ ; un chemin avec « / » va où il dit,
        # ce qui permet de remplacer aussi une vignette de img/especes/
        dest = os.path.join(BASE, final) if "/" in final else os.path.join(EXTRA, final)
        octets = open(src, "rb").read()
        # Rejouer le même fichier de choix doit être sans effet ; en revanche écraser une
        # AUTRE photo déjà versée se voit mal dans un dossier de 300 fichiers, et on
        # l'exige explicitement plutôt que de le faire en silence.
        if os.path.exists(dest) and open(dest, "rb").read() != octets:
            if "--remplacer" not in sys.argv:
                raise SystemExit(
                    "%s existe déjà avec un autre contenu — choisissez un autre numéro, "
                    "ou --remplacer si c'est voulu" % os.path.relpath(dest, BASE))
        with open(dest, "wb") as b:
            b.write(octets)
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
    motcle = categorie = None
    for i, a in enumerate(argv):
        if a == "--motcle" and i + 1 < len(argv):
            motcle = argv[i + 1]
        if a == "--categorie" and i + 1 < len(argv):
            categorie = argv[i + 1]
    vocabulaire = "faune" if "--faune" in argv else "plante"
    planches = "--planches" in argv
    especes = [(s, latin_court(l)) for s, l in especes_du_lot(argv)]
    print("%d espèce(s), jusqu'à %d candidats chacune%s → candidats/"
          % (len(especes), n, (" (titres contenant « %s »)" % motcle) if motcle else ""))
    recolter(especes, n, images.largeur_demandee(argv), motcle, categorie, vocabulaire,
             planches)


if __name__ == "__main__":
    main()
