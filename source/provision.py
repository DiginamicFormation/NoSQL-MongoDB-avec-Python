"""Validation JSON Schema et index de la collection produits (étapes 10 et 12).

Script réexécutable : on peut le lancer au démarrage de l'application ou en CI.
"""
from pymongo import ASCENDING, DESCENDING, IndexModel

from db import get_db

# --- Le noyau commun : ce sur quoi tout le code s'appuie ---------------------
NOYAU_COMMUN = {
    "$jsonSchema": {
        "bsonType": "object",
        "title": "produit",
        "required": ["sku", "nom", "categorie", "prix", "schema_version"],
        "properties": {
            "sku": {"bsonType": "string", "pattern": "^[A-Z]{3}-[0-9]{4}$"},
            "nom": {"bsonType": "string", "minLength": 2, "maxLength": 200},
            "categorie": {"enum": ["clavier", "ecran", "souris", "livre", "abonnement"]},
            "prix": {"bsonType": "decimal", "description": "Decimal128, en euros"},
            "stock": {"bsonType": "int", "minimum": 0},
            "tags": {"bsonType": "array", "items": {"bsonType": "string"}},
            "schema_version": {"bsonType": "int", "minimum": 1},
        },
        # On impose le noyau commun, on laisse la liberté sur le reste :
        # c'est tout l'intérêt du modèle documentaire.
        "additionalProperties": True,
    }
}

# --- Les contraintes propres à certaines familles ---------------------------
REGLES_FAMILLES = {
    "$or": [
        {"categorie": {"$ne": "ecran"}},
        {"$and": [{"pouces": {"$type": "int"}}, {"resolution": {"$exists": True}}]},
    ]
}

VALIDATOR = {"$and": [NOYAU_COMMUN, REGLES_FAMILLES]}

INDEX = [
    IndexModel([("sku", ASCENDING)], unique=True, name="uniq_sku"),
    IndexModel([("categorie", ASCENDING), ("prix", DESCENDING)], name="cat_prix"),
    IndexModel([("tags", ASCENDING)], name="tags"),
    # Index TTL partiel : purge la corbeille 30 jours après la suppression logique,
    # et ne touche jamais les documents qui n'ont pas le champ.
    IndexModel([("supprime_le", ASCENDING)], name="ttl_corbeille",
               expireAfterSeconds=30 * 24 * 3600,
               partialFilterExpression={"supprime_le": {"$type": "date"}}),
]


def provisionner(strict: bool = False) -> None:
    """Crée ou met à jour la collection, sa validation et ses index.

    strict=False (défaut) : validationLevel=moderate + validationAction=warn.
        À utiliser sur une collection existante, le temps de migrer les documents
        non conformes - les écritures passent, les violations sont journalisées.
    strict=True : validationLevel=strict + validationAction=error.
        La règle devient une garantie : les écritures non conformes sont refusées.
    """
    db = get_db()
    niveau = "strict" if strict else "moderate"
    action = "error" if strict else "warn"

    if "produits" not in db.list_collection_names():
        db.create_collection("produits", validator=VALIDATOR,
                             validationLevel=niveau, validationAction=action)
        print(f"collection créée (validation {niveau}/{action})")
    else:
        db.command("collMod", "produits", validator=VALIDATOR,
                   validationLevel=niveau, validationAction=action)
        print(f"validation mise à jour ({niveau}/{action})")

    db.produits.create_indexes(INDEX)      # idempotent
    print("index :", [i["name"] for i in db.produits.list_indexes()])


if __name__ == "__main__":
    import sys

    provisionner(strict="--strict" in sys.argv)
