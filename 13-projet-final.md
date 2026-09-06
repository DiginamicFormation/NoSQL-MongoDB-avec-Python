[← Étape 12](12-index-et-performances.md) · [Sommaire](README.md) · [Étape suivante →](14-annexes.md)

# Étape 13 - Projet final : une application CRUD complète

> 🎯 **Objectif** : rassembler tout le cours dans une petite application propre, testée, qui gère un catalogue hétérogène.
> ⏱️ **Durée** : 2 heures.
> 📁 **On crée** : `boutique/repository.py`, `boutique/app.py`, `boutique/test_repository.py`.
> 📦 **Corrigé complet** : dossier [`source/`](source/).

---

## 13.1 Le cahier des charges

Une application en ligne de commande qui gère le catalogue de la boutique :

| Commande | Comportement attendu |
|---|---|
| `python app.py init` | crée la collection, sa validation et ses index (réexécutable) |
| `python app.py seed` | charge le catalogue de démonstration (réexécutable) |
| `python app.py list [--categorie X] [--max-prix N]` | liste les produits, paginée |
| `python app.py show SKU` | affiche une fiche complète, **quelle que soit la forme du document** |
| `python app.py add SKU NOM CATEGORIE PRIX [--stock N]` | ajoute un produit |
| `python app.py set SKU CHAMP VALEUR` | modifie un champ |
| `python app.py reserve SKU N` | décrémente le stock atomiquement |
| `python app.py delete SKU [--hard]` | suppression logique par défaut, définitive avec `--hard` |
| `python app.py audit` | inventaire des champs et de leurs types |
| `python app.py stats` | chiffres par catégorie (agrégation) |

Les contraintes, qui reprennent tout ce que vous avez appris :

1. **un seul `MongoClient`** dans tout le programme ;
2. **toutes** les opérations MongoDB dans `repository.py` - aucune requête ailleurs ;
3. les prix en `Decimal128`, les dates *aware* en UTC ;
4. le code de lecture ne suppose **jamais** qu'un champ optionnel existe ;
5. les erreurs MongoDB sont traduites en exceptions métier ;
6. `init` et `seed` sont réexécutables sans effet de bord.

---

## 13.2 L'architecture

```
boutique/
├── compose.yaml          # étape 03
├── .env                  # étape 05  (dans .gitignore)
├── db.py                 # étape 05 - la connexion, et rien d'autre
├── provision.py          # étape 10 - validation + index
├── repository.py         # ⇦ le cœur : toutes les requêtes
├── app.py                # ⇦ l'interface en ligne de commande
└── test_repository.py    # ⇦ les tests
```

**Pourquoi un dépôt (*repository*) ?** Parce que c'est le seul moyen de tenir les règles 2, 4 et 5 dans la durée. Le jour où vous ajoutez la suppression logique, vous avez **un seul** endroit où ajouter `{"supprime_le": {"$exists": False}}` à toutes les lectures. Une application qui éparpille ses `find` dans les vues finit toujours par en oublier un.

---

## 13.3 Le dépôt

