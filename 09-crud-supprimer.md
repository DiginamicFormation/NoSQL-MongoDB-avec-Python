[← Étape 08](08-crud-modifier.md) · [Sommaire](README.md) · [Étape suivante →](10-schema-souple.md)

# Étape 09 - CRUD 4/4 : Supprimer, et écrire en lot

> 🎯 **Objectif** : supprimer sans regret (et savoir pourquoi on supprime rarement pour de bon), puis écrire des lots efficacement avec `bulk_write`.
> ⏱️ **Durée** : 40 minutes.
> 📁 **On crée** : `boutique/supprimer.py`.

---

## 9.1 `delete_one` et `delete_many`

```python
from db import get_db

db = get_db()

resultat = db.produits.delete_one({"sku": "NEW-0099"})
print(resultat.deleted_count)          # 0 ou 1

resultat = db.produits.delete_many({"categorie": "divers"})
print(resultat.deleted_count)          # n
```

`delete_one` supprime **le premier document** qui matche - même si le filtre en matche cent. C'est une sécurité : pour en supprimer plusieurs, il faut le demander explicitement.

### Récupérer le document supprimé

```python
doc = db.produits.find_one_and_delete({"sku": "MSE-0012"})
if doc:
    print("supprimé :", doc["nom"])
    db.corbeille.insert_one(doc)        # on peut l'archiver au passage
```

### Vider ou détruire une collection

```python
db.produits.delete_many({})     # vide la collection : index et validation conservés
db.produits.drop()              # supprime la collection, ses index et sa validation
```

| | `delete_many({})` | `drop()` |
|---|---|---|
| Ce qui reste | la collection, ses index, sa validation | rien |
| Coût | proportionnel au nombre de documents | quasi instantané |
| Déclenche les change streams | oui, un événement par document | non (un seul événement `drop`) |

> ⚠️ **Le filtre vide.** `delete_many({})` supprime **tout**. Il n'y a ni confirmation, ni `WHERE` obligatoire, ni annulation. En script, prenez l'habitude d'écrire le filtre **avant** la méthode, et de tester d'abord avec `count_documents(filtre)`.

```python
filtre = {"stock": 0, "actif": False}
print("va supprimer :", db.produits.count_documents(filtre))   # on vérifie d'abord
# db.produits.delete_many(filtre)                              # puis on décommente
```

---

## 9.2 En production, on supprime rarement

