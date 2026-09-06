[← Étape 07](07-crud-lire.md) · [Sommaire](README.md) · [Étape suivante →](09-crud-supprimer.md)

# Étape 08 - CRUD 3/4 : Modifier

> 🎯 **Objectif** : modifier des documents avec les bons opérateurs, comprendre `upsert`, manipuler des tableaux, et savoir quand `replace_one` est dangereux.
> ⏱️ **Durée** : 60 minutes.
> 📁 **On crée** : `boutique/modifier.py`.

---

## 8.1 `update_one` - la forme de base

```python
from db import get_db

db = get_db()

resultat = db.produits.update_one(
    {"sku": "KBD-0010"},                                  # 1. QUI : le filtre
    {"$set": {"nom": "Clavier TKL silencieux (v2)"},      # 2. QUOI : les opérateurs
     "$inc": {"stock": -1},
     "$currentDate": {"maj_le": True}},
)

print(resultat.matched_count, resultat.modified_count)     # 1 1
```

Une mise à jour a toujours deux parties : **le filtre** (les mêmes opérateurs qu'à l'étape 07) et **les modifications**, exprimées avec des opérateurs `$`.

`update_one` ne modifie **qu'un seul document**, même si le filtre en matche plusieurs - le premier trouvé.

### ⚠️ Les trois erreurs à connaître

**1. Oublier l'opérateur.**

```python
db.produits.update_one({"sku": "KBD-0010"}, {"nom": "Nouveau nom"})
# → WriteError: Update document requires atomic operators
```

Une mise à jour est **partielle** : sans `$set`, MongoDB ne sait pas si vous voulez modifier un champ ou remplacer tout le document. Pour remplacer, c'est `replace_one` (§ 8.6).

**2. Confondre `matched_count` et `modified_count`.**

```python
res = db.produits.update_one({"sku": "KBD-0010"}, {"$set": {"stock": 8}})
# Si le stock valait déjà 8 : matched_count = 1, modified_count = 0
```

| Attribut | Répond à la question |
|---|---|
| `matched_count` | le document existe-t-il ? |
| `modified_count` | quelque chose a-t-il réellement changé ? |
| `upserted_id` | un document a-t-il été créé ? (voir § 8.4) |

Pour signaler "produit introuvable" à l'utilisateur, testez `matched_count`, jamais `modified_count`.

**3. Croire qu'un filtre vide est sans danger.**

```python
db.produits.update_many({}, {"$set": {"actif": True}})   # touche TOUS les documents
```

C'est parfois exactement ce qu'on veut (§ 8.5), mais dans un script écrit à la va-vite, c'est un accident.

---

## 8.2 Les opérateurs de mise à jour

| Opérateur | Effet | Exemple |
|---|---|---|
| `$set` | définir un champ (le crée s'il n'existe pas) | `{"$set": {"prix": Decimal128("99.00")}}` |
| `$unset` | supprimer un champ | `{"$unset": {"promo": ""}}` |
| `$inc` | incrémenter (ou décrémenter) | `{"$inc": {"stock": -1, "vues": 1}}` |
| `$mul` | multiplier | `{"$mul": {"prix": 0.9}}` |
| `$min` / `$max` | n'écrire que si plus petit / plus grand | `{"$max": {"record": 42}}` |
| `$rename` | renommer un champ | `{"$rename": {"libelle": "nom"}}` |
| `$currentDate` | horodater | `{"$currentDate": {"maj_le": True}}` |
| `$push` | ajouter à un tableau | `{"$push": {"avis": {...}}}` |
| `$addToSet` | ajouter sans doublon | `{"$addToSet": {"tags": "promo"}}` |
| `$pull` | retirer d'un tableau | `{"$pull": {"tags": "promo"}}` |
| `$pop` | retirer le premier (`-1`) ou le dernier (`1`) | `{"$pop": {"avis": -1}}` |

### Le comportement qui étonne : les champs absents

