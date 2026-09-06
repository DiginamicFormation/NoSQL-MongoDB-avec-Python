[← Étape 05](05-se-connecter-en-python.md) · [Sommaire](README.md) · [Étape suivante →](07-crud-lire.md)

# Étape 06 - CRUD 1/4 : Créer

> 🎯 **Objectif** : insérer des documents depuis Python, maîtriser `_id`, et savoir quoi faire quand une insertion échoue.
> ⏱️ **Durée** : 45 minutes.
> 📁 **On crée** : `boutique/creer.py`.

Les quatre prochaines étapes suivent l'ordre de la documentation officielle du driver : **Insert → Query → Update / Replace → Delete / Bulk Write**.

---

## 6.1 `insert_one`

### À faire - `creer.py`

```python
from datetime import datetime, timezone

from bson import Decimal128
from pymongo.errors import DuplicateKeyError

from db import get_db

db = get_db()

document = {
    "sku": "KBD-0010",
    "nom": "Clavier TKL silencieux",
    "categorie": "clavier",
    "prix": Decimal128("119.00"),
    "stock": 8,
    "tags": ["clavier", "silencieux"],
    "cree_le": datetime.now(timezone.utc),
}

resultat = db.produits.insert_one(document)

print("Identifiant :", resultat.inserted_id)     # ObjectId('...')
print("Acquitté    :", resultat.acknowledged)    # True
print("Le dict a été modifié :", document["_id"])
```

```bash
python creer.py
```

### Ce qui se passe

`insert_one` renvoie un objet `InsertOneResult` avec deux attributs utiles : `inserted_id` et `acknowledged`.

Trois comportements à connaître :

1. **L'`_id` est généré côté client.** PyMongo crée l'`ObjectId` *avant* d'envoyer la requête : vous connaissez l'identifiant sans attendre la réponse du serveur.
2. **Votre dictionnaire est modifié sur place.** Après l'appel, `document` contient une clé `_id`. Pratique - et piégeux : réutiliser le même dictionnaire pour une seconde insertion lèvera une `DuplicateKeyError`, puisque l'`_id` est déjà pris.
3. **La collection est créée si elle n'existait pas**, ainsi que la base.

### Les types, tout de suite

```python
"prix": Decimal128("119.00"),               # ✅ montant exact
"cree_le": datetime.now(timezone.utc),      # ✅ date aware, en UTC
```

- **`Decimal128` pour l'argent.** Un `float` (BSON `Double`) accumule des erreurs binaires : `0.1 + 0.2 != 0.3`. Sur des prix et des totaux, cela finit toujours par produire un écart d'un centime - et un client mécontent. Alternative acceptable : stocker des **centimes** dans un `int`.
- **`datetime.now(timezone.utc)`, jamais `datetime.now()`.** MongoDB stocke les dates en UTC, sans fuseau. Fournir un datetime naïf, c'est laisser Python et MongoDB deviner - et se tromper.

> ⚠️ **Vous venez de créer une hétérogénéité de types.** Les produits insérés à l'étape 04 depuis `mongosh` ont un `prix` de type `Double` ; celui-ci est un `Decimal128`. Les deux cohabitent dans la même collection, et MongoDB ne dira rien. Ce n'est pas un accident de parcours : c'est exactement ce qui arrive dans la vraie vie quand deux applications écrivent dans la même collection. On apprendra à le détecter et à le corriger à l'[étape 10](10-schema-souple.md).

---

## 6.2 `insert_many`

```python
lot = [
    {"sku": "SCR-0011", "nom": "Ecran 24 pouces", "categorie": "ecran",
     "prix": Decimal128("179.00"), "stock": 15,
     "pouces": 24, "resolution": "1920x1080", "hz": 75,
     "cree_le": datetime.now(timezone.utc)},

    {"sku": "MSE-0012", "nom": "Souris verticale", "categorie": "souris",
     "prix": Decimal128("79.00"), "stock": 22,
     "poids_g": 110, "sans_fil": True,
     "cree_le": datetime.now(timezone.utc)},

    {"sku": "ABO-0013", "nom": "Support Pro mensuel", "categorie": "abonnement",
     "prix": Decimal128("19.00"),
     "periodicite": "mensuelle", "renouvellement_auto": True,
     "cree_le": datetime.now(timezone.utc)},     # 👈 ni stock, ni tags
]

resultat = db.produits.insert_many(lot, ordered=False)
print(len(resultat.inserted_ids), "documents insérés")
```

