[← Chapitre 08](08-ou-les-trouver.md) · [Sommaire](README.md) · [Sommaire du cours →](../README.md)

# Chapitre 09 - Agréger, auditer, verrouiller

> 🎯 **Objectif** : calculer côté serveur, découvrir la vraie forme de la collection, puis poser la validation et les index - dans cet ordre.
> ⏱️ **Durée** : 35 minutes.
> 📁 **On complète** : `repository.py` (4 méthodes) et `provision.py`.
> 📋 **Prérequis** : [étape 10](../10-schema-souple.md) et [étape 12](../12-index-et-performances.md), chapitre 08 terminé.

Dernier chapitre. À la fin, `fixtures.py` part à la poubelle.

---

## 9.1 `aggregate` s'attend, `find` ne s'attend pas

Vous l'avez appris au chapitre 03 dans un sens. Voici l'autre :

```python
# ❌ AttributeError: 'coroutine' object has no attribute '__aiter__'
curseur = self.col.aggregate(pipeline)

# ✅ aggregate EST une coroutine, et elle rend un AsyncCommandCursor
curseur = await self.col.aggregate(pipeline)
lignes = [ligne async for ligne in curseur]
```

| | coroutine ? | consommation |
|---|---|---|
| `col.find(...)` | **non** | `await curseur.to_list(n)` ou `async for` |
| `col.aggregate(...)` | **oui** | `async for` sur ce qu'elle rend |

> ⚠️ **C'est l'asymétrie la plus déroutante du driver asynchrone.** Les deux messages d'erreur sont opposés - l'un dit qu'on ne peut pas attendre un curseur, l'autre qu'on ne peut pas itérer une coroutine. Retenez la règle plutôt que les messages : **`find` construit, `aggregate` exécute.**

---

## 9.2 `statistiques()`

```python
    async def statistiques(self) -> list[dict[str, Any]]:
        """Chiffres par famille, tolerants aux champs absents."""
        curseur = await self.col.aggregate([
            {"$match": {"eteinte_le": {"$exists": False}}},
            {"$group": {
                "_id": "$famille",
                "nombre": {"$sum": 1},
                "xp_total": {"$sum": {"$ifNull": ["$xp", 0]}},
                # Champ ABSENT n'est pas champ a zero : on compte les deux.
                "sans_xp": {"$sum": {"$cond": [
                    {"$eq": [{"$type": "$xp"}, "missing"]}, 1, 0]}},
                # $avg sur un Decimal128 rend un Decimal128, non serialisable :
                # on convertit cote serveur.
                "salaire_gourou_moyen": {"$avg": {
                    "$toDouble": {"$getField": {
                        "field": "salaire",
                        "input": {"$arrayElemAt": ["$evolutions", -1]}}}}},
                "habitats": {"$sum": {"$size": {"$ifNull": ["$habitats", []]}}},
            }},
            {"$project": {"_id": 0, "famille": "$_id", "nombre": 1,
                          "xp_total": 1, "sans_xp": 1,
                          "salaire_gourou_moyen": {"$round": ["$salaire_gourou_moyen", 0]},
                          "habitats": 1}},
            {"$sort": {"nombre": DESCENDING, "famille": ASCENDING}},
        ])
        return [ligne async for ligne in curseur]
```

**`$match` en premier**, toujours : il réduit le flux avant tout calcul, et il peut utiliser un index. Un `$match` placé après un `$group` ferait travailler le serveur pour rien.

**`$arrayElemAt: ["$evolutions", -1]`** prend le dernier élément du tableau - le stade gourou - sans savoir combien il y en a.

> ⚠️ **`$avg` sur un `Decimal128` rend un `Decimal128`**, que FastAPI ne sait pas sérialiser : 500. La conversion `$toDouble` se fait **dans le pipeline**, côté serveur, et non en Python après coup. Règle générale : ce qui peut être calculé par le serveur doit l'être.

> ⚠️ **Champ absent n'est pas champ à zéro, jusque dans l'agrégation.** `{"$sum": "$xp"}` ignore silencieusement les documents sans `xp` - le total est juste. Mais `{"$avg": "$xp"}` les exclut aussi du **dénominateur**, et la moyenne devient fausse sans prévenir. D'où le `$ifNull` pour sommer, et le comptage séparé avec `{"$type": "$xp"} == "missing"`.

C'est la convention posée au chapitre 01, tenue jusqu'au bout : le front affiche `sans champ xp : 1` pour la famille `frontend`, parce que Dev Svelte n'a jamais été capturé.

