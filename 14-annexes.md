[← Étape 13](13-projet-final.md) · [Sommaire](README.md)

# Étape 14 - Annexes

Les tableaux qu'on garde ouverts dans un onglet.

---

## A. SQL → mongosh → PyMongo

| SQL | mongosh | PyMongo |
|---|---|---|
| `CREATE TABLE t (...)` | `db.createCollection("t", {validator})` | `db.create_collection("t", validator=...)` |
| `INSERT INTO t VALUES (...)` | `db.t.insertOne({...})` | `db.t.insert_one({...})` |
| `INSERT` multiple | `db.t.insertMany([...])` | `db.t.insert_many([...], ordered=False)` |
| `SELECT * FROM t WHERE a = 1` | `db.t.find({a: 1})` | `db.t.find({"a": 1})` |
| `SELECT a, b FROM t` | `db.t.find({}, {a: 1, b: 1, _id: 0})` | idem |
| `WHERE a > 1 AND b < 2` | `{a: {$gt: 1}, b: {$lt: 2}}` | idem |
| `WHERE a IN (1, 2)` | `{a: {$in: [1, 2]}}` | idem |
| `WHERE a IS NULL` | `{a: {$type: "null"}}` ⚠️ | idem |
| `WHERE a LIKE 'ab%'` | `{a: /^ab/}` | `{"a": {"$regex": "^ab"}}` |
| `ORDER BY a DESC LIMIT 10` | `.sort({a: -1}).limit(10)` | `.sort("a", -1).limit(10)` |
| `UPDATE t SET a = 1 WHERE b = 2` | `db.t.updateMany({b: 2}, {$set: {a: 1}})` | `db.t.update_many(...)` |
| `UPDATE … SET a = a + 1` | `{$inc: {a: 1}}` | idem |
| Remplacement complet (`PUT`) | `db.t.replaceOne({...}, {...})` | `db.t.replace_one(...)` |
| `INSERT … ON DUPLICATE KEY UPDATE` | `updateOne(..., {upsert: true})` | `update_one(..., upsert=True)` |
| `DELETE FROM t WHERE a = 1` | `db.t.deleteMany({a: 1})` | `db.t.delete_many({"a": 1})` |
| `SELECT COUNT(*)` | `db.t.countDocuments({})` | `count_documents({})` |
| `SELECT DISTINCT a` | `db.t.distinct("a")` | `distinct("a")` |
| `GROUP BY a` | `{$group: {_id: "$a", n: {$sum: 1}}}` | idem |
| `HAVING` | `$match` **après** `$group` | idem |
| `JOIN` | `$lookup` | idem |
| `CREATE INDEX` | `db.t.createIndex({a: 1})` | `create_index([("a", 1)])` |
| `EXPLAIN` | `.explain("executionStats")` | `.explain("executionStats")` |
| `BEGIN … COMMIT` | `session.withTransaction()` | `session.with_transaction()` |
| *(pas d'équivalent)* | `{a: {$exists: false}}` | idem - **le champ n'existe pas** |

---

## B. Opérateurs les plus utilisés

### Requête

| Catégorie | Opérateurs |
|---|---|
| Comparaison | `$eq $ne $gt $gte $lt $lte $in $nin` |
| Logique | `$and $or $not $nor` |
| Élément | `$exists $type` |
| Tableaux | `$all $size $elemMatch` |
| Évaluation | `$regex $text $expr $jsonSchema $mod` |
| Géospatial | `$near $geoWithin $geoIntersects` |

### Mise à jour

| Catégorie | Opérateurs |
|---|---|
| Champs | `$set $unset $rename $setOnInsert $currentDate` |
| Nombres | `$inc $mul $min $max` |
| Tableaux | `$push $pull $pullAll $addToSet $pop` |
| Modificateurs de `$push` | `$each $slice $sort $position` |
| Éléments ciblés | `$` (premier trouvé), `$[]` (tous), `$[<id>]` + `array_filters` |

### Agrégation (étapes principales)

`$match` · `$project` · `$set` / `$addFields` · `$unset` · `$group` · `$sort` · `$limit` · `$skip` · `$unwind` · `$lookup` · `$facet` · `$bucket` · `$count` · `$sortByCount` · `$graphLookup` · `$unionWith` · `$out` · `$merge`

Expressions utiles : `$ifNull` · `$cond` · `$switch` · `$toDouble` / `$toDecimal` / `$toString` / `$convert` · `$type` · `$objectToArray` · `$size` · `$dateToString`

---

## C. Erreurs fréquentes et solutions

| Symptôme | Cause | Solution |
|---|---|---|
| `ServerSelectionTimeoutError` | serveur arrêté, mauvais port/hôte | `docker compose ps` ; vérifier l'URI |
| `Authentication failed` | mauvais `authSource` ou mot de passe | `?authSource=boutique` (ou `admin`) |
| `The "dnspython" module must be installed` | URI `+srv` sans l'extra | `pip install "pymongo[srv]"` |
| `ImportError: cannot import name 'ObjectId'` | paquet `bson` de PyPI installé | `pip uninstall bson` |
| `E11000 duplicate key error` | index unique violé | attraper `DuplicateKeyError`, ou faire un upsert |
| `Update document requires atomic operators` | `$set` oublié | `{"$set": {...}}` |
| `WriteError` code **121** | validation JSON Schema | lire `exc.details["errInfo"]["details"]` |
| `Transaction numbers are only allowed…` | serveur standalone | replica set (§ 3.3) |
| **Zéro résultat, aucune erreur** | nom de collection erroné, `ObjectId` passé en chaîne, ou type inattendu | `list_collection_names()`, `ObjectId(...)`, `$type` |
| Requête soudainement lente | index manquant ou non utilisé | `explain("executionStats")` |
| `Sort exceeded memory limit` | tri en mémoire > 100 Mo | index sur le champ de tri, ou `allowDiskUse` |
| `KeyError` sur un champ | document d'une autre forme | `.get()`, `$exists`, `$ifNull` (étape 10) |

---

## D. Mémo mongosh

```javascript
show dbs                                   // bases
use maBase                                 // changer de base
show collections
db.maColl.findOne()                        // voir la forme d'un document
db.maColl.countDocuments({})
db.maColl.getIndexes()
db.maColl.stats()                          // taille, nombre de documents
db.maColl.find().pretty()
db.maColl.find(...).explain("executionStats")
db.maColl.aggregate([{$indexStats: {}}])   // index réellement utilisés
db.currentOp()                             // opérations en cours
db.serverStatus().connections
rs.status()                                // état du replica set
db.dropDatabase()                          // ⚠️
exit
```

---

## E. Sauvegarde, import, export

```bash
# Sauvegarde fidèle (BSON, types conservés)
mongodump    --uri="mongodb://app:app-password@localhost:27017/boutique?authSource=boutique" --out=dump/
mongorestore --uri="..." --drop dump/

# Échange avec d'autres outils (JSON/CSV, avec perte de types)
mongoexport --uri="..." --collection=produits --out=produits.json --jsonArray
mongoimport --uri="..." --collection=produits --file=produits.json --jsonArray
```

`mongodump`/`mongorestore` pour les sauvegardes et les migrations d'environnement ; `mongoexport`/`mongoimport` pour l'échange de données. Ne confondez pas : un `mongoexport` d'un champ `Decimal128` en fait une valeur JSON étendue, et un réimport négligent le transforme en `Double`.

---

## F. Glossaire

* **BSON** - Binary JSON, le format de stockage et du protocole, typé et binaire.
* **Change stream** - flux temps réel des modifications d'une collection.
* **COLLSCAN / IXSCAN** - parcours de toute la collection / parcours d'index.
* **Collection** - l'équivalent d'une table ; ses documents peuvent avoir des formes différentes.
* **Document** - l'équivalent d'une ligne, arborescent, 16 Mo maximum.
* **ESR** - Equality, Sort, Range : l'ordre des champs dans un index composé.
* **`_id`** - clé primaire obligatoire, unique, immuable, indexée d'office.
* **Multikey** - index automatique sur un champ tableau, une entrée par élément.
* **`mongod` / `mongos` / `mongosh`** - le serveur / le routeur d'un cluster shardé / le shell.
* **ObjectId** - identifiant de 12 octets, approximativement croissant dans le temps.
* **Oplog** - journal des opérations, base de la réplication et des change streams.
* **Pipeline** - suite d'étapes de transformation, le langage d'agrégation.
* **Replica set** - groupe de nœuds répliqués avec bascule automatique ; requis pour les transactions et les change streams.
* **Shard** - partition horizontale des données sur plusieurs replica sets.
* **Upsert** - mise à jour qui crée le document s'il n'existe pas.
* **Validation** - règles JSON Schema appliquées par le serveur à l'écriture.
* **WiredTiger** - le moteur de stockage (verrous au niveau document, compression).

---

## G. Pour continuer

- **Documentation Python officielle** - [`mongodb.com/docs/languages/python/`](https://www.mongodb.com/docs/languages/python/) : la structure CRUD de ce cours en est directement inspirée (*Insert · Query · Update · Replace · Delete · Bulk Write · Configure*).
- **Manuel serveur et référence des opérateurs** - [`mongodb.com/docs`](https://www.mongodb.com/docs/).
- **PyMongo** - [`pymongo.readthedocs.io`](https://pymongo.readthedocs.io/) : lisez le CHANGELOG à chaque montée de version.
- **MongoDB University** - [`learn.mongodb.com`](https://learn.mongodb.com/) : parcours gratuits et certification *Associate Developer*, disponibles en français.
- **Building with Patterns** - [`mongodb.com/company/blog/building-with-patterns-a-summary`](https://www.mongodb.com/company/blog/building-with-patterns-a-summary) : la série d'articles officielle sur les patterns de modélisation (Subset, Computed, Bucket, Attribute…).
- **MongoDB Compass** - [`mongodb.com/products/tools/compass`](https://www.mongodb.com/products/tools/compass) : pour explorer, et surtout pour l'onglet *Schema* - l'outil le plus rapide pour comprendre une collection hétérogène.

---

## H. Ce que vous savez faire, étape par étape

| Étape | Compétence acquise |
|---|---|
| [01](01-nosql-en-bref.md) | situer MongoDB parmi les familles NoSQL, et dire quand ne pas l'utiliser |
| [02](02-mongodb-decouverte.md) | traduire un modèle MySQL en modèle documentaire |
| [03](03-lancer-mongodb.md) | démarrer un MongoDB local et un cluster Atlas |
| [04](04-premiers-pas-mongosh.md) | faire un CRUD dans le shell, et lire un message d'erreur du serveur |
| [05](05-se-connecter-en-python.md) | écrire une connexion propre et diagnostiquer une panne |
| [06](06-crud-creer.md) | insérer, choisir ses types, traiter les erreurs d'écriture |
| [07](07-crud-lire.md) | filtrer, projeter, trier, paginer - et lire des documents hétérogènes |
| [08](08-crud-modifier.md) | modifier avec les bons opérateurs, atomiquement |
| [09](09-crud-supprimer.md) | supprimer proprement et écrire en lot |
| [10](10-schema-souple.md) | auditer, valider, versionner et migrer un schéma souple |
| [11](11-modeliser.md) | choisir entre imbriquer et référencer, et le justifier |
| [12](12-index-et-performances.md) | poser un index utile et le prouver avec `explain` |
| [13](13-projet-final.md) | assembler le tout dans une application testée |

→ [Retour au sommaire](README.md)
