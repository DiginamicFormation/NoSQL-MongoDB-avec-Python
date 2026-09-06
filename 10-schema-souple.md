[← Étape 09](09-crud-supprimer.md) · [Sommaire](README.md) · [Étape suivante →](11-modeliser.md)

# Étape 10 - Vivre avec un schéma souple

> 🎯 **Objectif** : maîtriser **la** spécificité du NoSQL documentaire - dans une même collection, les documents n'ont pas tous la même forme. Savoir auditer l'existant, écrire du code qui ne casse pas, poser des garde-fous et migrer sans interruption de service.
> ⏱️ **Durée** : 60 minutes.
> 📁 **On crée** : `boutique/auditer.py`, `boutique/provision.py`, `boutique/migrer.py`.

C'est l'étape la plus importante du cours après le CRUD. Un développeur qui la maîtrise travaille sereinement en MongoDB ; les autres finissent par écrire du SQL déguisé, ou par produire une collection dont plus personne ne connaît le contenu.

---

## 10.1 Pourquoi les documents diffèrent

Ce n'est jamais un accident. Il y a exactement quatre causes, et il est essentiel de savoir à laquelle on a affaire.

| Cause | Exemple | Est-ce sain ? |
|---|---|---|
| **① Familles métier différentes** | un écran a `pouces` et `hz`, un livre a `auteur` et `isbn` | ✅ oui - c'est la raison d'être du modèle |
| **② Évolution dans le temps** | les produits créés avant mars n'ont pas de champ `garantie_mois` | ✅ oui, si c'est **suivi** (versionnage, § 10.7) |
| **③ Champ optionnel** | `remise` n'existe que sur les produits soldés | ✅ oui - mieux qu'une colonne à `NULL` |
| **④ Incohérence subie** | `prix` tantôt `Decimal128`, tantôt `Double`, tantôt `"89.90"` | ❌ **non** - c'est une dette, à détecter et corriger |

Les trois premières sont des fonctionnalités. La quatrième est un bug silencieux : rappelez-vous l'étape 07, un prix stocké en chaîne est **ignoré** par `{"prix": {"$lt": 100}}`, sans la moindre erreur.

> **La règle qui résume l'étape** : la souplesse s'applique aux champs **spécifiques**. Le **noyau commun** - les champs dont tout le code dépend - doit être garanti par une validation côté serveur.

---

## 10.2 Auditer une collection : que contient-elle vraiment ?

Avant de coder, on regarde. C'est le premier réflexe quand on reprend une base MongoDB existante.

### À faire - `auditer.py`

```python
"""Dresse l'inventaire des champs réellement présents dans une collection."""
from db import get_db

db = get_db()
collection = db.produits
total = collection.count_documents({})

pipeline = [
    {"$project": {"champs": {"$objectToArray": "$$ROOT"}}},
    {"$unwind": "$champs"},
    {"$group": {
        "_id": "$champs.k",
        "presents": {"$sum": 1},
        "types": {"$addToSet": {"$type": "$champs.v"}},
    }},
    {"$sort": {"presents": -1}},
]

print(f"{total} documents\n")
print(f"{'champ':<22}{'présence':>10}  types")
print("-" * 60)
for ligne in collection.aggregate(pipeline):
    taux = 100 * ligne["presents"] / total
    alerte = "  ⚠️ plusieurs types" if len(ligne["types"]) > 1 else ""
    print(f"{ligne['_id']:<22}{taux:>9.0f}%  {', '.join(sorted(ligne['types']))}{alerte}")
```

```bash
python auditer.py
```

Sortie typique sur notre collection :

```
9 documents

champ                   présence  types
------------------------------------------------------------
_id                         100%  objectId, string
sku                         100%  string
nom                         100%  string
prix                        100%  decimal, double    ⚠️ plusieurs types
categorie                   100%  string
stock                        78%  int
tags                         56%  array
pouces                       22%  int
auteur                       11%  string
```

### Comment lire ce tableau

- **100 %** → champ du noyau commun : votre code peut s'appuyer dessus (et la validation doit l'exiger).
- **Entre 20 et 80 %** → champ spécifique à une famille, ou optionnel : `.get()` obligatoire à la lecture.
- **⚠️ plusieurs types** → à investiguer immédiatement. Ici, `prix` mélange `decimal` et `double`, héritage de l'étape 04 (mongosh) et de l'étape 06 (Python). `_id` mélange `objectId` et `string` parce qu'on a choisi un `_id` métier pour le livre - celui-là est volontaire.

