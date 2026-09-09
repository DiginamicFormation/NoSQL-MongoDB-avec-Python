"""Toutes les opérations MongoDB de l'application, et elles seules (étape 13).

Le reste du programme n'importe jamais pymongo : il passe par ce dépôt, qui
traduit les erreurs du driver en exceptions métier et applique les règles
transverses (suppression logique, champs interdits, atomicité).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterator

from bson import Decimal128, ObjectId
from bson.errors import InvalidId
from pymongo import ASCENDING, DESCENDING, IndexModel, ReturnDocument, UpdateOne
from pymongo.command_cursor import CommandCursor
from pymongo.database import Database
from pymongo.errors import BulkWriteError, DuplicateKeyError, WriteError

VERSION_SCHEMA = 1

# Le noyau commun : tout le reste d'un document est "spécifique à la famille".
CHAMPS_COMMUNS = {"_id", "sku", "nom", "categorie", "prix", "stock", "tags",
                  "cree_le", "maj_le", "supprime_le", "schema_version"}


# --------------------------------------------------------------- exceptions
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


# --------------------------------------------------------------- le dépôt
class CatalogueRepository:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.col = db["produits"]

    # ------------------------------------------------------------ setup
    def initialiser(self) -> None:
        """Crée les index. Idempotent (voir provision.py pour la validation)."""
        self.col.create_indexes([
            IndexModel([("sku", ASCENDING)], unique=True, name="uniq_sku"),
            IndexModel([("categorie", ASCENDING), ("prix", DESCENDING)], name="cat_prix"),
            IndexModel([("tags", ASCENDING)], name="tags"),
            IndexModel([("supprime_le", ASCENDING)], name="ttl_corbeille",
                       expireAfterSeconds=30 * 24 * 3600,
                       partialFilterExpression={"supprime_le": {"$type": "date"}}),
        ])

    # ----------------------------------------------------------- create
    def creer(self, sku: str, nom: str, categorie: str, prix: str,
              stock: int | None = None, **specifiques: Any) -> ObjectId:
        """Crée un produit. Les champs propres à la famille passent en kwargs."""
        document: dict[str, Any] = {
            "sku": sku,
            "nom": nom,
            "categorie": categorie,
            "prix": Decimal128(str(prix)),
            "cree_le": datetime.now(timezone.utc),
            "schema_version": VERSION_SCHEMA,
            **specifiques,
        }
        if stock is not None:          # champ absent = "non géré en stock"
            document["stock"] = int(stock)
        try:
            return self.col.insert_one(document).inserted_id
        except DuplicateKeyError as exc:
            raise ProduitDejaExistant(f"le SKU {sku} existe déjà") from exc
        except WriteError as exc:
            details = exc.details.get("errInfo", exc.details) if exc.details else exc
            raise DocumentInvalide(str(details)) from exc

    def importer(self, catalogue: list[dict[str, Any]]) -> tuple[int, int]:
        """Import réexécutable : crée ce qui manque, met à jour le reste.

        Renvoie (créés, mis à jour).
        """
        if not catalogue:
            return (0, 0)
        maintenant = datetime.now(timezone.utc)
        try:
            resultat = self.col.bulk_write([
                UpdateOne(
                    {"sku": produit["sku"]},
                    {"$set": {**produit, "schema_version": VERSION_SCHEMA},
                     "$setOnInsert": {"cree_le": maintenant}},   # jamais écrasé
                    upsert=True,
                )
                for produit in catalogue
            ], ordered=False)
        except BulkWriteError as exc:
            erreurs = exc.details.get("writeErrors", []) if exc.details else []
            if any(e.get("code") == 11000 for e in erreurs):
                raise ProduitDejaExistant(str(erreurs)) from exc
            raise DocumentInvalide(str(erreurs)) from exc
        return (resultat.upserted_count, resultat.modified_count)

    # ------------------------------------------------------------- read
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
            oid = ObjectId(identifiant)           # une chaîne ne matche jamais un ObjectId
        except InvalidId as exc:
            raise ProduitIntrouvable(identifiant) from exc
        document = self.col.find_one({"_id": oid, "supprime_le": {"$exists": False}})
        if document is None:
            raise ProduitIntrouvable(identifiant)
        return document

    def lister(self, categorie: str | None = None, prix_max: str | None = None,
               apres: ObjectId | None = None, taille: int = 20) -> list[dict[str, Any]]:
        """Liste paginée par curseur (pas de skip)."""
        filtre: dict[str, Any] = {"supprime_le": {"$exists": False}}
        if categorie:
            filtre["categorie"] = categorie
        if prix_max:
            filtre["prix"] = {"$lte": Decimal128(str(prix_max))}
        if apres:
            filtre["_id"] = {"$gt": apres}
        return list(
            self.col.find(filtre, {"sku": 1, "nom": 1, "prix": 1, "stock": 1, "categorie": 1})
                    .sort("_id", ASCENDING)
                    .limit(taille)
        )

    def compter(self, categorie: str | None = None,
                inclure_supprimes: bool = False) -> int:
        filtre: dict[str, Any] = {}
        if not inclure_supprimes:
            filtre["supprime_le"] = {"$exists": False}
        if categorie:
            filtre["categorie"] = categorie
        return self.col.count_documents(filtre)

    # ----------------------------------------------------------- update
    def modifier(self, sku: str, champs: dict[str, Any]) -> bool:
        """Modifie des champs. Renvoie True si quelque chose a changé.

        La condition "au moins un champ diffère" est dans le FILTRE : sinon
        `$currentDate` réécrirait `maj_le` à chaque appel et le retour serait
        toujours True, même sur une valeur identique.
        """
        interdits = [c for c in champs if c.startswith("$") or "." in c or c == "_id"]
        if interdits:
            raise DocumentInvalide(f"champs interdits : {interdits}")
        if not champs:
            self.par_sku(sku)                 # lève ProduitIntrouvable si absent
            return False
        filtre = {"sku": sku, "supprime_le": {"$exists": False},
                  "$or": [{cle: {"$ne": valeur}} for cle, valeur in champs.items()]}
        try:
            resultat = self.col.update_one(
                filtre, {"$set": champs, "$currentDate": {"maj_le": True}})
        except WriteError as exc:
            details = exc.details.get("errInfo", exc.details) if exc.details else exc
            raise DocumentInvalide(str(details)) from exc
        if resultat.matched_count == 0:
            self.par_sku(sku)                 # lève ProduitIntrouvable si absent
            return False                      # présent, mais déjà à jour
        return True

    def reserver(self, sku: str, quantite: int) -> dict[str, Any]:
        """Décrémente le stock atomiquement, jamais en dessous de zéro.

        La condition métier est DANS le filtre : deux clients concurrents ne
        peuvent pas réserver le même dernier article.
        """
        document = self.col.find_one_and_update(
            {"sku": sku, "stock": {"$gte": quantite}, "supprime_le": {"$exists": False}},
            {"$inc": {"stock": -quantite}, "$currentDate": {"maj_le": True}},
            return_document=ReturnDocument.AFTER,
        )
        if document is None:
            # Seconde requête UNIQUEMENT en cas d'échec, pour affiner le message.
            self.par_sku(sku)                     # lève ProduitIntrouvable le cas échéant
            raise StockInsuffisant(f"{sku} : stock insuffisant ou non géré en stock")
        return document

    # ----------------------------------------------------------- delete
    def supprimer(self, sku: str) -> None:
        """Suppression logique : purge automatique 30 jours plus tard (index TTL)."""
        resultat = self.col.update_one(
            {"sku": sku, "supprime_le": {"$exists": False}},
            {"$set": {"supprime_le": datetime.now(timezone.utc)}},
        )
        if resultat.matched_count == 0:
            raise ProduitIntrouvable(sku)

    def supprimer_definitivement(self, sku: str) -> None:
        if self.col.delete_one({"sku": sku}).deleted_count == 0:
            raise ProduitIntrouvable(sku)

    def restaurer(self, sku: str) -> None:
        resultat = self.col.update_one({"sku": sku, "supprime_le": {"$exists": True}},
                                       {"$unset": {"supprime_le": ""}})
        if resultat.matched_count == 0:
            raise ProduitIntrouvable(sku)

    # ------------------------------------------- lecture "hétérogène"
    @staticmethod
    def decouper(document: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        """Sépare le noyau commun des champs spécifiques à la famille."""
        commun = {k: v for k, v in document.items() if k in CHAMPS_COMMUNS}
        specifique = {k: v for k, v in document.items() if k not in CHAMPS_COMMUNS}
        return commun, specifique

    def auditer(self) -> CommandCursor:
        """Présence et types réels de chaque champ de la collection (étape 10)."""
        return self.col.aggregate([
            {"$project": {"champs": {"$objectToArray": "$$ROOT"}}},
            {"$unwind": "$champs"},
            {"$group": {"_id": "$champs.k",
                        "presents": {"$sum": 1},
                        "types": {"$addToSet": {"$type": "$champs.v"}}}},
            {"$sort": {"presents": -1}},
        ])

    def statistiques(self) -> CommandCursor:
        """Chiffres par catégorie, tolérants aux champs absents."""
        return self.col.aggregate([
            {"$match": {"supprime_le": {"$exists": False}}},
            {"$group": {
                "_id": "$categorie",
                "nombre": {"$sum": 1},
                "prix_moyen": {"$avg": {"$toDouble": "$prix"}},
                "stock_total": {"$sum": {"$ifNull": ["$stock", 0]}},
                "sans_stock": {"$sum": {"$cond": [
                    {"$eq": [{"$type": "$stock"}, "missing"]}, 1, 0]}},
            }},
            {"$sort": {"nombre": -1}},
        ])

    def types_du_champ(self, champ: str) -> Iterator[tuple[str, int]]:
        """Diagnostic : quels types BSON trouve-t-on dans ce champ ?"""
        for ligne in self.col.aggregate([
            {"$group": {"_id": {"$type": f"${champ}"}, "n": {"$sum": 1}}},
            {"$sort": {"n": -1}},
        ]):
            yield (ligne["_id"], ligne["n"])