Remarquez à nouveau : ces trois documents **n'ont pas les mêmes champs**, et c'est volontaire. Un écran a une résolution, un abonnement a une périodicité et pas de stock. En SQL il aurait fallu une table par famille, ou une table large pleine de `NULL`, ou une table d'attributs clé-valeur. Ici, chaque document porte ce qui le concerne.

### Le paramètre `ordered`

| Valeur | Comportement en cas d'échec d'un document |
|---|---|
| `True` *(défaut)* | s'arrête au premier échec ; les documents **suivants ne sont pas insérés** |
| `False` | tente **tous** les documents, puis lève `BulkWriteError` récapitulant les échecs |

`ordered=False` est aussi plus rapide (le serveur peut paralléliser). Utilisez-le dès que l'ordre d'insertion n'a pas d'importance métier - c'est-à-dire presque toujours.

---

## 6.3 Choisir son `_id`

Rien n'oblige à utiliser un `ObjectId`. Si vos documents ont déjà un identifiant naturel, prenez-le :

```python
db.produits.insert_one({
    "_id": "LIV-0014",                 # le SKU comme clé primaire
    "nom": "MongoDB en pratique",
    "categorie": "livre",
    "prix": Decimal128("42.00"),
    "auteur": "K. Chodorow",
    "pages": 514,
    "cree_le": datetime.now(timezone.utc),
})
```

Remarquez qu'il n'y a **pas** de champ `sku` : quand on prend l'identifiant métier comme `_id`, on ne le duplique pas. Ce document sera donc, volontairement, le mouton noir de la collection - l'audit de l'[étape 10](10-schema-souple.md) le repérera (`_id` de type `string` alors que les autres sont des `objectId`), et il ne satisfera pas la validation qui exigera `sku`. C'est un cas d'école utile : dans une vraie base, ce genre de document existe toujours.

| | `ObjectId` | `_id` métier |
|---|---|---|
| Unicité | garantie | à vous de la garantir (elle l'est par l'index `_id`) |
| Index supplémentaire | il en faut un sur `sku` | économisé |
| Lisibilité des URL | `/produits/66f0a1b2…` | `/produits/LIV-0014` |
| Modifiable | non | **non plus** - un `_id` est immuable |
| Ordre naturel | ≈ chronologique | selon la clé |

> ⚠️ **Un `_id` est immuable.** Si votre identifiant métier peut changer un jour (un SKU qu'on renomme, un e-mail qu'on modifie), ne le prenez pas comme `_id` : il faudrait supprimer et recréer le document, en cassant toutes les références.

---

## 6.4 Quand l'insertion échoue

### `DuplicateKeyError` - la violation d'unicité

```python
try:
    db.produits.insert_one({"sku": "KBD-0010", "nom": "Doublon"})
except DuplicateKeyError as exc:
    print("SKU déjà utilisé :", exc.details["keyValue"])
```

C'est le code serveur **11000** (le `E11000` déjà vu dans le shell). En pratique, on ne cherche jamais à éviter cette erreur par un `find_one` préalable - ce serait une *race condition* : deux processus peuvent lire "absent" en même temps. On **tente l'insertion et on attrape l'exception** ; c'est l'index unique qui arbitre, atomiquement.

### `BulkWriteError` - l'échec partiel d'un lot

```python
from pymongo.errors import BulkWriteError

try:
    db.produits.insert_many(lot, ordered=False)
except BulkWriteError as exc:
    for erreur in exc.details["writeErrors"]:
        print(f"document #{erreur['index']} - code {erreur['code']} : {erreur['errmsg'][:80]}")
    print("insérés malgré tout :", exc.details["nInserted"])
```

**Le point important** : avec `ordered=False`, l'exception ne signifie pas que rien n'a été inséré. Elle signifie "certains ont échoué". Lisez toujours `nInserted` et `writeErrors` avant de conclure.

### Les codes d'erreur à reconnaître