> **Raccourci graphique** : dans MongoDB Compass, l'onglet **Schema** d'une collection produit cette analyse visuellement, avec la distribution des valeurs. Sur Atlas, le Data Explorer fait de même. Gardez quand même le script : il tourne en CI.

---

## 10.3 Les quatre façons dont deux documents peuvent différer

```python
{"sku": "A", "remise": 10}      # ① le champ existe et a une valeur
{"sku": "B", "remise": None}    # ② le champ existe et vaut null
{"sku": "C"}                    # ③ le champ n'existe pas
{"sku": "D", "remise": "10%"}   # ④ le champ existe, mais dans un autre type
```

Comment les distinguer en requête :

| Vous voulez… | Filtre |
|---|---|
| les documents où `remise` vaut 10 | `{"remise": 10}` |
| ceux où le champ est **absent** | `{"remise": {"$exists": False}}` |
| ceux où il existe et vaut `null` | `{"remise": {"$type": "null"}}` |
| ceux où il existe, quelle que soit la valeur | `{"remise": {"$exists": True}}` |
| ceux où il est absent **ou** null | `{"remise": None}` ⚠️ |
| ceux d'un type précis | `{"remise": {"$type": "int"}}` |
| ceux d'un type **inattendu** | `{"remise": {"$exists": True, "$not": {"$type": "int"}}}` |

### ⚠️ Le piège fondateur : `{"champ": None}`

**`{"remise": None}` retourne les documents ② ET ③** - ceux où le champ vaut `null` et ceux où il est absent. C'est le comportement documenté de MongoDB, et c'est la source d'erreurs la plus fréquente chez les débutants.

```python
db.produits.count_documents({"remise": None})               # absents + null
db.produits.count_documents({"remise": {"$exists": False}}) # seulement les absents
db.produits.count_documents({"remise": {"$type": "null"}})  # seulement les null
```

**Conseil de conception** : choisissez une convention et tenez-la. La plus simple : **"un champ sans valeur n'est pas écrit"** - on n'écrit jamais `null`. Le `$unset` remplace alors l'affectation à `null`, et `$exists` devient votre seul test.

---

## 10.4 Les types mixtes, et comment MongoDB les compare

MongoDB accepte n'importe quel type dans n'importe quel champ. Quand il doit comparer ou trier des valeurs de types différents, il applique un **ordre entre les types** (grossièrement : `null` < nombres < chaînes < objets < tableaux < booléens < dates < ObjectId).

Trois conséquences très concrètes :

1. **Les types numériques sont comparables entre eux.** `Int32`, `Int64`, `Double` et `Decimal128` se comparent correctement : `{"prix": {"$lt": 100}}` fonctionne sur un mélange de `Double` et `Decimal128`.
2. **Une chaîne n'est jamais comparée à un nombre.** `{"prix": {"$lt": 100}}` **ignore purement et simplement** un document dont le prix vaut `"89.90"`. Pas d'erreur, pas d'avertissement : juste un document qui n'apparaît pas dans les résultats. C'est la panne la plus difficile à diagnostiquer de MongoDB.
3. **Un tri sur un champ aux types mixtes regroupe par type**, ce qui donne un ordre déroutant.

### Détecter

```python
for type_bson in ["double", "decimal", "int", "long", "string", "null"]:
    n = db.produits.count_documents({"prix": {"$type": type_bson}})
    if n:
        print(f"prix en {type_bson:<9}: {n}")
```

### Corriger - `migrer.py`

Uniformisons les prix en `Decimal128`, à l'aide d'un pipeline de mise à jour (MongoDB ≥ 4.2) qui convertit **côté serveur** :

```python
"""Migration : uniformise le champ prix en Decimal128."""
from db import get_db

db = get_db()

avant = db.produits.count_documents({"prix": {"$exists": True, "$not": {"$type": "decimal"}}})
print("documents à migrer :", avant)

resultat = db.produits.update_many(
    {"prix": {"$exists": True, "$not": {"$type": "decimal"}}},
    [{"$set": {"prix": {"$toDecimal": "$prix"}}}],       # 👈 pipeline, pas un simple $set
)
print("migrés :", resultat.modified_count)

restants = db.produits.count_documents({"prix": {"$exists": True,
                                                 "$not": {"$type": "decimal"}}})
print("restants :", restants)      # doit valoir 0
```

```bash
python migrer.py && python auditer.py     # le ⚠️ sur prix doit avoir disparu
```

