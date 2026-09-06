[← Étape 11](11-modeliser.md) · [Sommaire](README.md) · [Étape suivante →](13-projet-final.md)

# Étape 12 - Index et performances

> 🎯 **Objectif** : poser les bons index, vérifier avec `explain()` qu'ils servent vraiment, et connaître les particularités MongoDB qui n'existent pas en SQL.
> ⏱️ **Durée** : 45 minutes.
> 📁 **On crée** : `boutique/mesurer.py`.

---

## 12.1 Le principe, identique à SQL

Sans index, MongoDB effectue un **`COLLSCAN`** : il lit toute la collection, document par document. Un index est un **B-arbre**, exactement comme en SQL : lecture rapide, écritures plus lentes (chaque insertion met à jour tous les index), et de la RAM consommée.

```python
from pymongo import ASCENDING, DESCENDING, IndexModel
from db import get_db

db = get_db()

db.produits.create_index([("categorie", ASCENDING), ("prix", DESCENDING)], name="cat_prix")

# Plusieurs d'un coup - la forme à privilégier dans un script de provisionnement
db.produits.create_indexes([
    IndexModel([("sku", ASCENDING)], unique=True, name="uniq_sku"),
    IndexModel([("tags", ASCENDING)], name="tags"),
])

for index in db.produits.list_indexes():
    print(index["name"], index["key"])

db.produits.drop_index("tags")
```

`1` = croissant, `-1` = décroissant. `_id` est indexé automatiquement, et cet index ne peut pas être supprimé.

**`create_index` est idempotent** : le rejouer ne crée pas de doublon. En revanche, changer les *options* d'un index existant lève une erreur - il faut le supprimer puis le recréer.

---

## 12.2 Mesurer avant de conclure : `explain()`

### À faire - `mesurer.py`

```python
"""Compare un plan d'exécution avec et sans index."""
from bson import Decimal128
from pymongo import ASCENDING, DESCENDING

from db import get_db

db = get_db()

# 1. On fabrique un volume suffisant pour que la différence se voie
if db.mesures.count_documents({}) < 50_000:
    db.mesures.drop()
    db.mesures.insert_many(
        [{"categorie": f"cat-{i % 20}", "prix": Decimal128(str(10 + i % 500)),
          "nom": f"produit {i}", "stock": i % 100}
         for i in range(50_000)],
        ordered=False,
    )
    print("50 000 documents insérés")


def plan(titre):
    resultat = (db.mesures.find({"categorie": "cat-7", "prix": {"$gte": Decimal128("100")}})
                .sort("stock", DESCENDING)
                .explain("executionStats"))
    stats = resultat["executionStats"]
    gagnant = stats["executionStages"]
    print(f"\n{titre}")
    print(f"  étape             : {gagnant['stage']}")
    print(f"  documents rendus  : {stats['nReturned']}")
    print(f"  documents examinés: {stats['totalDocsExamined']}")
    print(f"  clés examinées    : {stats['totalKeysExamined']}")
    print(f"  durée             : {stats['executionTimeMillis']} ms")


plan("SANS index")

# 2. Index ESR : Egalité (categorie), Sort (stock), Range (prix)
db.mesures.create_index([("categorie", ASCENDING), ("stock", DESCENDING),
                         ("prix", ASCENDING)], name="esr")
plan("AVEC index ESR")
```

```bash
python mesurer.py
```

Résultat typique :

```
SANS index
  étape             : SORT
  documents rendus  : 1750
  documents examinés: 50000        ← toute la collection
  durée             : 78 ms

AVEC index ESR
  étape             : FETCH
  documents rendus  : 1750
  documents examinés: 1750         ← exactement ce qu'il fallait
  durée             : 6 ms
```

### Les cinq chiffres à lire, dans l'ordre