```python
# L'abonnement n'a PAS de champ tags
db.produits.update_one({"sku": "ABO-0013"}, {"$addToSet": {"tags": "service"}})
# → le tableau est créé avec l'élément dedans

# Le livre n'a PAS de champ stock
db.produits.update_one({"sku": "LIV-0014"}, {"$inc": {"stock": 5}})
# → le champ est créé à 5 (0 + 5)
```

`$set`, `$inc`, `$push` et `$addToSet` **créent le champ** s'il est absent. C'est ce qui rend les évolutions de schéma triviales en MongoDB… et ce qui permet aussi de créer discrètement des incohérences : rien ne vous empêche d'ajouter `stock` à un abonnement, où le concept n'a pas de sens.

---

## 8.3 `update_many` - modifier en masse

```python
resultat = db.produits.update_many(
    {"categorie": "clavier"},
    {"$addToSet": {"tags": "promo"}, "$mul": {"prix": 0.9}},
)
print(f"{resultat.modified_count} claviers en promotion")
```

C'est l'outil des évolutions de schéma. Exemple typique : ajouter un champ à tous les documents qui ne l'ont pas encore.

```python
db.produits.update_many(
    {"actif": {"$exists": False}},     # 👈 seulement ceux à qui il manque
    {"$set": {"actif": True}},
)
```