```python
# repository.py
"""Toutes les opérations MongoDB de l'application, et elles seules."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterator

from bson import Decimal128, ObjectId
from bson.errors import InvalidId
from pymongo import ASCENDING, DESCENDING, IndexModel, ReturnDocument, UpdateOne
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError, WriteError

VERSION_SCHEMA = 1

# Les champs du noyau commun : tout le reste est spécifique à une famille.
CHAMPS_COMMUNS = {"_id", "sku", "nom", "categorie", "prix", "stock", "tags",
                  "cree_le", "maj_le", "supprime_le", "schema_version"}


class ErreurCatalogue(Exception):
    """Classe mère des erreurs métier du catalogue."""


class ProduitIntrouvable(ErreurCatalogue):
    pass


class ProduitDejaExistant(ErreurCatalogue):
    pass


class DocumentInvalide(ErreurCatalogue):
    pass


class StockInsuffisant(ErreurCatalogue):
    pass


class CatalogueRepository:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.col = db["produits"]

    # ------------------------------------------------------------------ setup
    def initialiser(self) -> None:
        """Crée index et validation. Réexécutable."""
        self.col.create_indexes([
            IndexModel([("sku", ASCENDING)], unique=True, name="uniq_sku"),
            IndexModel([("categorie", ASCENDING), ("prix", DESCENDING)], name="cat_prix"),
            IndexModel([("tags", ASCENDING)], name="tags"),
            IndexModel([("supprime_le", ASCENDING)], name="ttl_corbeille",
                       expireAfterSeconds=30 * 24 * 3600,
                       partialFilterExpression={"supprime_le": {"$type": "date"}}),
        ])

    # ----------------------------------------------------------------- create
    def creer(self, sku: str, nom: str, categorie: str, prix: str,
              stock: int | None = None, **specifiques: Any) -> ObjectId:
        document = {
            "sku": sku,
            "nom": nom,
            "categorie": categorie,
            "prix": Decimal128(prix),
            "cree_le": datetime.now(timezone.utc),
            "schema_version": VERSION_SCHEMA,
            **specifiques,                       # les champs propres à la famille
        }
        if stock is not None:                    # absent = "non géré en stock"
            document["stock"] = int(stock)
        try:
            return self.col.insert_one(document).inserted_id
        except DuplicateKeyError as exc:
            raise ProduitDejaExistant(f"le SKU {sku} existe déjà") from exc
        except WriteError as exc:
            raise DocumentInvalide(str(exc.details.get("errInfo", exc))) from exc

    def importer(self, catalogue: list[dict[str, Any]]) -> tuple[int, int]:
        """Import réexécutable : crée ce qui manque, met à jour le reste."""
        if not catalogue:
            return (0, 0)
        maintenant = datetime.now(timezone.utc)
        resultat = self.col.bulk_write([
            UpdateOne(
                {"sku": produit["sku"]},
                {"$set": {**produit, "schema_version": VERSION_SCHEMA},
                 "$setOnInsert": {"cree_le": maintenant}},
                upsert=True,
            )
            for produit in catalogue
        ], ordered=False)
        return (resultat.upserted_count, resultat.modified_count)

    # ------------------------------------------------------------------- read
    def par_sku(self, sku: str, inclure_supprimes: bool = False) -> dict[str, Any]:
        filtre: dict[str, Any] = {"sku": sku}
        if not inclure_supprimes:
            filtre["supprime_le"] = {"$exists": False}
        document = self.col.find_one(filtre)
        if document is None:
            raise ProduitIntrouvable(sku)
        return document

    def par_id(self, identifiant: str) -> dict[str, Any]:
        try:
            oid = ObjectId(identifiant)
        except InvalidId as exc:
            raise ProduitIntrouvable(identifiant) from exc
        document = self.col.find_one({"_id": oid, "supprime_le": {"$exists": False}})
        if document is None:
            raise ProduitIntrouvable(identifiant)
        return document

    def lister(self, categorie: str | None = None, prix_max: str | None = None,
               apres: ObjectId | None = None, taille: int = 20) -> list[dict[str, Any]]:
        filtre: dict[str, Any] = {"supprime_le": {"$exists": False}}
        if categorie:
            filtre["categorie"] = categorie
        if prix_max:
            filtre["prix"] = {"$lte": Decimal128(prix_max)}
        if apres:                                     # pagination par curseur
            filtre["_id"] = {"$gt": apres}
        return list(
            self.col.find(filtre, {"sku": 1, "nom": 1, "prix": 1, "stock": 1, "categorie": 1})
                    .sort("_id", ASCENDING)
                    .limit(taille)
        )

    def compter(self, categorie: str | None = None) -> int:
        filtre: dict[str, Any] = {"supprime_le": {"$exists": False}}
        if categorie:
            filtre["categorie"] = categorie
        return self.col.count_documents(filtre)

    # ----------------------------------------------------------------- update
    def modifier(self, sku: str, champs: dict[str, Any]) -> bool:
        interdits = [c for c in champs if c.startswith("$") or "." in c or c == "_id"]
        if interdits:
            raise DocumentInvalide(f"champs interdits : {interdits}")
        resultat = self.col.update_one(
            {"sku": sku, "supprime_le": {"$exists": False}},
            {"$set": champs, "$currentDate": {"maj_le": True}},
        )
        if resultat.matched_count == 0:
            raise ProduitIntrouvable(sku)
        return resultat.modified_count == 1

    def reserver(self, sku: str, quantite: int) -> dict[str, Any]:
        """Décrémente le stock atomiquement, jamais en dessous de zéro."""
        document = self.col.find_one_and_update(
            {"sku": sku, "stock": {"$gte": quantite}, "supprime_le": {"$exists": False}},
            {"$inc": {"stock": -quantite}, "$currentDate": {"maj_le": True}},
            return_document=ReturnDocument.AFTER,
        )
        if document is None:
            self.par_sku(sku)          # lève ProduitIntrouvable si c'est la vraie cause
            raise StockInsuffisant(f"{sku} : stock insuffisant ou non géré en stock")
        return document

    # ----------------------------------------------------------------- delete
    def supprimer(self, sku: str) -> None:
        """Suppression logique : le document part en corbeille (purge TTL à 30 jours)."""
        resultat = self.col.update_one(
            {"sku": sku, "supprime_le": {"$exists": False}},
            {"$set": {"supprime_le": datetime.now(timezone.utc)}},
        )
        if resultat.matched_count == 0:
            raise ProduitIntrouvable(sku)

    def supprimer_definitivement(self, sku: str) -> None:
        if self.col.delete_one({"sku": sku}).deleted_count == 0:
            raise ProduitIntrouvable(sku)

    # ------------------------------------------------- lecture "hétérogène"
    @staticmethod
    def decouper(document: dict[str, Any]) -> tuple[dict, dict]:
        """Sépare le noyau commun des champs spécifiques à la famille."""
        commun = {k: v for k, v in document.items() if k in CHAMPS_COMMUNS}
        specifique = {k: v for k, v in document.items() if k not in CHAMPS_COMMUNS}
        return commun, specifique

    def auditer(self) -> Iterator[dict[str, Any]]:
        """Présence et types réels de chaque champ (étape 10)."""
        return self.col.aggregate([
            {"$project": {"champs": {"$objectToArray": "$$ROOT"}}},
            {"$unwind": "$champs"},
            {"$group": {"_id": "$champs.k",
                        "presents": {"$sum": 1},
                        "types": {"$addToSet": {"$type": "$champs.v"}}}},
            {"$sort": {"presents": -1}},
        ])

    def statistiques(self) -> Iterator[dict[str, Any]]:
        """Chiffres par catégorie - tolérant aux champs absents."""
        return self.col.aggregate([
            {"$match": {"supprime_le": {"$exists": False}}},
            {"$group": {
                "_id": "$categorie",
                "nombre": {"$sum": 1},
                "prix_moyen": {"$avg": {"$toDouble": "$prix"}},
                "stock_total": {"$sum": {"$ifNull": ["$stock", 0]}},   # 👈 champ optionnel
                "sans_stock": {"$sum": {"$cond": [{"$eq": [{"$type": "$stock"}, "missing"]}, 1, 0]}},
            }},
            {"$sort": {"nombre": -1}},
        ])
```

