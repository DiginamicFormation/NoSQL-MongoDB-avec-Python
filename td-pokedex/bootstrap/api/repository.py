"""Toutes les operations MongoDB du Pokedex, et elles seules.

C'EST LE FICHIER DU TD. Le reste du programme n'importe jamais pymongo : il
passe par ce depot, qui traduit les erreurs du driver en exceptions metier et
applique les regles transverses (extinction logique, champs interdits,
atomicite).

Chaque methode a encore un marqueur en fin de ligne, qui dit a quel chapitre
elle se remplit. Il en reste 18 : c'est votre barre de progression.

    docker compose exec api sh -c "grep -c 'chapitre 0.\$' repository.py"

Rappel du driver asynchrone :
    col.find(...)                      n'est PAS une coroutine -> AsyncCursor
    await col.find(...).to_list(n)     c'est la consommation qui s'attend
    curseur = await col.aggregate(...) aggregate EST une coroutine
    [ligne async for ligne in curseur] et rend un AsyncCommandCursor
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bson import Decimal128
from pymongo import (ASCENDING, DESCENDING, GEOSPHERE, IndexModel,
                     ReturnDocument, UpdateOne)
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import BulkWriteError, DuplicateKeyError, WriteError

import fixtures
from modeles import en_json

VERSION_SCHEMA = 1
STADES = ["junior", "mature", "senior", "gourou"]

# Le noyau commun : tout le reste d'un document est "specifique a la famille".
CHAMPS_COMMUNS = {"_id", "numero", "nom", "famille", "langages", "stade", "xp",
                  "evolutions", "habitats", "cree_le", "maj_le", "eteinte_le",
                  "schema_version"}

# Ce que la liste renvoie : assez pour dessiner une carte, pas plus.
PROJECTION_RESUME = {"_id": 0, "numero": 1, "nom": 1, "famille": 1, "stade": 1,
                     "langages": 1, "xp": 1, "evolutions.titre": 1,
                     "habitats": 1, "eteinte_le": 1}


# --------------------------------------------------------------- exceptions
class ErreurPokedex(Exception):
    """Classe mere des erreurs metier du Pokedex."""


class EspeceIntrouvable(ErreurPokedex):
    pass


class EspeceDejaExistante(ErreurPokedex):
    pass


class EvolutionImpossible(ErreurPokedex):
    pass


class DocumentInvalide(ErreurPokedex):
    pass


# ------------------------------------------------------------------ le depot
class DepotPokedex:
    def __init__(self, db: AsyncDatabase) -> None:
        self.db = db
        self.col = db["especes"]

    # -------------------------------------------------------------- setup
    async def initialiser(self) -> list[str]:
        """Cree les index de la collection, et renvoie leurs noms. Idempotent.

        TODO chapitre 05 : uniq_numero, sans lequel le 409 n'arrivera jamais.
        TODO chapitre 07 : ttl_extinction, un index TTL PARTIEL.
        TODO chapitre 08 : geo_habitats, un index 2dsphere sur habitats.point.
        TODO chapitre 09 : famille_numero et langages, apres explain().
        """
        return fixtures.INDEX                      # <- a supprimer au chapitre 05

    async def sante(self) -> dict[str, Any]:
        """Etat de la connexion, version du serveur, nombre d'especes.

        TODO chapitre 02 : la connexion est paresseuse. Seul un ping la force.
        """
        return fixtures.SANTE                      # <- a supprimer au chapitre 02

    # ------------------------------------------------------------- create
    async def creer(self, numero: int, nom: str, famille: str,
                    evolutions: list[dict[str, Any]],
                    langages: list[str] | None = None, xp: int | None = None,
                    habitats: list[dict[str, Any]] | None = None,
                    **specifiques: Any) -> int:
        """Cree une espece. Les champs propres a la famille passent en kwargs.

        TODO chapitre 05 : construisez le document, puis insert_one.
          - une espece nait toujours au stade 0 ;
          - les salaires deviennent des Decimal128, jamais des chaines ;
          - xp est OPTIONNEL : absent veut dire "jamais capturee", pas zero ;
          - DuplicateKeyError devient EspeceDejaExistante,
            WriteError devient DocumentInvalide.
        """
        return fixtures.CREATION                   # <- a supprimer au chapitre 05

    async def importer(self, catalogue: list[dict[str, Any]]) -> tuple[int, int]:
        """Import reexecutable : cree ce qui manque, met a jour le reste.

        Fourni. Lisez-le : c'est le bulk_write de l'etape 09 du cours.
        """
        if not catalogue:
            return (0, 0)
        maintenant = datetime.now(timezone.utc)
        try:
            resultat = await self.col.bulk_write([
                UpdateOne(
                    {"numero": espece["numero"]},
                    {"$set": espece,
                     "$setOnInsert": {"cree_le": maintenant}},   # jamais ecrase
                    upsert=True,
                )
                for espece in catalogue
            ], ordered=False)
        except BulkWriteError as exc:
            erreurs = exc.details.get("writeErrors", []) if exc.details else []
            raise DocumentInvalide(str(erreurs)) from exc
        return (resultat.upserted_count, resultat.modified_count)

    # --------------------------------------------------------------- read
    async def par_numero(self, numero: int,
                         inclure_eteintes: bool = False) -> dict[str, Any]:
        """La fiche complete d'une espece.

        TODO chapitre 04 : find_one, puis EspeceIntrouvable si None.
          - le filtre exclut les especes eteintes, sauf demande contraire ;
          - passez le document par en_json : ObjectId, Decimal128 et datetime
            n'ont pas d'equivalent JSON.
        """
        return fixtures.FICHE                      # <- a supprimer au chapitre 04

    async def lister(self, famille: str | None = None, q: str | None = None,
                     eteintes: bool = False, apres: int | None = None,
                     taille: int = 20) -> list[dict[str, Any]]:
        """Liste paginee par curseur (pas de skip).

        TODO chapitre 03 : construisez le filtre, puis find + sort + limit.
          - par defaut on exclut les eteintes ;
          - q cherche dans le nom OU dans les langages ;
          - apres est le numero de la derniere espece de la page precedente ;
          - projetez avec PROJECTION_RESUME, qui retire _id.
        """
        return fixtures.LISTE[:taille]             # <- a supprimer au chapitre 03

    async def compter(self, famille: str | None = None,
                      inclure_eteintes: bool = False) -> int:
        """Combien d'especes, avec le meme filtre que lister().

        TODO chapitre 03 : count_documents.
        """
        return fixtures.NOMBRE                     # <- a supprimer au chapitre 03

    @staticmethod
    def decouper(document: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        """Separe le noyau commun des champs specifiques a la famille.

        TODO chapitre 04 : deux dictionnaires en comprehension, a partir de
        CHAMPS_COMMUNS. C'est ce qui permet a une seule route d'afficher aussi
        bien un data scientist qu'un dev Svelte.
        """
        return (document, {})                      # <- a supprimer au chapitre 04

    # ------------------------------------------------------------- update
    async def modifier(self, numero: int, champs: dict[str, Any]) -> bool:
        """Modifie des champs. Renvoie True si quelque chose a change.

        TODO chapitre 06 :
          - refusez les cles commencant par $, contenant un point, ou valant
            _id / numero : c'est une injection d'operateur ;
          - mettez la condition "au moins un champ differe" DANS le filtre,
            sinon $currentDate reecrit maj_le a chaque appel et le retour est
            toujours True ;
          - matched_count == 0 : soit absente, soit deja a jour. Distinguez.
        """
        return fixtures.MODIFICATION               # <- a supprimer au chapitre 06

    async def evoluer(self, numero: int) -> dict[str, Any]:
        """Passe l'espece au stade suivant, atomiquement.

        TODO chapitre 06 : find_one_and_update, avec la condition metier
        "stade < gourou" DANS LE FILTRE. Deux clics simultanes ne doivent pas
        pouvoir sauter un stade.
          - return_document=ReturnDocument.AFTER, sinon l'ecran affiche le
            stade precedent ;
          - None : relisez l'espece pour distinguer "introuvable" de
            "deja gourou".
        """
        return fixtures.EVOLUTION                  # <- a supprimer au chapitre 06

    # ------------------------------------------------------------- delete
    async def eteindre(self, numero: int) -> None:
        """Extinction logique : le document reste, il porte une date.

        TODO chapitre 07 : update_one avec $set sur eteinte_le.
        matched_count == 0 -> EspeceIntrouvable.
        """
        return None                                # <- a supprimer au chapitre 07

    async def eteindre_definitivement(self, numero: int) -> None:
        """La vraie suppression, celle qui ne se rattrape pas.

        TODO chapitre 07 : delete_one. deleted_count == 0 est le SEUL signal
        qu'il n'y avait rien a supprimer.
        """
        return None                                # <- a supprimer au chapitre 07

    async def restaurer(self, numero: int) -> None:
        """Sort une espece de la corbeille.

        TODO chapitre 07 : $unset sur eteinte_le, avec $exists: True au filtre.
        """
        return None                                # <- a supprimer au chapitre 07

    # ---------------------------------------------------------- geospatial
    async def autour_de(self, lon: float, lat: float, km: float,
                        taille: int = 50) -> list[dict[str, Any]]:
        """Especes observees dans un rayon, triees par distance croissante.

        TODO chapitre 08 : $near sur habitats.point.
          - GeoJSON, c'est [longitude, latitude] - dans cet ordre ;
          - $maxDistance est en METRES ;
          - $near exige l'index 2dsphere pose par initialiser().
        """
        return fixtures.AUTOUR                     # <- a supprimer au chapitre 08

    async def dans_la_zone(self, ouest: float, sud: float, est: float,
                           nord: float, taille: int = 100) -> list[dict[str, Any]]:
        """Especes dont un habitat tombe dans le rectangle visible sur la carte.

        TODO chapitre 08 : $geoWithin avec un Polygon.
        Un anneau GeoJSON se FERME : le premier point est aussi le dernier.
        """
        return fixtures.ZONE                       # <- a supprimer au chapitre 08

    # ---------------------------------------------------------- agregation
    async def statistiques(self) -> list[dict[str, Any]]:
        """Chiffres par famille, tolerants aux champs absents.

        TODO chapitre 09 : $match, $group, $project, $sort.
          - xp absent n'est pas xp a zero : $ifNull pour la somme, et un
            comptage separe avec {"$type": "$xp"} == "missing" ;
          - le salaire du dernier stade est un Decimal128 : convertissez-le en
            $toDouble DANS le pipeline, sinon la reponse n'est pas
            serialisable.
        """
        return fixtures.STATISTIQUES               # <- a supprimer au chapitre 09

    async def auditer(self) -> list[dict[str, Any]]:
        """Presence et types reels de chaque champ de la collection.

        TODO chapitre 09 : $objectToArray, $unwind, $group.
        Attention au denominateur : l'agregation balaie TOUTE la collection,
        eteintes comprises. Un total qui les exclut fait depasser 100 %.
        """
        return fixtures.AUDIT                      # <- a supprimer au chapitre 09

    async def decrire_schema(self) -> dict[str, Any]:
        """Ce que le serveur impose reellement : validation et index.

        TODO chapitre 09 : listCollections pour le validateur, list_indexes
        pour les index.
        """
        return fixtures.SCHEMA                     # <- a supprimer au chapitre 09

    async def plan_de_requete(self, filtre: dict[str, Any]) -> dict[str, Any]:
        """Le plan choisi par le serveur : COLLSCAN ou IXSCAN ?

        TODO chapitre 09 : explain() est asynchrone aussi, le curseur l'est.
        """
        return fixtures.PLAN                       # <- a supprimer au chapitre 09
