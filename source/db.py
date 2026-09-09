"""Connexion unique à MongoDB, partagée par toute l'application (étape 05)."""
import os
from functools import lru_cache

from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.database import Database

load_dotenv()


@lru_cache(maxsize=1)
def get_client() -> MongoClient:
    """Un seul client par processus : il est thread-safe et gère son pool."""
    uri = os.getenv("MONGODB_URI")
    if not uri:
        raise SystemExit(
            "MONGODB_URI est absent : copiez .env.example en .env "
            "(cp .env.example .env) avant de lancer l'application."
        )
    return MongoClient(
        uri,
        serverSelectionTimeoutMS=5_000,   # échouer vite si le serveur est absent
        connectTimeoutMS=5_000,
        tz_aware=True,                    # datetime "aware", en UTC
        uuidRepresentation="standard",
        appname=os.getenv("APP_NAME", "boutique"),
    )


def get_db() -> Database:
    return get_client()[os.environ.get("MONGODB_DB", "boutique")]


if __name__ == "__main__":
    client = get_client()
    client.admin.command("ping")          # la connexion est paresseuse : on la force
    print("Connecté à MongoDB", client.server_info()["version"])
    print("Bases visibles  :", client.list_database_names())
    print("Collections     :", get_db().list_collection_names())