Trois qualités de ce script, à reproduire dans toutes vos migrations :

- il **cible** les documents à corriger (il ne réécrit pas toute la collection) ;
- il est **réexécutable** : relancé, il ne trouve plus rien à faire ;
- il **vérifie** son résultat, ce qui permet de le faire tourner en CI.

> `$toDecimal` échoue sur une valeur inconvertible (`"gratuit"`). Pour un jeu de données douteux, utilisez `$convert` avec `onError` :
> ```python
> [{"$set": {"prix": {"$convert": {"input": "$prix", "to": "decimal", "onError": None}}}}]
> ```
> puis traitez à la main les documents restés à `null`.

---

## 10.5 Écrire du code de lecture qui ne casse pas

Rappel de l'étape 07, complété par l'outil qu'on utilise en vrai projet : **Pydantic**.

```python
from datetime import datetime
from typing import Any

from bson import Decimal128
from pydantic import BaseModel, ConfigDict, Field, field_validator


class Produit(BaseModel):
    """Le noyau commun, garanti. Le reste va dans `specifique`."""
    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)

    id: Any = Field(alias="_id")
    sku: str
    nom: str
    categorie: str
    prix: float
    stock: int | None = None            # None = "non géré en stock"
    tags: list[str] = []
    cree_le: datetime | None = None
    specifique: dict[str, Any] = {}

    @field_validator("prix", mode="before")
    @classmethod
    def _prix(cls, v):                  # tolère Decimal128, float, int et chaîne
        if isinstance(v, Decimal128):
            return float(v.to_decimal())
        return float(v)

    @classmethod
    def depuis_mongo(cls, doc: dict) -> "Produit":
        connus = set(cls.model_fields) | {"_id"}
        specifique = {k: v for k, v in doc.items()
                      if k not in connus and k not in {"supprime_le", "schema_version"}}
        return cls(**{**doc, "specifique": specifique})


for doc in db.produits.find():
    produit = Produit.depuis_mongo(doc)
    print(produit.nom, produit.stock, produit.specifique)
```

Ce que ce modèle apporte :

- il **échoue bruyamment** si un document ne respecte pas le noyau commun - bien mieux qu'un `KeyError` trois écrans plus loin ;
- il **absorbe** l'hétérogénéité utile : les champs spécifiques atterrissent dans `specifique`, sans être perdus ;
- il **normalise les types** (`Decimal128` ou `float` → `float`) en un seul endroit ;
- au-delà de cette frontière, le reste du code manipule des objets de forme connue, et n'écrit plus un seul `.get()`.

---

## 10.6 Poser des garde-fous : la validation JSON Schema

Le schéma n'a pas disparu, il est dans votre code - sauf si vous demandez au serveur de le faire respecter. C'est le rôle de la **validation JSON Schema**, et c'est ce qui sépare une collection maîtrisée d'un dépotoir.

### À faire - `provision.py`

```python
"""Crée la collection produits avec sa validation et ses index. Réexécutable."""
from pymongo import ASCENDING, DESCENDING, IndexModel

from db import get_db

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
        "additionalProperties": True,      # 👈 la souplesse reste possible
    }
}

# Contraintes propres à certaines familles : un écran DOIT avoir pouces et resolution
REGLES_FAMILLES = {
    "$or": [
        {"categorie": {"$ne": "ecran"}},
        {"$and": [{"pouces": {"$type": "int"}}, {"resolution": {"$type": "string"}}]},
    ]
}

VALIDATOR = {"$and": [NOYAU_COMMUN, REGLES_FAMILLES]}


def provisionner() -> None:
    db = get_db()
    if "produits" not in db.list_collection_names():
        db.create_collection("produits", validator=VALIDATOR)
        print("collection créée")
    else:
        db.command("collMod", "produits", validator=VALIDATOR,
                   validationLevel="moderate", validationAction="warn")
        print("validation mise à jour (moderate/warn)")

    db.produits.create_indexes([
        IndexModel([("sku", ASCENDING)], unique=True, name="uniq_sku"),
        IndexModel([("categorie", ASCENDING), ("prix", DESCENDING)], name="cat_prix"),
    ])
    print("index en place :", [i["name"] for i in db.produits.list_indexes()])


if __name__ == "__main__":
    provisionner()
```

### Les deux réglages qui comptent

