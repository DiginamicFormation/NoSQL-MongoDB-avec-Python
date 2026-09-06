[← Étape 06](06-crud-creer.md) · [Sommaire](README.md) · [Étape suivante →](08-crud-modifier.md)

# Étape 07 - CRUD 2/4 : Lire

> 🎯 **Objectif** : interroger la base - filtres, projection, tri, pagination - et **lire sans planter des documents qui n'ont pas tous les mêmes champs**.
> ⏱️ **Durée** : 60 minutes.
> 📁 **On crée** : `boutique/lire.py`.
> 📋 **Prérequis** : le `seed.py` de l'étape 06 a été exécuté.

---

## 7.1 `find_one` - zéro ou un document

```python
from db import get_db

db = get_db()

produit = db.produits.find_one({"sku": "KBD-0010"})
if produit is None:
    raise LookupError("produit inconnu")

print(produit["nom"])
```

`find_one` renvoie un `dict` **ou `None`**. Il n'y a pas d'exception "not found" : le test explicite est votre responsabilité.

### Chercher par `_id`

```python
from bson import ObjectId
from bson.errors import InvalidId

produit = db.produits.find_one({"_id": ObjectId("66f0a1b2c3d4e5f600000001")})
```

> ⚠️ **Un `ObjectId` n'est pas une chaîne.** `find_one({"_id": "66f0a1b2c3d4e5f600000001"})` ne renvoie **rien**, sans erreur : vous comparez une chaîne à un `ObjectId`. Convertissez systématiquement à la frontière de votre application (API, formulaire, CLI) :
> ```python
> try:
>     oid = ObjectId(identifiant_recu)
> except InvalidId:
>     raise ValueError("identifiant invalide")
> ```

---

## 7.2 `find` - un curseur, pas une liste

```python
curseur = db.produits.find({"categorie": "clavier"})

for produit in curseur:
    print(produit["sku"], produit["nom"])
```

Un curseur est **paresseux** : les documents arrivent du serveur par lots, au fil de l'itération. Deux conséquences :

1. **Il s'épuise.** Une fois parcouru, il est vide - on ne peut pas le relire.
2. **`list(curseur)` charge tout en mémoire.** Acceptable sur 100 documents, fatal sur un million.

```python
tous = list(db.produits.find())                    # ⚠️ tout en RAM
extrait = list(db.produits.find().limit(20))       # ✅ borné explicitement
```

---

## 7.3 Les filtres

Un filtre est un **dictionnaire**. Plusieurs clés = **ET implicite**.

```python
db.produits.find({"categorie": "clavier", "stock": {"$gt": 0}})
```

### Les opérateurs du quotidien

| Besoin | Écriture |
|---|---|
| Égalité | `{"categorie": "clavier"}` |
| Différent | `{"categorie": {"$ne": "clavier"}}` |
| Comparaison | `{"prix": {"$lt": 100}}`, `$lte`, `$gt`, `$gte` |
| Encadrement | `{"prix": {"$gte": 50, "$lte": 200}}` |
| Dans une liste | `{"categorie": {"$in": ["clavier", "souris"]}}` |
| OU | `{"$or": [{"stock": 0}, {"actif": False}]}` |
| Champ présent / absent | `{"hz": {"$exists": True}}` / `{"$exists": False}` |
| Type d'un champ | `{"prix": {"$type": "decimal"}}` |
| Début de chaîne | `{"nom": {"$regex": "^Clavier"}}` |
| Comparer deux champs | `{"$expr": {"$gt": ["$stock", "$seuil"]}}` |

### Les tableaux

```python
db.produits.find({"tags": "clavier"})                       # contient cet élément
db.produits.find({"tags": {"$all": ["clavier", "rgb"]}})    # contient tous ceux-ci
db.produits.find({"tags": {"$size": 2}})                    # exactement 2 éléments
```

### Les sous-documents : la notation pointée

```python
db.commandes.find({"livraison.ville": "Lyon"})
db.commandes.find({"lignes.sku": "KBD-0010"})     # au moins une ligne avec ce sku
```

> ⚠️ **Le piège du tableau d'objets.** `{"lignes.sku": "KBD-0010", "lignes.quantite": {"$gte": 2}}` matche un document où *une* ligne a ce SKU et où *une autre*, éventuellement différente, a une quantité ≥ 2. Pour exiger que ce soit **le même élément** :
> ```python
> db.commandes.find({"lignes": {"$elemMatch": {"sku": "KBD-0010", "quantite": {"$gte": 2}}}})
> ```

---

## 7.4 Projection : ne rapatrier que l'utile

```python
db.produits.find(
    {"categorie": "clavier"},
    {"nom": 1, "prix": 1, "_id": 0},     # 1 = inclure, 0 = exclure
)
```

On ne mélange pas les deux modes dans une même projection - **sauf** pour retirer `_id`, qui est inclus par défaut.

Projeter réduit le trafic réseau et la mémoire Python. Sur une liste de 500 produits, ne rapatrier que trois champs au lieu du document entier change concrètement les temps de réponse.

---

## 7.5 Trier, limiter, paginer

