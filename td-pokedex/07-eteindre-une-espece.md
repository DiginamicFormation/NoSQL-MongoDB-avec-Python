[← Chapitre 06](06-modifier-et-evoluer.md) · [Sommaire](README.md) · [Chapitre suivant →](08-ou-les-trouver.md)

# Chapitre 07 - Éteindre une espèce

> 🎯 **Objectif** : supprimer sans détruire, et laisser un index TTL faire le ménage trente jours plus tard.
> ⏱️ **Durée** : 25 minutes.
> 📁 **On complète** : `repository.py`, méthodes `eteindre()`, `eteindre_definitivement()`, `restaurer()`, et le TTL dans `initialiser()`.
> 📋 **Prérequis** : [étape 09](../09-crud-supprimer.md) et [étape 12](../12-index-et-performances.md), chapitre 06 terminé.

Le Dev Perl et le Dev TurboPascal existent encore dans la base. Ils ne devraient plus s'afficher, mais on n'a pas envie de les perdre.

---

## 7.1 Trois suppressions, pas une

| Méthode | Effet | Réversible |
|---|---|---|
| `eteindre()` | pose `eteinte_le` | oui, par `restaurer()` |
| `restaurer()` | retire `eteinte_le` | - |
| `eteindre_definitivement()` | `delete_one` | **non** |

Le défaut est l'extinction **logique**. La suppression physique existe, mais elle demande `?definitif=1` - un geste explicite.

### À faire - `repository.py`

```python
    async def eteindre(self, numero: int) -> None:
        """Extinction logique : purge automatique 30 jours plus tard (index TTL)."""
        resultat = await self.col.update_one(
            {"numero": int(numero), "eteinte_le": {"$exists": False}},
            {"$set": {"eteinte_le": datetime.now(timezone.utc)}},
        )
        if resultat.matched_count == 0:
            raise EspeceIntrouvable(f"aucune espece vivante numero {numero}")

    async def eteindre_definitivement(self, numero: int) -> None:
        resultat = await self.col.delete_one({"numero": int(numero)})
        if resultat.deleted_count == 0:
            raise EspeceIntrouvable(f"aucune espece numero {numero}")

    async def restaurer(self, numero: int) -> None:
        resultat = await self.col.update_one(
            {"numero": int(numero), "eteinte_le": {"$exists": True}},
            {"$unset": {"eteinte_le": ""}})
        if resultat.matched_count == 0:
            raise EspeceIntrouvable(f"aucune espece eteinte numero {numero}")
```

Trois détails.

**`{"eteinte_le": {"$exists": False}}` dans le filtre d'extinction** : éteindre une espèce déjà éteinte ne doit pas écraser la date d'origine, et donc pas repousser sa purge de trente jours.

**`$unset` prend `""` comme valeur** - qui est ignorée. C'est la syntaxe de MongoDB, pas une bizarrerie de PyMongo.

> ⚠️ **`delete_one` qui ne trouve rien ne dit rien.** Aucune exception, aucun avertissement : `deleted_count == 0` est le **seul** signal. Sans ce test, l'interface afficherait « supprimé » pour une espèce qui n'a jamais existé.

---

## 7.2 L'index TTL, et pourquoi il doit être partiel

Une corbeille qui ne se vide jamais est une fuite. MongoDB sait purger tout seul : un index TTL supprime les documents dont le champ daté a dépassé un délai.

### À faire - `repository.py`

Ajoutez dans `initialiser()` :

```python
            # TTL partiel : purge la corbeille 30 jours apres l'extinction, et
            # ne touche jamais les documents qui n'ont pas le champ.
            IndexModel([("eteinte_le", ASCENDING)], name="ttl_extinction",
                       expireAfterSeconds=30 * 24 * 3600,
                       partialFilterExpression={"eteinte_le": {"$type": "date"}}),
```

> ⚠️ **Un index TTL sans `partialFilterExpression` est une bombe à retardement.** Il ignore les documents où le champ est **absent** - c'est son comportement normal - mais il fait expirer ceux où le champ vaut **`null`**. Un `$set: {"eteinte_le": None}` malencontreux, et l'espèce disparaît pour de bon en moins d'une minute. Le filtre `{"$type": "date"}` restreint l'index aux documents qui portent une vraie date : les autres n'y entrent même pas.

C'est encore la distinction absent / `null` / valeur du § 10.3, cette fois avec des conséquences irréversibles.

> ⚠️ **Le TTL n'est pas ponctuel.** Une tâche de fond passe environ **toutes les soixante secondes**. Ne concluez pas à l'échec au bout de dix secondes, et ne comptez jamais dessus pour une échéance à la seconde près.

---

## 7.3 Le filtre d'exclusion, une dernière fois

Après extinction, le document est **toujours là** :

```bash
docker compose exec mongo mongosh -u app -p app-password \
  --authenticationDatabase pokedex pokedex \
  --quiet --eval 'db.especes.countDocuments({})'
```

Quinze, avant comme après. Ce qui change, c'est que toutes les lectures du dépôt portent `{"eteinte_le": {"$exists": False}}` - `lister`, `compter`, `par_numero`, `evoluer`, `autour_de`, `dans_la_zone`, `statistiques`.

