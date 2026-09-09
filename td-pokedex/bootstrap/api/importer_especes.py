"""Charge donnees/especes.json dans MongoDB. Reexecutable.

Fourni : vous n'avez pas a modifier ce fichier. Lisez-le au chapitre 02 - il
fait, en plus simple, exactement ce que vous allez ecrire dans db.py.

    docker compose exec api python importer_especes.py
    docker compose exec api python importer_especes.py --reset   # vide d'abord
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from bson import json_util
from pymongo import ASCENDING, IndexModel, UpdateOne
from pymongo.errors import ServerSelectionTimeoutError

from db import fermer, get_db

FICHIER = Path(__file__).parent / "donnees" / "especes.json"


def charger() -> list[dict[str, Any]]:
    """Lit l'Extended JSON : $numberDecimal devient Decimal128, $date un datetime."""
    texte = FICHIER.read_text(encoding="utf-8")
    return json_util.loads(texte)


async def attendre_mongo(essais: int = 30) -> None:
    """Le conteneur mongo peut n'etre pas encore pret : on reessaie."""
    for tentative in range(1, essais + 1):
        try:
            await get_db().client.admin.command("ping")
            return
        except ServerSelectionTimeoutError:
            print(f"MongoDB pas encore la ({tentative}/{essais})...")
            await asyncio.sleep(2)
    raise SystemExit("MongoDB reste injoignable : `docker compose ps` ?")


async def importer(reset: bool = False) -> None:
    await attendre_mongo()
    db = get_db()
    col = db["especes"]

    if reset:
        supprimes = (await col.delete_many({})).deleted_count
        print(f"{supprimes} documents supprimes (--reset)")

    especes = charger()
    # Index unique pose des l'import : sans lui, deux --reset concurrents
    # pourraient creer des doublons de numero.
    await col.create_indexes([
        IndexModel([("numero", ASCENDING)], unique=True, name="uniq_numero"),
    ])

    resultat = await col.bulk_write([
        UpdateOne({"numero": espece["numero"]},
                  {"$set": espece},
                  upsert=True)
        for espece in especes
    ], ordered=False)

    total = await col.count_documents({})
    print(f"{resultat.upserted_count} especes importees, "
          f"{resultat.modified_count} mises a jour - {total} au total")
    await fermer()


if __name__ == "__main__":
    asyncio.run(importer(reset="--reset" in sys.argv))