### Les six points à comprendre dans ce code

1. **Les exceptions métier** (`ProduitIntrouvable`, `StockInsuffisant`…) : l'appelant n'a jamais à connaître `DuplicateKeyError` ni le code 11000. Le jour où vous changez de base, seule cette couche est à réécrire.
2. **La suppression logique est appliquée dans le dépôt**, une fois pour toutes : impossible d'oublier le filtre dans une vue.
3. **`stock` absent ≠ `stock: 0`** - la convention choisie à l'étape 10 est tenue de bout en bout, jusque dans `statistiques()` qui compte les deux séparément.
4. **`reserver` fait une seconde requête uniquement en cas d'échec**, pour distinguer "produit inconnu" de "stock insuffisant". Jamais avant : ce serait rouvrir la fenêtre de concurrence.
5. **`modifier` refuse les clés contenant `$` ou `.`** - c'est la protection contre l'injection d'opérateurs quand les champs viennent d'un formulaire.
6. **L'index TTL est partiel** : il ne s'applique qu'aux documents ayant réellement une date dans `supprime_le`.

---

## 13.4 L'interface en ligne de commande

```python
# app.py
import argparse
import sys

from bson import Decimal128

from db import get_db
from repository import CatalogueRepository, ErreurCatalogue

CATALOGUE_DEMO = [
    {"sku": "KBD-0010", "nom": "Clavier TKL silencieux", "categorie": "clavier",
     "prix": Decimal128("119.00"), "stock": 8, "tags": ["clavier"], "switches": "marron"},
    {"sku": "SCR-0011", "nom": "Ecran 24 pouces", "categorie": "ecran",
     "prix": Decimal128("179.00"), "stock": 15, "pouces": 24, "resolution": "1920x1080"},
    {"sku": "LIV-0014", "nom": "MongoDB en pratique", "categorie": "livre",
     "prix": Decimal128("42.00"), "stock": 30, "auteur": "K. Chodorow", "pages": 514},
    {"sku": "ABO-0013", "nom": "Support Pro mensuel", "categorie": "abonnement",
     "prix": Decimal128("19.00"), "periodicite": "mensuelle"},      # pas de stock
]


def main() -> int:
    parseur = argparse.ArgumentParser(description="Catalogue MongoDB")
    sous = parseur.add_subparsers(dest="commande", required=True)

    sous.add_parser("init")
    sous.add_parser("seed")
    sous.add_parser("audit")
    sous.add_parser("stats")

    p = sous.add_parser("list")
    p.add_argument("--categorie")
    p.add_argument("--max-prix")

    p = sous.add_parser("show");     p.add_argument("sku")
    p = sous.add_parser("reserve");  p.add_argument("sku"); p.add_argument("n", type=int)
    p = sous.add_parser("delete");   p.add_argument("sku"); p.add_argument("--hard", action="store_true")
    p = sous.add_parser("set");      p.add_argument("sku"); p.add_argument("champ"); p.add_argument("valeur")
    p = sous.add_parser("add")
    for arg in ("sku", "nom", "categorie", "prix"):
        p.add_argument(arg)
    p.add_argument("--stock", type=int)

    args = parseur.parse_args()
    depot = CatalogueRepository(get_db())

    try:
        if args.commande == "init":
            depot.initialiser()
            print("collection initialisée")

        elif args.commande == "seed":
            crees, majs = depot.importer(CATALOGUE_DEMO)
            print(f"{crees} créés, {majs} mis à jour, {depot.compter()} au total")

        elif args.commande == "list":
            for produit in depot.lister(args.categorie, args.max_prix):
                stock = produit.get("stock", "-")          # 👈 champ optionnel
                print(f"{produit['sku']:<12}{produit['nom']:<32}"
                      f"{str(produit['prix']):>9} €  stock {stock}")

        elif args.commande == "show":
            commun, specifique = depot.decouper(depot.par_sku(args.sku))
            for cle, valeur in commun.items():
                print(f"{cle:<16}: {valeur}")
            if specifique:
                print("--- spécifique à la famille ---")
                for cle, valeur in specifique.items():
                    print(f"{cle:<16}: {valeur}")

        elif args.commande == "add":
            depot.creer(args.sku, args.nom, args.categorie, args.prix, args.stock)
            print("créé")

        elif args.commande == "set":
            depot.modifier(args.sku, {args.champ: args.valeur})
            print("modifié")

        elif args.commande == "reserve":
            print("stock restant :", depot.reserver(args.sku, args.n)["stock"])

        elif args.commande == "delete":
            (depot.supprimer_definitivement if args.hard else depot.supprimer)(args.sku)
            print("supprimé")

        elif args.commande == "audit":
            total = depot.compter()
            for ligne in depot.auditer():
                alerte = " ⚠️" if len(ligne["types"]) > 1 else ""
                print(f"{ligne['_id']:<20}{100 * ligne['presents'] // max(total, 1):>4}%  "
                      f"{', '.join(sorted(ligne['types']))}{alerte}")

        elif args.commande == "stats":
            for ligne in depot.statistiques():
                print(f"{ligne['_id']:<14} {ligne['nombre']:>3} produits  "
                      f"prix moyen {ligne['prix_moyen']:>8.2f} €  "
                      f"stock {ligne['stock_total']:>4}  (sans stock : {ligne['sans_stock']})")

    except ErreurCatalogue as exc:
        print(f"erreur : {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

```bash
python app.py init
python app.py seed
python app.py list --categorie clavier
python app.py show ABO-0013
python app.py reserve KBD-0010 2
python app.py audit
python app.py stats
```

---

## 13.5 Les tests

```python
# test_repository.py
import pytest
from bson import Decimal128