```python
from pymongo import ASCENDING, DESCENDING

page = (db.produits.find({"categorie": "ecran"})
        .sort("prix", DESCENDING)
        .limit(10))

# Tri sur plusieurs champs
db.produits.find().sort([("categorie", ASCENDING), ("prix", DESCENDING)])
```

L'ordre d'écriture de `.sort()`, `.skip()` et `.limit()` n'a aucune importance : le serveur applique toujours **tri → saut → limite**.

### La pagination : évitez `skip`

```python
# ❌ Se dégrade page après page : le serveur parcourt puis jette les documents sautés
db.produits.find().sort("_id", ASCENDING).skip(10_000).limit(20)

# ✅ Pagination par curseur : coût constant
def page_suivante(dernier_id=None, taille=20):
    filtre = {"_id": {"$gt": dernier_id}} if dernier_id else {}
    return list(db.produits.find(filtre).sort("_id", ASCENDING).limit(taille))
```

La pagination par curseur est aussi **stable** : si des documents sont insérés pendant la navigation, vous ne verrez pas deux fois le même élément - ce qui arrive avec `skip`.

---

## 7.6 Compter et dédoublonner

```python
db.produits.count_documents({"categorie": "clavier"})   # exact : exécute la requête
db.produits.estimated_document_count()                  # instantané, mais approximatif
db.produits.distinct("categorie")                       # ['clavier', 'ecran', 'livre', ...]
```

| Méthode | Quand l'utiliser |
|---|---|
| `count_documents(filtre)` | quand le chiffre doit être juste - il **parcourt** réellement |
| `estimated_document_count()` | tableau de bord, ordre de grandeur ; **n'accepte aucun filtre** |
| `distinct(champ)` | listes de valeurs (facettes, menus déroulants) - attention aux collections énormes |

> ⚠️ N'appelez pas `count_documents({})` pour afficher un badge sur chaque page : sur une grosse collection, c'est un scan complet à chaque affichage.

---

## 7.7 Lire des documents hétérogènes sans planter

C'est **le** réflexe spécifique au NoSQL, et il concerne toutes vos lectures.

Votre collection contient des claviers (`switches`), des écrans (`pouces`, `hz`), un livre (`auteur`, `pages`) et un abonnement (ni `stock`, ni `tags`). Ce code semble raisonnable :

```python
for p in db.produits.find():
    print(p["nom"], p["stock"], p["tags"][0])     # 💥 KeyError sur l'abonnement
```

Il plante dès le premier document sans `stock`. **En documentaire, l'accès direct par crochets est un pari.** Quatre techniques, de la plus simple à la plus solide :

### ① `.get()` avec une valeur par défaut

```python
for p in db.produits.find():
    print(p["nom"], p.get("stock", 0), p.get("tags", []))
```

