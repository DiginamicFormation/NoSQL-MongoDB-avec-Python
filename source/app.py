"""Catalogue MongoDB - interface en ligne de commande (étape 13).

    python app.py init [--strict]
    python app.py seed
    python app.py list [--categorie clavier] [--max-prix 150]
                       [--taille 20] [--apres <_id>]
    python app.py show KBD-0010
    python app.py add SKU NOM CATEGORIE PRIX [--stock N]
    python app.py set KBD-0010 nom "Nouveau nom"
    python app.py reserve KBD-0010 2
    python app.py delete KBD-0010 [--hard]
    python app.py audit
    python app.py stats
"""
import argparse
import sys

from bson import Decimal128, ObjectId

from db import get_db
from provision import provisionner
from repository import CatalogueRepository, ErreurCatalogue

# Un catalogue volontairement HÉTÉROGÈNE : chaque famille a ses propres champs,
# et l'abonnement n'a pas de stock du tout.
CATALOGUE_DEMO = [
    {"sku": "KBD-0010", "nom": "Clavier TKL silencieux", "categorie": "clavier",
     "prix": Decimal128("119.00"), "stock": 8, "tags": ["clavier", "silencieux"],
     "switches": "marron", "retroeclairage": True},

    {"sku": "KBD-0020", "nom": "Clavier 60% RGB", "categorie": "clavier",
     "prix": Decimal128("89.90"), "stock": 12, "tags": ["clavier", "rgb"],
     "switches": "rouge", "retroeclairage": True},

    {"sku": "SCR-0011", "nom": "Ecran 24 pouces", "categorie": "ecran",
     "prix": Decimal128("179.00"), "stock": 15,
     "pouces": 24, "resolution": "1920x1080", "hz": 75},

    {"sku": "SCR-0021", "nom": "Ecran 27 pouces QHD", "categorie": "ecran",
     "prix": Decimal128("349.00"), "stock": 4,
     "pouces": 27, "resolution": "2560x1440", "hz": 144},

    {"sku": "LIV-0014", "nom": "MongoDB en pratique", "categorie": "livre",
     "prix": Decimal128("42.00"), "stock": 30,
     "auteur": "K. Chodorow", "isbn": "978-1491954461", "pages": 514},

    {"sku": "ABO-0013", "nom": "Support Pro mensuel", "categorie": "abonnement",
     "prix": Decimal128("19.00"),
     "periodicite": "mensuelle", "renouvellement_auto": True},
]


# `set` recoit toujours des chaines : sans conversion, `set SKU prix 79.90`
# remplacerait un Decimal128 par une string et le produit sortirait des
# filtres numeriques (`--max-prix`). On convertit les champs du noyau typé.
CONVERSIONS = {
    "prix": lambda v: Decimal128(str(v)),
    "stock": int,
    "schema_version": int,
    "tags": lambda v: [t.strip() for t in v.split(",") if t.strip()],
}


def convertir(champ: str, valeur: str):
    try:
        return CONVERSIONS.get(champ, lambda v: v)(valeur)
    except Exception as exc:                 # noqa: BLE001 - message utilisateur
        raise SystemExit(f"valeur invalide pour {champ} : {valeur!r} ({exc})")