| Code | Signification | Exception PyMongo |
|---|---|---|
| **11000** | clé dupliquée (index unique) | `DuplicateKeyError` |
| **121** | échec de validation JSON Schema | `WriteError` (étape 10) |
| **13** | droits insuffisants | `OperationFailure` |
| **50** | dépassement du temps maximal d'exécution | `ExecutionTimeout` |

---

## 6.5 Insérer de façon réexécutable

Un script d'import qu'on relance ne doit pas créer de doublons. La bonne pratique n'est pas `insert_many` mais un **upsert en lot** :

```python
from pymongo import UpdateOne

catalogue = [
    {"sku": "KBD-0010", "nom": "Clavier TKL silencieux", "prix": Decimal128("119.00")},
    {"sku": "SCR-0011", "nom": "Ecran 24 pouces",        "prix": Decimal128("179.00")},
]

resultat = db.produits.bulk_write(
    [UpdateOne({"sku": p["sku"]}, {"$set": p}, upsert=True) for p in catalogue],
    ordered=False,
)
print("créés :", resultat.upserted_count, "- mis à jour :", resultat.modified_count)
```

On peut relancer ce script autant de fois qu'on veut : il met à jour ce qui existe et crée le reste. `bulk_write` est détaillé à l'[étape 09](09-crud-supprimer.md), `upsert` à l'[étape 08](08-crud-modifier.md).

---

## 6.6 Récapitulatif

| Méthode | Retour | Attribut utile |
|---|---|---|
| `insert_one(doc)` | `InsertOneResult` | `inserted_id` |
| `insert_many(docs, ordered=False)` | `InsertManyResult` | `inserted_ids` |
| `bulk_write([UpdateOne(..., upsert=True)])` | `BulkWriteResult` | `upserted_count`, `modified_count` |

---

## Exercice (15 min)

Écrivez `seed.py`, un script de **peuplement réexécutable** qui insère six produits d'au moins trois familles différentes (clavier, écran, livre, abonnement…), chacune avec ses propres champs spécifiques. Contraintes :

1. les prix sont des `Decimal128`, les dates des `datetime` aware ;
2. relancer le script deux fois ne doit **pas** créer de doublons ;
3. le script affiche combien de documents ont été créés et combien mis à jour.

<details>
<summary>Voir la correction</summary>

```python
# seed.py
from datetime import datetime, timezone

from bson import Decimal128
from pymongo import UpdateOne

from db import get_db

MAINTENANT = datetime.now(timezone.utc)

CATALOGUE = [
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


def peupler() -> None:
    db = get_db()
    operations = [
        UpdateOne(
            {"sku": produit["sku"]},
            {"$set": produit, "$setOnInsert": {"cree_le": MAINTENANT}},
            upsert=True,
        )
        for produit in CATALOGUE
    ]
    resultat = db.produits.bulk_write(operations, ordered=False)
    print(f"créés : {resultat.upserted_count} - mis à jour : {resultat.modified_count}")
    print("total en base :", db.produits.count_documents({}))


if __name__ == "__main__":
    peupler()
```

Deux détails qui font la différence :

- **`$setOnInsert`** n'écrit `cree_le` qu'à la création. Avec un simple `$set`, chaque relance écraserait la date de création - une erreur classique dans les scripts d'import.
- Les produits n'ont volontairement **pas les mêmes champs** : `switches` pour les claviers, `pouces`/`hz` pour les écrans, `auteur`/`isbn` pour le livre, et pas de `stock` pour l'abonnement. Gardez ce jeu de données : toutes les étapes suivantes s'appuient dessus.

</details>

---

## ✅ Ce qu'il faut retenir

1. `insert_one` renvoie `inserted_id` ; l'`_id` est généré **côté client** et ajouté à votre dictionnaire.
2. `Decimal128` pour les montants, `datetime.now(timezone.utc)` pour les dates.
3. `insert_many(..., ordered=False)` : plus rapide, et n'abandonne pas au premier échec.
4. On ne teste pas l'existence avant d'insérer : on tente et on attrape `DuplicateKeyError` (code 11000).
5. Un import réexécutable s'écrit avec `bulk_write` + `UpdateOne(..., upsert=True)` et `$setOnInsert`.
6. Deux documents insérés par des chemins différents peuvent avoir des **types différents** pour le même champ : c'est à surveiller (étape 10).

→ **[Étape 07 - CRUD 2/4 : Lire](07-crud-lire.md)**