| Réglage | Valeurs | Effet |
|---|---|---|
| `validationLevel` | `strict` *(défaut)* / `moderate` / `off` | `moderate` n'applique la règle qu'aux **nouveaux** documents et à ceux **déjà valides** : les vieux documents invalides peuvent encore être modifiés |
| `validationAction` | `error` *(défaut)* / `warn` | `warn` **accepte** l'écriture et se contente de journaliser |

**La stratégie de déploiement d'une validation sur une collection existante**, en trois temps :

1. `moderate` + `warn` → on observe les journaux du serveur sans rien casser ;
2. on migre les documents non conformes (§ 10.4) ;
3. `strict` + `error` → la règle devient une garantie.

Passer directement en `strict`/`error` sur une collection existante, c'est provoquer des erreurs d'écriture en production sur des documents dont on ignorait l'existence.

### Ce que voit l'application

```python
from pymongo.errors import WriteError

try:
    db.produits.insert_one({"sku": "mauvais", "nom": "X"})
except WriteError as exc:
    print("code", exc.code)                      # 121 = échec de validation
    print(exc.details["errInfo"]["details"])     # le détail : quel champ, quelle règle
```

Le champ `errInfo.details` indique précisément la règle violée : c'est ce qu'il faut remonter dans les logs, pas seulement "écriture refusée".

> **À noter** : `additionalProperties: True` est volontaire. On impose le noyau commun et on **laisse la liberté** sur les champs spécifiques. Mettre `False` transformerait MongoDB en base relationnelle rigide - et vous perdriez tout l'intérêt du modèle.

---

## 10.7 Faire évoluer le schéma sans interruption : `schema_version`

Le jour où la forme d'un document doit changer (renommer un champ, transformer une chaîne en tableau, découper un objet), la migration "stop the world" - arrêter l'application, migrer, redémarrer - est rarement acceptable. MongoDB permet mieux : **le versionnage de schéma**.

On ajoute un champ `schema_version` dans chaque document :

```python
{"sku": "KBD-0010", "nom": "Clavier", "schema_version": 2, ...}
```

Et le code sait lire **toutes** les versions, mais n'écrit que la dernière :

```python
VERSION_COURANTE = 2

def migrer_en_memoire(doc: dict) -> dict:
    """Amène un document à la version courante, sans écrire en base."""
    version = doc.get("schema_version", 1)

    if version < 2:
        # v1 → v2 : le champ `libelle` devient `nom`, `tags` devient une liste
        doc["nom"] = doc.pop("libelle", doc.get("nom", ""))
        if isinstance(doc.get("tags"), str):
            doc["tags"] = [t.strip() for t in doc["tags"].split(",") if t.strip()]
        doc["schema_version"] = 2

    return doc


def lire(sku: str) -> dict:
    doc = db.produits.find_one({"sku": sku})
    return migrer_en_memoire(doc) if doc else None
```

Trois stratégies de migration, à choisir selon le volume :

| Stratégie | Principe | Quand |
|---|---|---|
| **Paresseuse (*lazy*)** | on migre un document quand on le lit (ou à sa prochaine écriture) | grosses collections, migration progressive et gratuite |
| **En arrière-plan** | un script parcourt les documents `schema_version < N` par tranches | quand on veut en finir, sans bloquer |
| **En une passe** | `update_many` sur toute la collection | petites collections, hors production |

```python
# Migration en arrière-plan, par tranches, réexécutable
while db.produits.count_documents({"schema_version": {"$lt": 2}}) > 0:
    lot = list(db.produits.find({"schema_version": {"$lt": 2}}).limit(500))
    db.produits.bulk_write([
        ReplaceOne({"_id": d["_id"]}, migrer_en_memoire(d)) for d in lot
    ], ordered=False)
```

C'est **le** pattern qui rend le schéma souple exploitable en production. Sans lui, la souplesse devient de l'archéologie.

---

## 10.8 Quand les attributs sont vraiment imprévisibles : le pattern *Attribute*

Si vos produits ont des dizaines d'attributs spécifiques et que vous devez pouvoir chercher sur n'importe lequel, ne les mettez pas en champs de premier niveau : il faudrait un index par champ.

```json
{
  "sku": "SCR-0021",
  "nom": "Ecran 27 pouces QHD",
  "attributs": [
    { "k": "pouces", "v": 27 },
    { "k": "resolution", "v": "2560x1440" },
    { "k": "hz", "v": 144 }
  ]
}
```

Un **seul** index composé couvre alors toutes les recherches d'attributs :