def construire_parseur() -> argparse.ArgumentParser:
    parseur = argparse.ArgumentParser(description="Catalogue MongoDB")
    sous = parseur.add_subparsers(dest="commande", required=True)

    p = sous.add_parser("init", help="validation + index (réexécutable)")
    p.add_argument("--strict", action="store_true",
                   help="validationLevel=strict + validationAction=error")
    sous.add_parser("seed", help="charge le catalogue de démonstration")
    sous.add_parser("audit", help="champs réellement présents et leurs types")
    sous.add_parser("stats", help="chiffres par catégorie")

    p = sous.add_parser("list", help="liste paginée")
    p.add_argument("--categorie")
    p.add_argument("--max-prix", dest="max_prix")
    p.add_argument("--taille", type=int, default=20)
    p.add_argument("--apres", help="_id du dernier produit de la page précédente")

    p = sous.add_parser("show", help="fiche complète")
    p.add_argument("sku")

    p = sous.add_parser("add", help="ajoute un produit")
    for argument in ("sku", "nom", "categorie", "prix"):
        p.add_argument(argument)
    p.add_argument("--stock", type=int)

    p = sous.add_parser("set", help="modifie un champ")
    p.add_argument("sku")
    p.add_argument("champ")
    p.add_argument("valeur")

    p = sous.add_parser("reserve", help="décrémente le stock atomiquement")
    p.add_argument("sku")
    p.add_argument("n", type=int)

    p = sous.add_parser("delete", help="suppression logique (--hard : définitive)")
    p.add_argument("sku")
    p.add_argument("--hard", action="store_true")

    return parseur


def main() -> int:
    args = construire_parseur().parse_args()
    depot = CatalogueRepository(get_db())

    try:
        if args.commande == "init":
            provisionner(strict=args.strict)   # moderate/warn par défaut : étape 10
            depot.initialiser()
            print("collection initialisée")

        elif args.commande == "seed":
            crees, majs = depot.importer(CATALOGUE_DEMO)
            print(f"{crees} créés, {majs} mis à jour - {depot.compter()} produits au total")

        elif args.commande == "list":
            apres = ObjectId(args.apres) if args.apres else None
            produits = depot.lister(args.categorie, args.max_prix, apres, args.taille)
            if not produits:
                print("aucun produit")
            for produit in produits:
                stock = produit.get("stock", "-")        # champ optionnel !
                print(f"{produit['sku']:<12}{produit['nom']:<32}"
                      f"{str(produit['prix']):>9} EUR   stock {stock}")
            if len(produits) == args.taille:
                print(f"... page suivante : --apres {produits[-1]['_id']}")

        elif args.commande == "show":
            commun, specifique = depot.decouper(depot.par_sku(args.sku))
            largeur = max(len(c) for c in (*commun, *specifique))
            for cle, valeur in commun.items():
                print(f"{cle:<{largeur}} : {valeur}")
            if specifique:
                print("--- spécifique à la famille ---")
                for cle, valeur in specifique.items():
                    print(f"{cle:<{largeur}} : {valeur}")

        elif args.commande == "add":
            depot.creer(args.sku, args.nom, args.categorie, args.prix, args.stock)
            print("créé")

        elif args.commande == "set":
            change = depot.modifier(args.sku, {args.champ: convertir(args.champ, args.valeur)})
            print("modifié" if change else "aucun changement (valeur identique)")

        elif args.commande == "reserve":
            print("stock restant :", depot.reserver(args.sku, args.n)["stock"])

        elif args.commande == "delete":
            if args.hard:
                depot.supprimer_definitivement(args.sku)
                print("supprimé définitivement")
            else:
                depot.supprimer(args.sku)
                print("mis en corbeille (purge automatique dans 30 jours)")

        elif args.commande == "audit":
            # auditer() balaie TOUTE la collection : le total doit inclure
            # la corbeille, sinon la presence depasse 100 %.
            total = max(depot.compter(inclure_supprimes=True), 1)
            print(f"{'champ':<20}{'présence':>9}  types")
            print("-" * 56)
            for ligne in depot.auditer():
                alerte = "  <-- plusieurs types" if len(ligne["types"]) > 1 else ""
                print(f"{ligne['_id']:<20}{100 * ligne['presents'] // total:>8}%  "
                      f"{', '.join(sorted(ligne['types']))}{alerte}")

        elif args.commande == "stats":
            for ligne in depot.statistiques():
                print(f"{ligne['_id']:<14}{ligne['nombre']:>3} produits   "
                      f"prix moyen {ligne['prix_moyen']:>8.2f} EUR   "
                      f"stock {ligne['stock_total']:>4}   "
                      f"(sans champ stock : {ligne['sans_stock']})")

    except ErreurCatalogue as exc:
        print(f"erreur : {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
