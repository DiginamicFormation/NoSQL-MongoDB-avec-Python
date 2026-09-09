"""Validation JSON Schema de la collection especes (chapitre 09).

Script reexecutable : on peut le lancer au demarrage de l'application ou en CI.

    docker compose exec api python provision.py
    docker compose exec api python provision.py --strict

TODO chapitre 09 : NOYAU_COMMUN et REGLES_FAMILLES sont a ecrire. Tant qu'ils
sont vides, le validateur ne refuse rien - et c'est deja un enseignement.
"""
from __future__ import annotations

from typing import Any

from db import fermer, get_db

# --- Le noyau commun : ce sur quoi tout le code s'appuie ---------------------
# TODO chapitre 09 : decrivez ici numero, nom, famille, langages, stade, xp,
# evolutions (4 sous-documents, salaire en decimal), habitats (GeoJSON Point)
# et schema_version.
#
# Le piege : `additionalProperties` doit rester a True. A False, vous
# refuseriez bundler, gpu_requis et chapeau - et vous perdriez tout l'interet
# du modele documentaire.
NOYAU_COMMUN: dict[str, Any] = {
    "$jsonSchema": {
        "bsonType": "object",
        "additionalProperties": True,
    }
}                                              # <- a completer au chapitre 09

# --- Les contraintes propres a certaines familles ---------------------------
# TODO chapitre 09 : "toute espece frontend a un bundler (chaine) et une
# reactivite". Un $or, exactement comme la regle des ecrans a l'etape 10.
REGLES_FAMILLES: dict[str, Any] = {}           # <- a completer au chapitre 09

VALIDATOR: dict[str, Any] = ({"$and": [NOYAU_COMMUN, REGLES_FAMILLES]}
                             if REGLES_FAMILLES else NOYAU_COMMUN)


async def provisionner(strict: bool = False) -> str:
    """Cree ou met a jour la collection et sa validation.

    strict=False (defaut) : moderate/warn. A utiliser sur une collection
        existante, le temps de migrer les documents non conformes - les
        ecritures passent, les violations sont journalisees.
    strict=True : strict/error. La regle devient une garantie.

    Fourni. La sequence moderate -> migrer -> strict est le sujet du
    chapitre 09 : passer directement en strict ferait echouer l'import, parce
    que Dev TurboPascal n'est pas conforme.
    """
    db = get_db()
    niveau = "strict" if strict else "moderate"
    action = "error" if strict else "warn"

    if "especes" not in await db.list_collection_names():
        await db.create_collection("especes", validator=VALIDATOR,
                                   validationLevel=niveau,
                                   validationAction=action)
        return f"collection creee (validation {niveau}/{action})"
    # collMod exige le role dbAdmin : c'est pourquoi init/01-init.js donne
    # dbOwner a l'utilisateur applicatif.
    await db.command("collMod", "especes", validator=VALIDATOR,
                     validationLevel=niveau, validationAction=action)
    return f"validation mise a jour ({niveau}/{action})"


if __name__ == "__main__":
    import asyncio
    import sys

    async def principal() -> None:
        print(await provisionner(strict="--strict" in sys.argv))
        await fermer()

    asyncio.run(principal())