from db import get_client
from repository import (CatalogueRepository, ProduitDejaExistant,
                        ProduitIntrouvable, StockInsuffisant)


@pytest.fixture
def depot():
    """Une base jetable par test : simple, rapide, isolé."""
    client = get_client()
    base = client["boutique_test"]
    depot = CatalogueRepository(base)
    depot.initialiser()
    yield depot
    client.drop_database("boutique_test")


def test_creer_puis_lire(depot):
    depot.creer("KBD-0001", "Clavier", "clavier", "99.00", stock=5)
    assert depot.par_sku("KBD-0001")["nom"] == "Clavier"


def test_sku_unique(depot):
    depot.creer("KBD-0001", "Clavier", "clavier", "99.00")
    with pytest.raises(ProduitDejaExistant):
        depot.creer("KBD-0001", "Autre", "clavier", "50.00")


def test_produit_sans_stock(depot):
    """Un abonnement n'a pas de champ stock : la lecture ne doit pas casser."""
    depot.creer("ABO-0001", "Support", "abonnement", "19.00", periodicite="mensuelle")
    document = depot.par_sku("ABO-0001")
    assert "stock" not in document
    assert document.get("stock") is None
    with pytest.raises(StockInsuffisant):
        depot.reserver("ABO-0001", 1)