Trois raisons : la traçabilité (qui a supprimé quoi), les références (d'autres documents pointent peut-être dessus - souvenez-vous : **pas de `FOREIGN KEY`, donc pas de garde-fou**), et le droit à l'erreur.

### La suppression logique (*soft delete*)

```python
from datetime import datetime, timezone

db.produits.update_one(
    {"sku": "LIV-0014"},
    {"$set": {"supprime_le": datetime.now(timezone.utc)}},
)
```

Toutes les lectures normales excluent alors ces documents :

```python
db.produits.find({"supprime_le": {"$exists": False}, "categorie": "livre"})
```

C'est simple, mais cela impose une discipline : **chaque requête doit penser à filtrer**. Pour ne pas l'oublier, centralisez vos lectures dans un dépôt (étape 13) - un seul endroit où ajouter la condition.

### La purge automatique avec un index TTL

Pour ce qui doit vraiment disparaître au bout d'un temps donné (paniers abandonnés, sessions, logs, corbeille), MongoDB sait le faire tout seul :

```python
# Purge les documents 30 jours après la date figurant dans supprime_le
db.produits.create_index("supprime_le", expireAfterSeconds=30 * 24 * 3600,
                         name="ttl_corbeille")
```

Quatre règles pour les index TTL :

1. le champ doit contenir une **date** (ou un tableau de dates : la plus ancienne fait foi) ;
2. le nettoyage tourne **toutes les 60 secondes** en tâche de fond - la suppression n'est pas instantanée ;
3. l'index doit être **simple**, pas composé ;
4. `expireAfterSeconds=0` signifie "expire exactement à la date indiquée" - l'idiome pour les sessions et les jetons.

Les documents **sans** le champ ne sont jamais supprimés : c'est ce qui rend le mécanisme sûr sur une collection hétérogène.

---

## 9.3 `bulk_write` - écrire en lot

Une boucle Python qui fait mille `update_one`, c'est mille allers-retours réseau. `bulk_write` regroupe tout en un minimum d'échanges : sur un import, le gain est couramment d'un facteur **10 à 100**.

```python
from pymongo import DeleteOne, InsertOne, ReplaceOne, UpdateMany, UpdateOne

operations = [
    InsertOne({"sku": "KBD-0030", "nom": "Clavier compact", "categorie": "clavier"}),
    UpdateOne({"sku": "SCR-0011"}, {"$inc": {"stock": 10}}),
    UpdateMany({"categorie": "souris"}, {"$set": {"promo": True}}),
    UpdateOne({"sku": "ABO-0013"}, {"$set": {"actif": True}}, upsert=True),
    DeleteOne({"sku": "OBSOLETE-0001"}),
]

res = db.produits.bulk_write(operations, ordered=False)
print(res.inserted_count, res.modified_count, res.upserted_count, res.deleted_count)
```

### Le paramètre `ordered`, encore

| Valeur | Comportement |
|---|---|
| `True` *(défaut)* | opérations exécutées **dans l'ordre**, arrêt au premier échec |
| `False` | ordre non garanti, **toutes** sont tentées, les erreurs sont récapitulées à la fin |

Choisissez `ordered=True` si une opération dépend de la précédente ; `ordered=False` sinon - c'est plus rapide.

### Gérer les échecs partiels

```python
from pymongo.errors import BulkWriteError

try:
    db.produits.bulk_write(operations, ordered=False)
except BulkWriteError as exc:
    detail = exc.details
    print("insérés :", detail["nInserted"], "- modifiés :", detail["nModified"])
    for err in detail["writeErrors"]:
        print(f"  opération #{err['index']} - code {err['code']} : {err['errmsg'][:70]}")
```

Encore une fois : **`BulkWriteError` ne veut pas dire "rien n'est passé"**. Avec `ordered=False`, une partie du lot a très probablement réussi. Lisez toujours le détail avant de rejouer quoi que ce soit - au risque, sinon, de créer des doublons.

### Traiter un gros volume par tranches

```python
from itertools import islice

def par_tranches(iterable, taille=1000):
    it = iter(iterable)
    while lot := list(islice(it, taille)):
        yield lot

for lot in par_tranches(gros_catalogue, 1000):
    db.produits.bulk_write(
        [UpdateOne({"sku": p["sku"]}, {"$set": p}, upsert=True) for p in lot],
        ordered=False,
    )
```

Pourquoi ne pas tout envoyer d'un coup ? Une requête BSON est limitée à 48 Mo, le serveur découpe de toute façon en lots de 100 000 opérations, et surtout : par tranches, un échec ne fait pas tout recommencer depuis le début. **1 000 par lot est un bon réglage par défaut.**

---

## 9.4 Le tableau récapitulatif du CRUD

| Besoin | Méthode | Retour |
|---|---|---|
| Créer un document | `insert_one` | `inserted_id` |
| Créer un lot | `insert_many(..., ordered=False)` | `inserted_ids` |
| Lire un document | `find_one` | `dict` ou `None` |
| Lire plusieurs documents | `find` | curseur paresseux |
| Compter | `count_documents` / `estimated_document_count` | `int` |
| Modifier des champs | `update_one` / `update_many` | `matched_count`, `modified_count` |
| Créer si absent | `update_one(..., upsert=True)` | `upserted_id` |
| Lire+modifier atomiquement | `find_one_and_update` | le document |
| Remplacer entièrement | `replace_one` | `matched_count` |
| Supprimer | `delete_one` / `delete_many` | `deleted_count` |
| Supprimer et récupérer | `find_one_and_delete` | le document |
| Lot hétérogène | `bulk_write` | compteurs par type |

---

## Exercice (15 min)

1. Comptez, puis supprimez, les produits sans champ `stock` **et** dont la catégorie est `divers`.
2. Mettez en place une suppression logique : marquez `LIV-0014` comme supprimé, puis écrivez la requête de liste qui l'exclut.
3. Créez un index TTL qui purgera la corbeille au bout de 7 jours.
4. Écrivez un `bulk_write` qui, en une seule fois : met tous les claviers en promotion, incrémente de 5 le stock des écrans, et supprime les produits sans nom.
5. Question : après un `bulk_write(ordered=False)` qui lève `BulkWriteError`, comment savoir ce qui est réellement passé ?

<details>
<summary>Voir la correction</summary>

```python
from datetime import datetime, timezone
from pymongo import DeleteMany, UpdateMany
from db import get_db

db = get_db()

# 1 - on compte AVANT de supprimer
filtre = {"stock": {"$exists": False}, "categorie": "divers"}
print("à supprimer :", db.produits.count_documents(filtre))
print("supprimés   :", db.produits.delete_many(filtre).deleted_count)

# 2
db.produits.update_one({"sku": "LIV-0014"},
                       {"$set": {"supprime_le": datetime.now(timezone.utc)}})
actifs = db.produits.find({"supprime_le": {"$exists": False}})

# 3
db.produits.create_index("supprime_le", expireAfterSeconds=7 * 24 * 3600,
                         name="ttl_corbeille")

# 4
db.produits.bulk_write([
    UpdateMany({"categorie": "clavier"}, {"$set": {"promo": True}}),
    UpdateMany({"categorie": "ecran"}, {"$inc": {"stock": 5}}),
    DeleteMany({"nom": {"$exists": False}}),
], ordered=False)
```

**Question 5** : par `exc.details`. Il contient `nInserted`, `nModified`, `nUpserted`, `nRemoved` - ce qui a réussi - et `writeErrors`, une liste où chaque entrée porte l'`index` de l'opération fautive dans votre liste, son `code` et son `errmsg`. On rejoue **uniquement** les opérations listées dans `writeErrors`, jamais le lot entier.

**Attention au piège de la question 3** : l'index TTL de la correction supprimera définitivement, au bout de 7 jours, tout document ayant un champ `supprime_le` - y compris ceux que vous aviez "juste marqués" en question 2. C'est exactement le comportement voulu ici, mais vérifiez toujours qu'un TTL porte sur un champ dont la seule raison d'être est l'expiration.

</details>

---

## ✅ Ce qu'il faut retenir

1. `delete_one` n'en supprime qu'un ; `delete_many({})` supprime tout, sans confirmation ni retour arrière.
2. Comptez avec le filtre avant de supprimer avec le même filtre.
3. En production : suppression **logique** (`supprime_le`) plus, si besoin, un index **TTL** pour la purge automatique.
4. Un index TTL ne touche jamais les documents qui n'ont pas le champ - pratique sur une collection hétérogène.
5. `bulk_write` remplace les boucles d'écritures : un facteur 10 à 100 sur les imports, par tranches de ~1 000.
6. `BulkWriteError` signale un échec **partiel** : lisez `exc.details` avant de rejouer.

🎉 **Le CRUD est complet.** Les trois étapes suivantes rendent tout cela robuste : le schéma souple, la modélisation, puis les index.

→ **[Étape 10 - Vivre avec un schéma souple](10-schema-souple.md)**