---

## 9.3 `auditer()` - la forme réelle de la collection

Une collection MongoDB n'a pas de schéma déclaré. La seule source de vérité sur sa forme est son **contenu**.

```python
    async def auditer(self) -> list[dict[str, Any]]:
        """Presence et types reels de chaque champ de la collection."""
        total = max(await self.compter(inclure_eteintes=True), 1)
        curseur = await self.col.aggregate([
            {"$project": {"champs": {"$objectToArray": "$$ROOT"}}},
            {"$unwind": "$champs"},
            {"$group": {"_id": "$champs.k",
                        "presents": {"$sum": 1},
                        "types": {"$addToSet": {"$type": "$champs.v"}}}},
            {"$sort": {"presents": DESCENDING, "_id": ASCENDING}},
        ])
        return [{"champ": ligne["_id"],
                 "presents": ligne["presents"],
                 "taux": round(100 * ligne["presents"] / total),
                 "types": sorted(ligne["types"])}
                async for ligne in curseur]
```

`$objectToArray: "$$ROOT"` transforme chaque document en liste de paires `{k, v}`. `$unwind` les met à plat, `$group` compte. C'est le § 10.2, et c'est le premier réflexe devant une collection inconnue.

> ⚠️ **Le dénominateur doit couvrir les mêmes documents que l'agrégation.** Le pipeline balaie **toute** la collection, espèces éteintes comprises. Si `total` les excluait, les taux dépasseraient 100 % - et vous auriez un tableau qui affiche `116 %` sans que rien ne plante. D'où le `inclure_eteintes=True`, seul endroit du dépôt où on le demande.

Ouvrez l'onglet **Audit** :

```
numero                100%  int
...
langages               93%  array
xp                     93%  int
frameworks             47%  array
bundler                27%  string
gpu_requis             13%  bool
language                7%  string      <- l'intrus
```

`language`, au singulier, à 7 % : **un seul document**. C'est le Dev TurboPascal repéré au chapitre 01. Personne ne l'avait déclaré nulle part ; l'agrégation l'a trouvé.

---

## 9.4 `decrire_schema()` et `plan_de_requete()`

```python
    async def decrire_schema(self) -> dict[str, Any]:
        """Ce que le serveur impose reellement : validation et index."""
        infos = await self.db.command("listCollections",
                                      filter={"name": "especes"})
        lot = infos["cursor"]["firstBatch"]
        options = lot[0].get("options", {}) if lot else {}
        return {
            "validation": en_json(options.get("validator", {})),
            "niveau": options.get("validationLevel", "off"),
            "action": options.get("validationAction", "-"),
            "index": [en_json(i) async for i in await self.col.list_indexes()],
        }

    async def plan_de_requete(self, filtre: dict[str, Any]) -> dict[str, Any]:
        """explain() est asynchrone aussi : le curseur l'est."""
        plan = await self.col.find(filtre).explain()
        return en_json(plan["queryPlanner"]["winningPlan"])
```

Les 18 marqueurs sont maintenant à zéro :

```bash
docker compose exec api sh -c "grep -c 'chapitre 0.$' repository.py"
```

```
0
```

---

## 9.5 Mesurer avant d'indexer

Ne posez jamais un index « au cas où ». Regardez d'abord.

```bash
docker compose exec api python -c "
import asyncio
from db import fermer, get_db

async def m():
    r = await get_db().command({'explain': {'find': 'especes',
                                            'filter': {'famille': 'backend'}},
                                'verbosity': 'executionStats'})
    e = r['executionStats']
    print('stage         :', r['queryPlanner']['winningPlan'].get('stage'))
    print('docs examines :', e['totalDocsExamined'])
    print('retournes     :', e['nReturned'])
    await fermer()

asyncio.run(m())
"
```

```
stage         : COLLSCAN
docs examines : 15
retournes     : 7
```

Quinze documents lus pour en rendre sept. Sur quinze c'est indolore ; sur un million, c'est la panne.

### À faire - `repository.py`

Ajoutez les deux derniers index dans `initialiser()` :

```python
            IndexModel([("famille", ASCENDING), ("numero", ASCENDING)],
                       name="famille_numero"),
            IndexModel([("langages", ASCENDING)], name="langages"),
```

`famille` puis `numero` : **égalité d'abord, tri ensuite**, c'est la règle ESR du § 12.4. La même requête, une fois l'index posé :

```
stage         : FETCH
docs examines : 7
cles examinees: 7
retournes     : 7
```