> **`update_many` n'est pas atomique dans son ensemble.** Chaque document est modifié atomiquement, mais un lecteur concurrent peut voir un état intermédiaire - certains documents modifiés, d'autres non. Pour une atomicité globale, il faut une transaction (survolée à l'étape 13), qui exige un replica set.

---

## 8.4 `upsert` - modifier, ou créer si absent

```python
resultat = db.produits.update_one(
    {"sku": "NEW-0099"},
    {"$set": {"nom": "Produit tout neuf", "categorie": "divers"},
     "$setOnInsert": {"cree_le": datetime.now(timezone.utc)}},
    upsert=True,
)
print(resultat.upserted_id)     # ObjectId si créé, None si simplement mis à jour
```

Le document créé est composé **du filtre d'égalité + des opérateurs** : le `sku` du filtre se retrouve donc dans le document, sans qu'on ait à le répéter.

**`$setOnInsert` n'est appliqué qu'à la création.** C'est ce qui permet à un import réexécutable de ne pas écraser la date de création à chaque passage - vous l'avez déjà utilisé dans `seed.py`.

> ⚠️ **Un upsert avec un filtre non trivial peut créer des documents inattendus.** `update_one({"prix": {"$lt": 100}}, {"$set": {...}}, upsert=True)` sur une collection vide crée un document **sans prix** : seules les égalités du filtre sont reprises. Un upsert se fait sur une clé d'identité (`sku`, `_id`, e-mail), jamais sur un critère de recherche.

---

## 8.5 Modifier des tableaux

```python
from datetime import datetime, timezone

# Ajouter un avis
db.produits.update_one(
    {"sku": "KBD-0010"},
    {"$push": {"avis": {"auteur": "alice", "note": 5, "texte": "Parfait",
                        "date": datetime.now(timezone.utc)}}},
)

# Ajouter un tag sans créer de doublon
db.produits.update_one({"sku": "KBD-0010"}, {"$addToSet": {"tags": "best-seller"}})

# Retirer un tag
db.produits.update_one({"sku": "KBD-0010"}, {"$pull": {"tags": "promo"}})
```

### Garder une liste bornée (pattern *Subset*)

Un tableau qui grossit sans limite finit par heurter les 16 Mo du document - et ralentit chaque lecture bien avant. On garde les N derniers éléments :

```python
db.produits.update_one(
    {"sku": "KBD-0010"},
    {"$push": {"avis": {
        "$each": [{"auteur": "bob", "note": 4, "date": datetime.now(timezone.utc)}],
        "$sort": {"date": -1},     # les plus récents d'abord
        "$slice": 10,              # on n'en garde que 10
    }}},
)
```

### Modifier un élément précis d'un tableau

```python
# Marquer tous les avis dont la note est ≤ 2
db.produits.update_one(
    {"sku": "KBD-0010"},
    {"$set": {"avis.$[a].signale": True}},
    array_filters=[{"a.note": {"$lte": 2}}],
)
```

`$[a]` désigne "chaque élément qui satisfait le filtre nommé `a`". Sans `array_filters`, on ne peut modifier que le **premier** élément trouvé, avec l'opérateur positionnel `$`.

---

## 8.6 `replace_one` - remplacer tout le document

```python
db.produits.replace_one(
    {"sku": "MSE-0012"},
    {"sku": "MSE-0012", "nom": "Souris verticale MK2", "categorie": "souris",
     "prix": Decimal128("84.00"), "stock": 10},
)
```

`replace_one` **remplace intégralement** le contenu, sauf l'`_id`. Tous les champs absents du nouveau document **disparaissent** : ici, `poids_g`, `sans_fil` et `cree_le` sont perdus.

| | `update_one` + `$set` | `replace_one` |
|---|---|---|
| Analogie HTTP | `PATCH` | `PUT` |
| Champs non mentionnés | conservés | **supprimés** |
| Usage typique | 99 % des cas | import d'un document complet venu d'ailleurs |

### ⚠️ Le piège du "lire, modifier, réécrire"

```python
# ❌ Écrase les modifications faites par quelqu'un d'autre entre-temps
doc = db.produits.find_one({"sku": "KBD-0010"})
doc["prix"] = Decimal128("109.00")
db.produits.replace_one({"sku": "KBD-0010"}, doc)
```

Entre la lecture et l'écriture, un autre processus a pu changer le stock : votre réécriture le remet à la valeur que vous aviez lue. C'est le *lost update*, et il est invisible en test à un seul utilisateur.

Deux solutions :

```python
# ✅ Solution 1 : ne modifier que le champ concerné
db.produits.update_one({"sku": "KBD-0010"}, {"$set": {"prix": Decimal128("109.00")}})

# ✅ Solution 2 : verrouillage optimiste, si vous devez vraiment remplacer
res = db.produits.replace_one(
    {"_id": doc["_id"], "version": doc["version"]},
    {**nouveau, "version": doc["version"] + 1},
)
if res.matched_count == 0:
    raise RuntimeError("le document a été modifié entre-temps")
```

---

## 8.7 `find_one_and_update` - lire et modifier atomiquement

```python
from pymongo import ReturnDocument

doc = db.compteurs.find_one_and_update(
    {"_id": "commandes"},
    {"$inc": {"seq": 1}},
    upsert=True,
    return_document=ReturnDocument.AFTER,     # ou BEFORE (défaut)
)
numero_commande = doc["seq"]
```

C'est **la** primitive à connaître pour tout ce qui ressemble à un compteur, une réservation ou une file de tâches. Elle remplace le classique "je lis, je décide, j'écris" qui perd des mises à jour dès qu'il y a deux utilisateurs.

L'exemple qui parle à tout le monde - réserver du stock sans jamais passer sous zéro, **sans transaction** :

```python
produit = db.produits.find_one_and_update(
    {"sku": "KBD-0010", "stock": {"$gte": 2}},    # 👈 la condition est DANS le filtre
    {"$inc": {"stock": -2}},
    return_document=ReturnDocument.AFTER,
)
if produit is None:
    raise ValueError("stock insuffisant")
print("stock restant :", produit["stock"])
```

Le secret est là : **la condition métier fait partie du filtre**. Si deux clients tentent la même réservation en même temps, un seul verra son filtre matcher - l'autre obtient `None`. Un document est toujours modifié atomiquement, quelle que soit sa profondeur ; c'est la garantie la plus utile de MongoDB.

Variantes : `find_one_and_replace`, `find_one_and_delete`.

---

## Exercice (20 min)

1. Augmentez de 10 % le prix de tous les écrans (attention aux types : `$mul` sur un `Decimal128` fonctionne, sur une chaîne non).
2. Ajoutez le champ `actif: True` **uniquement** aux produits qui ne l'ont pas.
3. Ajoutez deux avis au clavier `KBD-0010`, en ne conservant que les 3 plus récents.
4. Écrivez `reserver(sku, quantite)` qui décrémente le stock de façon atomique et lève une exception si le stock est insuffisant **ou** si le produit n'est pas géré en stock (champ absent).
5. Renommez le champ `hz` en `frequence_hz` sur tous les écrans.

<details>
<summary>Voir la correction</summary>

```python
from datetime import datetime, timezone
from pymongo import ReturnDocument
from db import get_db

db = get_db()

# 1
db.produits.update_many({"categorie": "ecran"}, {"$mul": {"prix": 1.10}})

# 2
db.produits.update_many({"actif": {"$exists": False}}, {"$set": {"actif": True}})

# 3
db.produits.update_one(
    {"sku": "KBD-0010"},
    {"$push": {"avis": {
        "$each": [
            {"auteur": "alice", "note": 5, "date": datetime.now(timezone.utc)},
            {"auteur": "bob",   "note": 4, "date": datetime.now(timezone.utc)},
        ],
        "$sort": {"date": -1},
        "$slice": 3,
    }}},
)

# 4
def reserver(sku: str, quantite: int) -> dict:
    doc = db.produits.find_one_and_update(
        {"sku": sku, "stock": {"$gte": quantite}},
        {"$inc": {"stock": -quantite}},
        return_document=ReturnDocument.AFTER,
    )
    if doc is None:
        # deux causes possibles : stock insuffisant, ou champ stock absent
        existe = db.produits.count_documents({"sku": sku}) == 1
        raise ValueError("stock insuffisant" if existe else "produit inconnu")
    return doc

# 5
db.produits.update_many({"hz": {"$exists": True}}, {"$rename": {"hz": "frequence_hz"}})
```

**Le point de la question 4** : `find_one_and_update` ne peut pas distinguer "produit inconnu", "stock insuffisant" et "pas de champ stock" - dans les trois cas, le filtre ne matche pas et vous obtenez `None`. Si vous devez donner un message précis, faites une **seconde requête de diagnostic**, seulement dans le cas d'échec. Ne renversez jamais la logique en vérifiant *avant* : ce serait rouvrir la fenêtre de concurrence que `find_one_and_update` vient justement de fermer.

**Le point de la question 5** : `$rename` ne touche que les documents où le champ existe - les claviers et les livres ne sont pas concernés. Après cette opération, si une partie de votre code cherche encore `hz`, elle ne trouvera plus rien, silencieusement. **Toute renommage de champ en production se fait en trois temps** : (1) l'application écrit et lit les deux noms, (2) on migre les documents existants, (3) on retire l'ancien nom du code. C'est le sujet de l'étape suivante sur le schéma souple.

</details>

---

## ✅ Ce qu'il faut retenir

1. Une mise à jour = un **filtre** + des **opérateurs** (`$set`, `$inc`, `$push`…). Sans opérateur : erreur.
2. `matched_count` répond "le document existe-t-il ?", `modified_count` "a-t-il changé ?".
3. `$set`, `$inc`, `$addToSet` **créent** les champs absents : c'est ainsi qu'on fait évoluer un schéma.
4. `upsert=True` + `$setOnInsert` = l'idiome de l'import réexécutable ; on n'upsert que sur une clé d'identité.
5. `replace_one` supprime les champs non fournis ; préférez `$set`, sinon utilisez un verrouillage optimiste.
6. `find_one_and_update` avec la **condition métier dans le filtre** rend une opération atomique sans transaction.

→ **[Étape 09 - CRUD 4/4 : Supprimer et écrire en lot](09-crud-supprimer.md)**