def test_reservation_atomique(depot):
    depot.creer("KBD-0001", "Clavier", "clavier", "99.00", stock=3)
    assert depot.reserver("KBD-0001", 2)["stock"] == 1
    with pytest.raises(StockInsuffisant):
        depot.reserver("KBD-0001", 2)          # il n'en reste qu'un


def test_suppression_logique(depot):
    depot.creer("KBD-0001", "Clavier", "clavier", "99.00")
    depot.supprimer("KBD-0001")
    with pytest.raises(ProduitIntrouvable):
        depot.par_sku("KBD-0001")
    assert depot.par_sku("KBD-0001", inclure_supprimes=True)["sku"] == "KBD-0001"


def test_import_reexecutable(depot):
    catalogue = [{"sku": "A-0001", "nom": "A", "categorie": "livre",
                  "prix": Decimal128("10.00")}]
    assert depot.importer(catalogue) == (1, 0)      # créé
    depot.importer(catalogue)                        # relancé : aucun doublon
    assert depot.compter() == 1
```

```bash
pip install pytest
pytest -v
```

> **Autre approche, plus proche de la production** : `testcontainers` démarre un vrai MongoDB éphémère par session de tests.
> ```python
> from testcontainers.mongodb import MongoDbContainer
> with MongoDbContainer("mongo:8.0") as mongo:
>     client = MongoClient(mongo.get_connection_url())
> ```
> Évitez `mongomock` comme unique filet : la simulation en mémoire ne reproduit pas fidèlement les agrégations.

---

## 13.6 Pour aller plus loin

Trois sujets que le CRUD ne couvre pas, à connaître de nom - et à explorer quand le besoin se présente.

### L'agrégation

Vous l'avez déjà utilisée deux fois (`auditer`, `statistiques`). Un pipeline est une suite d'étapes, chacune transformant le flux de documents de la précédente. C'est l'équivalent de `GROUP BY … HAVING … JOIN`, en plus expressif.

```python
db.commandes.aggregate([
    {"$match": {"statut": "payee"}},                    # ① filtrer AU PLUS TÔT
    {"$unwind": "$lignes"},                             # ② un document par ligne
    {"$group": {"_id": "$lignes.sku",
                "unites": {"$sum": "$lignes.quantite"},
                "ca": {"$sum": {"$multiply": [{"$toDouble": "$lignes.prix_unitaire"},
                                              "$lignes.quantite"]}}}},
    {"$sort": {"ca": -1}}, {"$limit": 10},
])
```

Les étapes principales : `$match`, `$project` / `$set`, `$group`, `$sort`, `$limit`, `$unwind`, `$lookup`, `$facet`, `$count`, `$out` / `$merge`. Deux règles : **`$match` et `$sort` en tête** (pour utiliser les index), et projetez tôt pour réduire le volume transporté.

### Les transactions

Nécessitent un **replica set** (§ 3.3). Elles permettent d'écrire dans plusieurs documents ou collections de façon atomique.

```python
with client.start_session() as session:
    session.with_transaction(lambda s: (
        db.produits.update_one({"sku": sku}, {"$inc": {"stock": -1}}, session=s),
        db.commandes.insert_one({"sku": sku}, session=s),
    ))