Sept méthodes, sept fois la même ligne. C'est répétitif, et c'est **voulu** : la règle est écrite là où vivent les requêtes. Une vue SQL, un décorateur ou un « filtre global » la rendrait invisible - et le jour où quelqu'un écrirait une requête ailleurs, elle ne s'appliquerait pas.

L'unique méthode qui l'ignore délibérément est `auditer()`, au chapitre 09 : elle décrit la collection **telle qu'elle est**, corbeille comprise.

---

## 7.4 Vérifier

Dans l'interface, ouvrez une fiche et cliquez **Éteindre**. La carte disparaît de la grille.

Cochez **espèces éteintes** : elle réapparaît, barrée, avec un lien `restaurer`.

```bash
curl -s -o /dev/null -w "%{http_code}\n" -X DELETE localhost:8000/api/especes/900
```

```
204
```

La base n'a rien perdu :

```bash
docker compose exec mongo mongosh -u app -p app-password \
  --authenticationDatabase pokedex pokedex --quiet \
  --eval 'print(db.especes.countDocuments({}), db.especes.countDocuments({eteinte_le:{$exists:false}}))'
```

```
15 12
```

Quinze documents, douze vivantes. Restaurez, puis supprimez pour de bon :

```bash
curl -s -X POST localhost:8000/api/especes/900/restauration
curl -s -o /dev/null -w "%{http_code}\n" -X DELETE "localhost:8000/api/especes/900?definitif=1"
```

```json
{"restauree":true}
```
```
204
```

Cette fois le compte tombe à quatorze. Et l'index :

```bash
docker compose exec mongo mongosh -u app -p app-password \
  --authenticationDatabase pokedex pokedex --quiet \
  --eval 'printjson(db.especes.getIndexes().find(i => i.name === "ttl_extinction"))'
```

```javascript
{
  v: 2,
  key: { eteinte_le: 1 },
  name: 'ttl_extinction',
  expireAfterSeconds: 2592000,
  partialFilterExpression: { eteinte_le: { '$type': 'date' } }
}
```

```bash
docker compose exec api pytest -k chapitre07
docker compose exec api python importer_especes.py --reset
```

```
3 passed
```

---

## Exercice (15 min)

Trente jours, c'est long à attendre en TP. Observez une vraie purge TTL.

1. Créez une espèce jetable, éteignez-la avec une date **déjà passée**.
2. Posez un index TTL temporaire à `expireAfterSeconds=0` sur un autre champ, et attendez.
3. Question : pourquoi ne peut-on pas simplement changer `expireAfterSeconds` de `ttl_extinction` à `0` pour le test ?

<details>
<summary>Voir la correction</summary>

```python
# demo_ttl.py
import asyncio
from datetime import datetime, timedelta, timezone

from pymongo import ASCENDING, IndexModel

from db import fermer, get_db


async def principal() -> None:
    col = get_db()["especes"]

    # Un champ dedie, pour ne pas toucher a l'index de production.
    await col.create_indexes([
        IndexModel([("purge_demo", ASCENDING)], name="ttl_demo",
                   expireAfterSeconds=0,
                   partialFilterExpression={"purge_demo": {"$type": "date"}}),
    ])

    await col.insert_one({
        "numero": 999, "nom": "Dev Jetable", "famille": "backend",
        "stade": 0, "evolutions": [], "habitats": [], "schema_version": 1,
        "purge_demo": datetime.now(timezone.utc) - timedelta(minutes=5),
    })
    print("insere, purge_demo date d'il y a 5 minutes")

    for tour in range(1, 13):
        reste = await col.count_documents({"numero": 999})
        print(f"{tour * 10:>3}s : {reste} document")
        if reste == 0:
            break
        await asyncio.sleep(10)

    await col.drop_index("ttl_demo")
    await fermer()


asyncio.run(principal())
```

```bash
docker compose exec api python demo_ttl.py
```

```
insere, purge_demo date d'il y a 5 minutes
 10s : 1 document
 ...
 60s : 0 document
```

Le document part au premier passage de la tâche de fond, jamais à l'instant exact.

3. Trois raisons, dont une bloquante :

- **Changer `expireAfterSeconds` sur un index existant demande un `collMod`**, pas un `create_indexes` : le recréer avec d'autres options lève `IndexOptionsConflict` (code 85).
- Surtout, un TTL à `0` sur `eteinte_le` **effacerait immédiatement toutes les espèces éteintes réelles** - Perl et TurboPascal comprises. Le TP les détruirait.
- Enfin, on n'expérimente pas sur l'index dont dépend le comportement qu'on est en train de démontrer. Un champ jetable coûte deux lignes et ne risque rien.

</details>

---

## ✅ Ce qu'il faut retenir

1. La suppression par défaut est **logique** : on pose une date, le document reste.
2. Un index TTL **sans `partialFilterExpression`** fait expirer les documents où le champ vaut `null`. Toujours restreindre à `{"$type": "date"}`.
3. La purge TTL passe environ toutes les soixante secondes : elle n'est jamais ponctuelle.
4. `delete_one` ne signale rien : `deleted_count == 0` est le seul indice qu'il n'y avait rien à supprimer.
5. Le filtre d'exclusion est répété dans chaque méthode du dépôt, volontairement : c'est là que vivent les requêtes.

→ **[Chapitre 08 - Où les trouver ?](08-ou-les-trouver.md)**