| Indicateur | Ce qu'on veut |
|---|---|
| `stage` | **`IXSCAN`** (parcours d'index) - pas `COLLSCAN`, sauf sur une toute petite collection |
| `nReturned` vs `totalDocsExamined` | un ratio le plus proche possible de **1:1** |
| `totalKeysExamined` | proche de `nReturned` ; très supérieur = index mal **ordonné** |
| `executionTimeMillis` | à comparer avant / après |
| une étape **`SORT`** | un tri en mémoire : ajoutez le champ de tri à l'index |

> **Compass et Atlas** affichent le même plan graphiquement (onglet *Explain*), avec l'arbre des étapes. Sur Atlas, le **Performance Advisor** propose même des index à partir des requêtes lentes réellement observées : commencez par lui avant d'en inventer.

---

## 12.3 La règle **ESR** et la règle du préfixe

### ESR - Equality, Sort, Range

Dans un index composé, ordonnez les champs ainsi :

1. **E** - ceux testés en **égalité** ;
2. **S** - ceux qui servent au **tri** ;
3. **R** - ceux testés en **plage** (`$gt`, `$lt`, `$in` sur un intervalle).

Pour `find({categorie: "clavier", prix: {$gte: 50}}).sort({stock: -1})`, l'index optimal est donc `{categorie: 1, stock: -1, prix: 1}` - et surtout **pas** l'ordre dans lequel la requête est écrite.

### La règle du préfixe

Un index `{a: 1, b: 1, c: 1}` sert aussi les requêtes sur `{a}` et sur `{a, b}`. Il **ne sert jamais** une requête portant seulement sur `{b}`, `{c}` ou `{b, c}`.

Conséquence : **trois index simples ne remplacent pas un index composé**, et un index composé bien ordonné en remplace souvent trois. C'est l'erreur n°1 en formation.

### La requête couverte (*covered query*)

Si **tous** les champs filtrés, triés et retournés sont dans l'index, MongoDB ne lit aucun document : `totalDocsExamined: 0`. Il faut alors exclure `_id` de la projection s'il n'est pas dans l'index.

```python
db.mesures.create_index([("categorie", 1), ("prix", 1)], name="couverture")
db.mesures.find({"categorie": "cat-7"}, {"_id": 0, "categorie": 1, "prix": 1})
```

---

## 12.4 Le catalogue des types d'index

| Type | Déclaration | Sert à |
|---|---|---|
| Simple | `[("prix", 1)]` | égalité, plage, tri |
| **Composé** | `[("categorie", 1), ("prix", -1)]` | plusieurs critères ; 32 champs maximum |
| **Multikey** | *automatique* sur un champ tableau | `{"tags": "promo"}` |
| Texte | `[("nom", "text")]` | `$text` ; **un seul par collection** |
| Géospatial | `[("position", "2dsphere")]` | `$near`, `$geoWithin` |
| Hashé | `[("_id", "hashed")]` | clé de shard bien répartie |
| **TTL** | `("expire_le", expireAfterSeconds=…)` | purge automatique (étape 09) |
| **Partiel** | `partialFilterExpression={...}` | n'indexer que les documents utiles |
| **Unique** | `unique=True` | contrainte d'unicité |
| Wildcard | `{"attributs.$**": 1}` | champs imprévisibles (étape 10) |
| Caché | `hidden=True` | index invisible du planificateur, sans le supprimer |

---

## 12.5 Les particularités MongoDB - celles qui surprennent

Ce sont elles qui différencient vraiment l'indexation MongoDB de celle de MySQL. Elles découlent presque toutes du schéma souple.

**① Les index multikey sont automatiques… et contraints.** Indexer un champ tableau crée une entrée d'index **par élément** : un document à 50 tags produit 50 clés. Surtout, **un index composé ne peut contenir qu'un seul champ tableau** - `{tags: 1, categories: 1}` est refusé si les deux sont des tableaux (le produit cartésien des clés exploserait).

**② `unique` sur un tableau contraint globalement.** Un index unique sur un champ tableau interdit que **deux documents partagent ne serait-ce qu'un seul élément**. C'est rarement ce qu'on veut.

**③ `unique` considère les documents sans le champ comme ayant `null`** - et deux `null` violent l'unicité. Sur une collection hétérogène, un index unique naïf casse donc tout. La bonne réponse est l'**index partiel** :

```python
# Un SIRET unique, mais seulement pour les produits qui en ont un
db.produits.create_index(
    [("siret", ASCENDING)],
    unique=True,
    partialFilterExpression={"siret": {"$type": "string"}},
    name="uniq_siret_si_present",
)
```

C'est **la** technique à retenir de cette étape : sur une collection aux documents hétérogènes, un index partiel est presque toujours préférable à un index complet. Il est plus petit, plus rapide, et il n'impose rien aux documents qui ne sont pas concernés.

**④ Les index TTL ont leurs règles** (voir étape 09) : champ de type date, nettoyage toutes les 60 secondes, index simple obligatoire, et les documents sans le champ ne sont jamais supprimés.

**⑤ Un seul index texte par collection**, et il ne gère ni la recherche par préfixe partiel, ni la pertinence fine. Pour une vraie recherche : **Atlas Search** (Lucene) ou un moteur externe.

**⑥ `$regex` n'utilise l'index que s'il est ancré et sensible à la casse.** `/^Clav/` oui ; `/clav/i` non - ce dernier provoque un scan complet. Pour l'insensibilité à la casse, utilisez une **collation** (`{locale: "fr", strength: 2}`) déclarée sur l'index *et* rappelée dans la requête, ou stockez un champ normalisé en minuscules.

**⑦ La direction compte pour le tri.** `{a: 1, b: 1}` sert `sort({a: 1, b: 1})` et son inverse exact `sort({a: -1, b: -1})`, mais **pas** `sort({a: 1, b: -1})`.

**⑧ Un tri en mémoire est plafonné à 100 Mo.** Au-delà, la requête échoue si `allowDiskUse` n'est pas activé. Un tri lent est presque toujours un index manquant.

**⑨ Les index cachés** (`hidden=True`) permettent de tester la suppression d'un index sans le perdre : on le cache, on observe la production, puis on le supprime - ou on le réaffiche.

**⑩ Les plafonds** : 64 index par collection, 32 champs par index composé.

---

## 12.6 Hygiène : moins d'index, mais les bons

Chaque index ralentit **toutes** les écritures et consomme de la RAM. Un index inutilisé est une dette pure.

```python
# Quels index servent réellement ? (compteurs remis à zéro au redémarrage du serveur)
for stat in db.produits.aggregate([{"$indexStats": {}}]):
    print(f"{stat['name']:<25} {stat['accesses']['ops']:>8} utilisations")
```

La liste de contrôle :

- un index **par requête fréquente**, pas un par champ ;
- appliquez **ESR** et vérifiez le **préfixe** avant d'en ajouter un ;
- `explain()` sur un volume réaliste - pas sur dix documents de test ;
- supprimez ce que `$indexStats` montre à zéro depuis des semaines (cachez-le d'abord) ;
- créez les index en **heures creuses** : la construction consomme CPU et I/O.

---

## Exercice (15 min)

1. Lancez `mesurer.py`. Notez `totalDocsExamined` avant et après l'index.
2. Créez un index `{categorie: 1, prix: 1}` puis testez `find({"prix": {"$lt": 100}})`. L'index est-il utilisé ? Pourquoi ?
3. Rendez la requête `find({"categorie": "cat-3"}, {"_id": 0, "categorie": 1, "prix": 1})` **couverte**, et prouvez-le avec `explain`.
4. Créez un index unique sur un champ que seuls certains documents possèdent, sans casser les autres.
5. Mesurez le coût des index à l'écriture : insérez 5 000 documents avec et sans les index, et comparez.

<details>
<summary>Voir la correction</summary>

```python
# 2 - NON. L'index {categorie: 1, prix: 1} a pour préfixe `categorie` :
#     une requête portant uniquement sur `prix` ne peut pas l'utiliser.
#     explain() montre un COLLSCAN. Il faudrait un index {prix: 1}.
db.mesures.find({"prix": {"$lt": 100}}).explain("executionStats")["executionStats"]["executionStages"]["stage"]

# 3
db.mesures.create_index([("categorie", 1), ("prix", 1)], name="couverture")
stats = (db.mesures.find({"categorie": "cat-3"}, {"_id": 0, "categorie": 1, "prix": 1})
         .explain("executionStats")["executionStats"])
print(stats["totalDocsExamined"])     # 0 → requête couverte : aucun document lu
# Si vous laissez _id dans la projection, totalDocsExamined redevient > 0.

# 4
db.produits.create_index([("isbn", 1)], unique=True,
                         partialFilterExpression={"isbn": {"$type": "string"}},
                         name="uniq_isbn_si_present")
# Sans partialFilterExpression : les 8 produits sans ISBN valent tous "null"
# → E11000 dès le deuxième. C'est LE piège de l'index unique sur collection hétérogène.

# 5
import time
from pymongo import IndexModel

docs = lambda n: [{"categorie": f"c{i%10}", "prix": i, "stock": i} for i in range(n)]

db.perf_sans.drop(); db.perf_avec.drop()
db.perf_avec.create_indexes([IndexModel([("categorie", 1)]), IndexModel([("prix", 1)]),
                             IndexModel([("stock", 1)]), IndexModel([("categorie", 1), ("prix", -1)])])

for nom, col in [("sans index", db.perf_sans), ("avec 4 index", db.perf_avec)]:
    debut = time.perf_counter()
    col.insert_many(docs(5_000), ordered=False)
    print(f"{nom:<14}: {time.perf_counter() - debut:.2f} s")
```

L'écart mesuré est typiquement de **30 à 60 %** sur les écritures. Sur une collection qui reçoit des millions d'insertions, quatre index de trop se paient tous les jours. C'est pour cela qu'on indexe les requêtes **fréquentes**, et pas "au cas où".

</details>

---

## ✅ Ce qu'il faut retenir

1. Pas d'index = `COLLSCAN`. `explain("executionStats")` est le seul juge : visez `IXSCAN` et un ratio rendus/examinés proche de 1:1.
2. **ESR** : égalité, puis tri, puis plage. C'est l'ordre des champs qui fait la performance.
3. **Règle du préfixe** : `{a,b,c}` sert `{a}` et `{a,b}`, jamais `{b}` seul.
4. Sur une collection hétérogène, préférez les **index partiels** - indispensables pour un `unique` sur un champ optionnel.
5. `$regex` non ancré, tri de direction mixte, tri en mémoire > 100 Mo : trois façons classiques de perdre son index.
6. Chaque index coûte à l'écriture : supprimez ceux que `$indexStats` montre inutilisés.

→ **[Étape 13 - Projet final](13-projet-final.md)**