`_id` et les champs que vous imposez (via la validation de l'étape 10) sont les seuls sur lesquels vous pouvez compter aveuglément.

### ② Filtrer sur l'existence du champ

Ne lisez que les documents qui ont ce qui vous intéresse :

```python
# Les produits gérés en stock - l'abonnement est écarté par la requête elle-même
for p in db.produits.find({"stock": {"$exists": True}}):
    print(p["nom"], p["stock"])          # ici, l'accès direct est sûr
```

### ③ Demander au serveur de combler les trous

`$ifNull` fournit une valeur par défaut **côté serveur**, dans un pipeline d'agrégation :

```python
pipeline = [
    {"$project": {
        "_id": 0,
        "nom": 1,
        "stock": {"$ifNull": ["$stock", 0]},
        "nb_tags": {"$size": {"$ifNull": ["$tags", []]}},
    }}
]
for ligne in db.produits.aggregate(pipeline):
    print(ligne)          # tous les documents ont désormais la même forme
```

C'est la solution la plus propre quand la lecture alimente une API : la normalisation se fait une fois, au plus près des données.

### ④ Normaliser à l'entrée de l'application

```python
def normaliser(doc: dict) -> dict:
    """Ramène un document de forme quelconque à la forme attendue par l'application."""
    return {
        "id": str(doc["_id"]),
        "sku": doc.get("sku"),
        "nom": doc.get("nom", "(sans nom)"),
        "prix": float(doc["prix"].to_decimal()) if hasattr(doc.get("prix"), "to_decimal")
                else float(doc.get("prix", 0)),
        "stock": doc.get("stock"),                  # None = "non géré en stock"
        "tags": doc.get("tags", []),
        "specifique": {k: v for k, v in doc.items()
                       if k not in {"_id", "sku", "nom", "prix", "stock", "tags",
                                    "categorie", "cree_le"}},
    }

for p in db.produits.find():
    print(normaliser(p))
```

Notez le traitement du prix : il gère à la fois le `Decimal128` (documents créés en Python) et le `float` (documents créés dans mongosh à l'étape 04). **C'est le prix à payer d'une collection aux types mixtes** - et une bonne raison de les éviter, ou de migrer (étape 10).

> **La règle** : à la frontière entre la base et le reste de votre application, tout document doit passer par une fonction de normalisation - écrite à la main, ou un modèle Pydantic (étape 10). Au-delà de cette frontière, le code manipule des objets de forme connue et ne fait plus de `.get()`.

---

## 7.8 Le script complet de l'étape

### À faire - `lire.py`

```python
from pymongo import ASCENDING, DESCENDING

from db import get_db

db = get_db()

print("--- un produit ---")
print(db.produits.find_one({"sku": "KBD-0010"}, {"_id": 0, "nom": 1, "prix": 1}))

print("\n--- claviers en stock, du plus cher au moins cher ---")
for p in (db.produits.find({"categorie": "clavier", "stock": {"$gt": 0}},
                           {"_id": 0, "nom": 1, "prix": 1, "stock": 1})
          .sort("prix", DESCENDING)):
    print(f"  {p['nom']:<30} {p['prix']} € ({p['stock']} en stock)")

print("\n--- répartition ---")
print("catégories        :", db.produits.distinct("categorie"))
print("total             :", db.produits.count_documents({}))
print("sans champ stock  :", db.produits.count_documents({"stock": {"$exists": False}}))
print("avec champ hz     :", db.produits.count_documents({"hz": {"$exists": True}}))

print("\n--- pagination par curseur ---")
dernier = None
while True:
    lot = list(db.produits.find({"_id": {"$gt": dernier}} if dernier else {})
               .sort("_id", ASCENDING).limit(3))
    if not lot:
        break
    print("  page :", [p["sku"] for p in lot])
    dernier = lot[-1]["_id"]
```

```bash
python lire.py
```

---

## Exercice (20 min)

1. Affichez les produits de moins de 100 €, triés par prix croissant, avec seulement `sku`, `nom` et `prix`.
2. Comptez les produits qui possèdent le champ `stock`, puis ceux qui ne l'ont pas.
3. Listez les produits dont le champ `tags` contient `"clavier"` **et** dont le stock est strictement positif.
4. Écrivez une fonction `fiche(sku)` qui affiche un produit ligne par ligne, **quelle que soit sa forme** : les champs communs d'abord, puis les champs spécifiques à sa famille.
5. Question de réflexion : pourquoi `db.produits.find({"prix": {"$lt": 100}})` risque-t-il de ne pas renvoyer ce que vous croyez, dans notre collection ?

<details>
<summary>Voir la correction</summary>

```python
# 1
for p in db.produits.find({"prix": {"$lt": 100}}, {"_id": 0, "sku": 1, "nom": 1, "prix": 1}) \
                    .sort("prix", 1):
    print(p)

# 2
print(db.produits.count_documents({"stock": {"$exists": True}}))
print(db.produits.count_documents({"stock": {"$exists": False}}))

# 3
db.produits.find({"tags": "clavier", "stock": {"$gt": 0}})

# 4
COMMUNS = ["sku", "nom", "categorie", "prix", "stock", "tags", "cree_le"]

def fiche(sku: str) -> None:
    doc = db.produits.find_one({"sku": sku})
    if doc is None:
        print("introuvable"); return
    for champ in COMMUNS:
        if champ in doc:                      # 👈 on n'impose rien
            print(f"{champ:<12}: {doc[champ]}")
    specifiques = {k: v for k, v in doc.items() if k not in COMMUNS and k != "_id"}
    if specifiques:
        print("--- spécifique à la famille ---")
        for k, v in specifiques.items():
            print(f"{k:<12}: {v}")
```

**Question 5 - la bonne réponse.** Notre collection contient des prix en `Decimal128` (insérés depuis Python) et des prix en `Double` (insérés depuis mongosh à l'étape 04). MongoDB **sait comparer les types numériques entre eux**, donc la requête fonctionne ici. Mais si un prix avait été enregistré en **chaîne** (`"89.90"`), il serait totalement ignoré par ce filtre : en BSON, les chaînes ne sont pas comparables aux nombres, et le document est simplement écarté - **sans aucune erreur**.

Vérifiez ce qui existe vraiment dans votre collection :

```python
for t in ["double", "decimal", "int", "string"]:
    n = db.produits.count_documents({"prix": {"$type": t}})
    if n:
        print(f"prix en {t} : {n}")
```

C'est exactement le genre d'incohérence silencieuse que l'étape 10 apprend à détecter et à corriger.

</details>

---

## ✅ Ce qu'il faut retenir

1. `find_one` renvoie `None` s'il ne trouve rien ; `find` renvoie un **curseur** paresseux et non rejouable.
2. Convertissez toujours les identifiants en `ObjectId` - une chaîne ne matche jamais.
3. Projetez ce dont vous avez besoin ; paginez par curseur (`_id > dernier`) plutôt qu'avec `skip`.
4. **Ne supposez jamais qu'un champ existe** : `.get()`, filtre `$exists`, `$ifNull`, ou normalisation à l'entrée.
5. Un champ stocké dans un mauvais type est **ignoré** par les filtres, sans erreur : `$type` permet de le débusquer.

→ **[Étape 08 - CRUD 3/4 : Modifier](08-crud-modifier.md)**