Sept clés, sept documents, sept résultats. Plus une seule lecture inutile.

> ⚠️ **`explain(verbosity=...)` n'existe pas sur un `AsyncCursor`.** Pour les statistiques d'exécution, il faut passer par `db.command({"explain": ..., "verbosity": "executionStats"})`. Le `explain()` du curseur ne donne que le plan choisi.

---

## 9.6 Verrouiller le noyau commun

Reste à empêcher qu'une écriture fantaisiste casse ce sur quoi tout le code s'appuie. Mais **on ne verrouille pas tout** :

> ⚠️ **`additionalProperties: false` détruirait le Pokédex.** Ce serait refuser `bundler`, `gpu_requis`, `chapeau`, `astreinte` - tous les champs qui font l'intérêt du modèle documentaire. On impose le **noyau commun**, on laisse le reste libre. C'est le § 10.6.

### À faire - `provision.py`

```python
NOYAU_COMMUN = {
    "$jsonSchema": {
        "bsonType": "object",
        "title": "espece",
        "required": ["numero", "nom", "famille", "stade", "evolutions",
                     "schema_version"],
        "properties": {
            "numero": {"bsonType": "int", "minimum": 1},
            "nom": {"bsonType": "string", "minLength": 2, "maxLength": 100},
            "famille": {"enum": ["backend", "frontend", "data", "securite",
                                 "infra"]},
            "langages": {"bsonType": "array", "items": {"bsonType": "string"}},
            "stade": {"bsonType": "int", "minimum": 0, "maximum": 3},
            "xp": {"bsonType": "int", "minimum": 0},
            "evolutions": {
                "bsonType": "array", "minItems": 4, "maxItems": 4,
                "items": {
                    "bsonType": "object",
                    "required": ["niveau", "titre", "salaire"],
                    "properties": {
                        "niveau": {"enum": ["junior", "mature", "senior",
                                            "gourou"]},
                        "titre": {"bsonType": "string"},
                        "salaire": {"bsonType": "decimal"},
                    },
                },
            },
            "schema_version": {"bsonType": "int", "minimum": 1},
        },
        # On impose le noyau commun, on laisse la liberte sur le reste.
        "additionalProperties": True,
    }
}

REGLES_FAMILLES = {
    "$or": [
        {"famille": {"$ne": "frontend"}},
        {"$and": [{"bundler": {"$type": "string"}},
                  {"reactivite": {"$exists": True}}]},
    ]
}
```

Le `$or` se lit : « ou bien ce n'est pas un frontend, ou bien il a un `bundler` et une `reactivite` ». C'est la règle des écrans du § 10.6, transposée. Un validateur accepte les opérateurs de requête à côté de `$jsonSchema` : c'est ainsi qu'on exprime les contraintes conditionnelles.

Le fichier complète tout seul `VALIDATOR` à partir de ces deux constantes.

---

## 9.7 Pourquoi on ne passe pas directement en `strict`

```bash
docker compose exec api python provision.py --strict
docker compose exec api python importer_especes.py --reset
```

```
pymongo.errors.BulkWriteError: batch op errors occurred
  'errmsg': 'Document failed validation'
  'propertyName': 'schema_version'
  'specifiedAs': {'minimum': 1}, 'reason': 'comparison failed', 'consideredValue': 0
  'nUpserted': 14
```

**Quatorze espèces sur quinze.** Dev TurboPascal est refusé : son `schema_version` vaut `0`.

C'est exactement ce qui arrive quand on verrouille une base réelle. La séquence correcte est en trois temps :

1. **`moderate` / `warn`** - les écritures passent, les violations sont journalisées ;
2. **on regarde** ce que dit l'audit, et **on migre** les documents fautifs ;
3. **`strict` / `error`** - la règle devient une garantie.

```bash
docker compose exec api python provision.py     # retour en moderate/warn
docker compose exec api python importer_especes.py --reset
```

> ⚠️ **`collMod` exige le rôle `dbAdmin`.** Avec un simple `readWrite`, on obtient `not authorized on pokedex to execute command { collMod: ... }`. C'est pour cela que `init/01-init.js` donne `dbOwner` à l'utilisateur applicatif - et c'est le genre de détail qui bloque une mise en production un vendredi soir.

---

## 9.8 Vérifier, puis jeter les fixtures

```bash
docker compose exec api pytest -v
```

```
27 passed
```

Les 27 tests, tous les chapitres. Supprimez alors le mensonge :