```

Trois pièges : le callback peut être **rejoué** (il doit être idempotent et sans effet de bord externe), `session=` doit être passé à **toutes** les opérations, et la durée est limitée à 60 secondes par défaut. Si votre application a besoin de transactions partout, c'est généralement le signe qu'il fallait regrouper les données dans un même document.

### Les change streams

Un flux temps réel des modifications, également réservé aux replica sets.

```python
with db.produits.watch([{"$match": {"operationType": "update"}}]) as flux:
    for evenement in flux:
        invalider_cache(evenement["documentKey"]["_id"])
```

Usages : synchroniser un cache ou un index de recherche, notifier, propager une dénormalisation (§ 11.5).

### L'asynchrone

`AsyncMongoClient` est intégré à PyMongo - l'API est identique, avec `await` et `async for`. Motor, l'ancien driver asynchrone, est en fin de vie : ne démarrez plus rien avec.

```python
from pymongo import AsyncMongoClient

client = AsyncMongoClient(uri)
doc = await client.boutique.produits.find_one({"sku": "KBD-0010"})
async for produit in client.boutique.produits.find({"stock": {"$gt": 0}}):
    ...
await client.aclose()
```

---

## 13.7 Auto-évaluation

Répondez sans regarder, puis vérifiez.

1. Quelle est la différence entre `matched_count` et `modified_count` ?
2. `{"remise": None}` - quels documents cette requête retourne-t-elle exactement ?
3. Pourquoi `find({"prix": {"$lt": 100}})` peut-elle "oublier" des produits ?
4. Un index `{a: 1, b: 1, c: 1}` sert-il une requête portant seulement sur `b` ?
5. Pourquoi ne pas vérifier le stock avec un `find_one` avant de le décrémenter ?
6. Que se passe-t-il si vous faites `replace_one` avec un document auquel il manque des champs ?
7. Comment rendre un index unique sur un champ que seuls certains documents possèdent ?
8. Quel est le risque d'un `bulk_write(ordered=False)` qui lève `BulkWriteError` ?
9. Pourquoi imbriquer les lignes d'une commande, mais pas les commandes d'un client ?
10. Quelle est la première chose à faire avant de coder sur une collection existante ?

<details>
<summary>Voir les réponses</summary>

1. `matched_count` = le filtre a trouvé le document ; `modified_count` = quelque chose a réellement changé. Un document déjà à jour donne 1 et 0. Pour un "introuvable", testez `matched_count`. *(Étape 08)*
2. Ceux où `remise` vaut `null` **et** ceux où le champ est **absent**. Pour distinguer : `$exists` et `$type: "null"`. *(Étapes 04 et 10)*
3. Parce qu'un document dont le prix est stocké dans un type non numérique (une chaîne) est **silencieusement ignoré** : BSON ne compare pas une chaîne à un nombre. *(Étapes 07 et 10)*
4. Non. Règle du préfixe : il sert `{a}`, `{a,b}`, `{a,b,c}` - jamais `{b}` seul. *(Étape 12)*
5. Parce que deux processus peuvent lire "stock suffisant" en même temps et décrémenter tous les deux. Il faut mettre la condition **dans le filtre** de `find_one_and_update`. *(Étape 08)*
6. Les champs absents du nouveau document sont **supprimés** : `replace_one` est un `PUT`, pas un `PATCH`. Et si vous avez relu le document avant, vous risquez d'écraser les modifications d'un autre (*lost update*). *(Étape 08)*
7. Avec un **index partiel** : `unique=True` + `partialFilterExpression={"champ": {"$type": "string"}}`. Sans cela, tous les documents sans le champ valent `null` et violent l'unicité dès le deuxième. *(Étape 12)*
8. Croire que rien n'est passé. Avec `ordered=False`, une partie du lot a réussi : lisez `exc.details["nInserted"]` et `writeErrors`, et ne rejouez que les opérations en échec. *(Étape 09)*
9. Les lignes sont **bornées** et toujours lues avec la commande ; les commandes d'un client sont **non bornées** et se lisent séparément - les imbriquer conduirait au mur des 16 Mo. *(Étape 11)*
10. L'auditer : quels champs existent réellement, dans quelle proportion, et avec quels types (`$objectToArray` + `$group`, ou l'onglet Schema de Compass). *(Étape 10)*

</details>

---

## 13.8 La checklist des bonnes pratiques

**Connexion** - un client par processus · timeouts explicites · `tz_aware=True` · URI dans `.env` · client créé après le fork · `ping` au démarrage.

**Modélisation** - modéliser les requêtes, pas les entités · borner les tableaux · `Decimal128` pour l'argent · dates UTC *aware* · une source de vérité par donnée dupliquée.

**Schéma souple** - auditer avant de coder · noyau commun verrouillé par une validation JSON Schema · `additionalProperties: true` · une convention écrite pour "absent vs null vs 0" · `schema_version` et migration progressive.

**Lecture** - jamais de crochets sur un champ optionnel · projeter · paginer par curseur · itérer les curseurs plutôt que les matérialiser.

**Écriture** - `$set` plutôt que `replace_one` · condition métier dans le filtre de `find_one_and_update` · `bulk_write` par tranches de 1 000 · `upsert` + `$setOnInsert` pour les imports.

**Index** - un index par requête fréquente · règle ESR · index **partiels** sur les champs optionnels · `explain()` avant de conclure · supprimer les inutilisés.

**Exploitation** - suppression logique + TTL · sauvegardes testées · `w: "majority"` · l'application n'est jamais `root` · le port 27017 n'est jamais exposé.

---

## ✅ Bravo

Vous savez maintenant démarrer MongoDB, vous y connecter, écrire un CRUD complet, gérer une collection dont les documents n'ont pas tous la même forme, modéliser sans réflexe relationnel et vérifier vos index.

→ **[Étape 14 - Annexes](14-annexes.md)** : les tableaux de correspondance et les ressources pour continuer.