```python
db.produits.create_index([("attributs.k", 1), ("attributs.v", 1)], name="attributs")

db.produits.find({"attributs": {"$elemMatch": {"k": "hz", "v": {"$gte": 120}}}})
```

L'alternative moderne est l'**index wildcard**, qui indexe tout un sous-document :

```python
db.produits.create_index({"caracteristiques.$**": 1}, name="wildcard_carac")
```

Deux outils pour le même problème ; le pattern *Attribute* reste plus prévisible en performance.

---

## Exercice (20 min)

1. Lancez `auditer.py`. Repérez les champs présents à 100 %, ceux qui sont spécifiques, et les éventuels types mixtes.
2. Ajoutez `schema_version: 1` à tous les documents qui ne l'ont pas.
3. Exécutez `provision.py` en `moderate`/`warn`, puis tentez d'insérer un produit invalide (SKU mal formé). Que se passe-t-il ? Passez en `strict`/`error` et réessayez.
4. Écrivez une migration qui transforme le champ `resolution` (`"2560x1440"`) en sous-document `{"largeur": 2560, "hauteur": 1440}`, en passant les écrans en `schema_version: 2`.
5. Réfléchissez : quelle convention adoptez-vous pour un produit sans stock - champ absent, `null`, ou `0` ? Justifiez.

<details>
<summary>Voir la correction</summary>

```python
from pymongo import ReplaceOne
from db import get_db

db = get_db()

# 2
db.produits.update_many({"schema_version": {"$exists": False}},
                        {"$set": {"schema_version": 1}})

# 3 - en moderate/warn : l'insertion PASSE, un avertissement part dans les logs serveur.
#     En strict/error : WriteError code 121, l'insertion est refusée.
db.command("collMod", "produits", validationLevel="strict", validationAction="error")

# 4
ecrans = list(db.produits.find({"categorie": "ecran", "resolution": {"$type": "string"}}))
operations = []
for e in ecrans:
    largeur, _, hauteur = e["resolution"].partition("x")
    e["resolution"] = {"largeur": int(largeur), "hauteur": int(hauteur)}
    e["schema_version"] = 2
    operations.append(ReplaceOne({"_id": e["_id"]}, e))
if operations:
    print(db.produits.bulk_write(operations, ordered=False).modified_count, "écrans migrés")
```

**Attention** : cette migration doit être précédée d'un déploiement du code qui sait lire **les deux formes** (chaîne et sous-document). Sinon, pendant les quelques secondes de la migration, l'application plante sur les documents déjà convertis. C'est tout l'objet du § 10.7.

**Question 5 - il n'y a pas une seule bonne réponse, mais une bonne méthode.** Les trois conventions sont défendables, à condition d'être explicites :

- **champ absent** : "le stock ne s'applique pas à ce produit" (un abonnement). Se teste avec `$exists`, ne fausse aucune agrégation, ne consomme pas de place. C'est la convention retenue dans ce cours.
- **`0`** : "produit géré en stock, actuellement en rupture". Sémantiquement différent du précédent - et c'est bien pour cela qu'il ne faut pas les confondre.
- **`null`** : "on devrait avoir la valeur, on ne l'a pas" (import incomplet). Utile pour tracer une donnée manquante, mais rappelez-vous que `{"stock": None}` matche aussi les documents sans le champ.

Le vrai risque n'est pas de mal choisir : c'est que trois développeurs choisissent trois conventions différentes dans la même collection. **Écrivez la convention dans le README du projet, et faites-la respecter par la validation.**

</details>

---

## ✅ Ce qu'il faut retenir

1. Les documents diffèrent pour quatre raisons : famille métier, évolution, champ optionnel (les trois saines) et **incohérence subie** (à corriger).
2. **Auditez avant de coder** : `$objectToArray` + `$group` donne la présence et les types réels de chaque champ.
3. `{"champ": None}` matche aussi les documents **sans le champ** ; `$exists` et `$type` sont vos outils de précision.
4. Un champ dans un type inattendu est **silencieusement ignoré** par les filtres - le bug le plus coûteux du modèle.
5. Verrouillez le **noyau commun** par une validation JSON Schema (`additionalProperties: true`), déployée en `moderate`/`warn` puis durcie en `strict`/`error`.
6. Faites évoluer le schéma avec `schema_version` + une migration paresseuse ou par tranches : le code lit toutes les versions, n'écrit que la dernière.

→ **[Étape 11 - Modéliser en documentaire](11-modeliser.md)**