```bash
docker compose exec api sh -c "grep -c fixtures repository.py"
```

```
0
```

```bash
rm api/fixtures.py
docker compose restart api
curl -s localhost:8000/api/sante
```

```json
{"mongo":"ok","version":"8.0.30","especes":15}
```

L'application tourne, sans une seule ligne de donnée en dur. Ouvrez `http://localhost:8080` : les cinq onglets répondent, et tout vient de MongoDB.

---

## Exercice (20 min)

L'audit a trouvé `language` au singulier chez Dev TurboPascal. Migrez-le, puis verrouillez pour de bon.

1. Écrivez `migrer_langages()` : les documents qui ont `language` (chaîne) reçoivent `langages` (tableau), l'ancien champ est retiré, et `schema_version` passe à 1.
2. La migration doit être **réexécutable** : la relancer ne doit rien casser.
3. Passez ensuite en `strict`, et vérifiez que l'import complet des quinze espèces échoue toujours. Question : pourquoi, et qu'est-ce que cela dit du fichier `donnees/especes.json` ?

<details>
<summary>Voir la correction</summary>

```python
    async def migrer_langages(self) -> int:
        """Passe language (chaine) a langages (tableau). Reexecutable.

        Le filtre porte sur la FORME du document, pas sur un numero : relancer
        la migration ne trouve plus rien, et ne fait rien.
        """
        resultat = await self.col.update_many(
            {"language": {"$type": "string"}},
            [{"$set": {"langages": ["$language"], "schema_version": 1}},
             {"$unset": "language"}],
        )
        return resultat.modified_count
```

```bash
docker compose exec api python -c "
import asyncio
from db import fermer, get_db
from repository import DepotPokedex

async def m():
    depot = DepotPokedex(get_db())
    print('migres :', await depot.migrer_langages())
    print('migres :', await depot.migrer_langages())   # relance
    espece = await depot.par_numero(901, inclure_eteintes=True)
    print(espece['langages'], 'v' + str(espece['schema_version']))
    await fermer()

asyncio.run(m())
"
```

```
migres : 1
migres : 0
['pascal']
```

Deux détails qui font la différence :

- **C'est un `update_many` avec un *pipeline*** (une liste, pas un dictionnaire). C'est ce qui permet à `langages` d'être calculé **à partir de** `$language` : une mise à jour classique ne sait pas lire la valeur qu'elle écrit.
- **Le filtre décrit la forme fautive**, `{"language": {"$type": "string"}}`, et non un identifiant. C'est ce qui rend la migration réexécutable et applicable à des documents qu'on n'a pas encore vus.

3. L'import échoue toujours - mais plus pour la même raison. Le document en base est corrigé ; c'est **`donnees/especes.json` qui contient encore l'original**, avec `language` et `schema_version: 0`. Un `--reset` réintroduit donc la donnée fautive, que le validateur strict refuse.

C'est le vrai enseignement du chapitre : **migrer la base ne migre pas les sources**. Tant que le fichier d'import, les scripts de peuplement et les jeux de test portent l'ancienne forme, la dette revient au premier rechargement. Une migration se fait toujours en deux endroits.

</details>

---

## ✅ Ce qu'il faut retenir

1. `aggregate` **est** une coroutine, `find` ne l'est pas. `find` construit, `aggregate` exécute.
2. Un champ absent fausse `$avg` sans prévenir : `$ifNull` pour sommer, `{"$type": ...} == "missing"` pour compter.
3. `$objectToArray` révèle la forme réelle d'une collection - et le dénominateur doit couvrir les mêmes documents, sinon les taux dépassent 100 %.
4. On mesure avec `explain()` **avant** de poser un index, et on l'ordonne par égalité puis tri.
5. On verrouille le **noyau commun** avec `additionalProperties: true`, et on passe par `moderate/warn` avant `strict/error`.

---

## ✅ Bravo

Dix-huit marqueurs, neuf chapitres, une application qui lit et écrit dans MongoDB de bout en bout. Vous savez maintenant écrire un dépôt qui tient toutes les requêtes d'une application, rendre une opération atomique sans transaction, vivre avec des documents qui n'ont pas la même forme, interroger la géographie, et verrouiller un schéma sans le figer.

Le dépôt que vous avez écrit tient en trois cents lignes. C'est la taille normale de la couche d'accès aux données d'une petite application - et c'est le seul endroit où `pymongo` apparaît.

→ [Retour au sommaire du TD](README.md) · [Sommaire du cours](../README.md)
