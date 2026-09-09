"""Connexion unique a MongoDB, partagee par toute l'application.

Fourni : vous n'avez pas a le modifier. Lisez-le au chapitre 02, les deux
commentaires ci-dessous portent tout le chapitre.
"""
import os

from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

_client: AsyncMongoClient | None = None


def get_client() -> AsyncMongoClient:
    """Un seul client par processus : il est sur, et il porte le pool.

    Il est cree paresseusement, et non a l'import : un AsyncMongoClient se lie a
    la boucle asyncio dans laquelle il est cree. Construit au niveau module, le
    premier `await` leverait "attached to a different loop".
    """
    global _client
    if _client is None:
        uri = os.environ.get("MONGODB_URI")
        if not uri:
            raise RuntimeError(
                "MONGODB_URI est absent : copiez .env.example en .env")
        _client = AsyncMongoClient(
            uri,
            serverSelectionTimeoutMS=5_000,   # echouer vite si le serveur manque
            connectTimeoutMS=5_000,
            tz_aware=True,                    # datetime "aware", en UTC
            appname="pokedex",
        )
    return _client


def get_db() -> AsyncDatabase:
    return get_client()[os.environ.get("MONGODB_DB", "pokedex")]


async def fermer() -> None:
    """Ferme le client. Appelee a l'extinction de l'application."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
