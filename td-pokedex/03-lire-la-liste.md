[← Chapitre 02](02-connexion-asynchrone.md) · [Sommaire](README.md) · [Chapitre suivant →](04-ouvrir-une-fiche.md)

# Chapitre 03 - Lire la liste des espèces

> 🎯 **Objectif** : brancher la grille sur MongoDB - filtres, recherche, tri, pagination par curseur.
> ⏱️ **Durée** : 30 minutes.
> 📁 **On complète** : `repository.py`, méthodes `lister()` et `compter()`.
> 📋 **Prérequis** : [étape 07](../07-crud-lire.md) du cours, chapitre 02 terminé.

C'est le chapitre où l'écran cesse de mentir.

---

## 3.1 `find()` ne s'attend pas

Le piège numéro un du driver asynchrone, et il vaut mieux le rencontrer tout de suite :

```python
# ❌ TypeError: object AsyncCursor can't be used in 'await' expression
documents = await self.col.find(filtre)

# ✅ find() rend un curseur ; c'est sa consommation qui s'attend
documents = await self.col.find(filtre).to_list(20)
```

`find()` ne va pas au serveur. Elle construit un `AsyncCursor`, sur lequel on empile `sort`, `limit`, `skip` - toujours sans `await`. La requête ne part qu'à la consommation.

Deux façons de consommer :

```python
documents = await curseur.to_list(20)              # tout d'un coup, borne
async for document in curseur:                     # un par un, en flux
    ...
```

> ⚠️ **Retenez l'asymétrie maintenant** : `find` **non**, `aggregate` **oui**. Vous la retrouverez au chapitre 09, et elle produit un message d'erreur radicalement différent.

---

## 3.2 Le contrat de `lister()`

L'interface envoie jusqu'à cinq paramètres :

| Paramètre | Effet |
|---|---|
| `famille` | égalité stricte sur `famille` |
| `q` | cherche dans `nom` **ou** dans `langages` |
| `eteintes` | à `False` (défaut), exclut les espèces éteintes |
| `apres` | numéro de la dernière espèce de la page précédente |
| `taille` | nombre maximum de documents |

Le tri est **toujours** `numero` croissant : c'est ce qui rend la pagination par curseur possible.

---

## 3.3 Le filtre d'extinction, posé une fois

```python
        if not eteintes:
            filtre["eteinte_le"] = {"$exists": False}
```

Deux lignes, mais c'est l'argument central de l'[étape 13](../13-projet-final.md) : la règle « une espèce éteinte ne s'affiche pas » vit **dans le dépôt**, à un seul endroit par méthode. Aucune vue, aucune route, aucun composant Svelte ne peut l'oublier.

> ⚠️ **`{"eteinte_le": None}` n'est pas `{"eteinte_le": {"$exists": False}}`.** Le premier ramène aussi les documents où le champ existe et vaut `null`. C'est le piège fondateur du § 10.3 : en MongoDB, « absent » et « présent mais nul » sont deux états distincts.

---

## 3.4 La projection

```python
PROJECTION_RESUME = {"_id": 0, "numero": 1, "nom": 1, "famille": 1, "stade": 1,
                     "langages": 1, "xp": 1, "evolutions.titre": 1,
                     "habitats": 1, "eteinte_le": 1}
```

Elle est déjà écrite en haut de `repository.py`. Deux détails :

- `"evolutions.titre": 1` ne remonte que le titre de chaque stade, pas les salaires ni les attaques. Une carte n'en a pas besoin.
- **`"_id": 0` n'est pas cosmétique.**

> ⚠️ **`ObjectId` n'est pas sérialisable en JSON.** Oubliez `"_id": 0` et l'API renvoie un `500` - avec, dans les journaux du conteneur et **nulle part ailleurs** :
>
> ```
> ValueError: [TypeError("'ObjectId' object is not iterable"), ...]
> ```
>
> Le navigateur, lui, n'affiche rien d'utile. Le réflexe : `docker compose logs -f api`.

Pour une liste, on projette `_id` dehors. Pour une fiche complète - chapitre 04 - on le convertit avec `en_json()`.

---

## 3.5 La pagination par curseur

```python
# ❌ Se degrade page apres page : le serveur parcourt puis jette
curseur = self.col.find(filtre).skip(20 * page).limit(20)

# ✅ Cout constant : on repart du dernier numero vu
if apres is not None:
    filtre["numero"] = {"$gt": int(apres)}
```

C'est le § 7.8 du cours. Le champ de pagination doit être **unique et trié** : `numero` l'est, et il est indexé dès le chargement des données.

### À faire - `repository.py`

```python
    async def lister(self, famille: str | None = None, q: str | None = None,
                     eteintes: bool = False, apres: int | None = None,
                     taille: int = 20) -> list[dict[str, Any]]:
        """Liste paginee par curseur (pas de skip)."""
        filtre: dict[str, Any] = {}
        if not eteintes:
            filtre["eteinte_le"] = {"$exists": False}
        if famille:
            filtre["famille"] = famille
        if q:
            filtre["$or"] = [{"nom": {"$regex": q, "$options": "i"}},
                             {"langages": q.lower()}]
        if apres is not None:
            filtre["numero"] = {"$gt": int(apres)}
        # find() n'est PAS une coroutine : elle rend un curseur. C'est sa
        # consommation - to_list - qui s'attend.
        curseur = self.col.find(filtre, PROJECTION_RESUME)
        curseur = curseur.sort("numero", ASCENDING).limit(taille)
        return en_json(await curseur.to_list(taille))

    async def compter(self, famille: str | None = None,
                      inclure_eteintes: bool = False) -> int:
        filtre: dict[str, Any] = {}
        if not inclure_eteintes:
            filtre["eteinte_le"] = {"$exists": False}
        if famille:
            filtre["famille"] = famille
        return await self.col.count_documents(filtre)
```

Deux points sur le `$or` de la recherche :

- `{"langages": q.lower()}` interroge un **tableau** sans `$elemMatch` : en MongoDB, comparer un tableau à une valeur teste chacun de ses éléments. C'est le § 7.5.
- `$regex` sans ancrage ne peut pas utiliser d'index. Acceptable sur quinze documents, à remplacer par un index texte au-delà.

---

## 3.6 Vérifier

Rechargez `http://localhost:8080`. **Le compte passe de 13 à 13** - identique, parce que la fixture disait déjà la vérité. Ce sont les filtres qui prouvent le changement :

```bash
curl -s "localhost:8000/api/especes?famille=frontend" | grep -o '"nom":"[^"]*"'
```

```
"nom":"Dev Angular"
"nom":"Dev React"
"nom":"Dev Svelte"
"nom":"Dev Vue"
```

Puis la preuve décisive - insérez une espèce à la main :

```javascript
db.especes.insertOne({
  numero: 500, nom: "Dev Rust", famille: "backend",
  langages: ["rust"], stade: 0,
  evolutions: [{ niveau: "junior", titre: "Rustacé debutant" }],
  habitats: [], schema_version: 1
});
```

Rechargez : **elle apparaît**. Au chapitre 01, elle n'apparaissait pas. La grille lit MongoDB.

```javascript
db.especes.deleteOne({ numero: 500 });
```

Cochez enfin **espèces éteintes** : Dev Perl et Dev TurboPascal se montrent, barrées. Le filtre `$exists` fonctionne dans les deux sens.

```bash
docker compose exec api pytest -k chapitre03
```

```
3 passed
```

---

## Exercice (15 min)

L'interface ne demande jamais plus de cent espèces d'un coup. Ajoutez au dépôt une méthode `lister_toutes()` qui parcourt **toute** la collection en flux, par lots de cinq, sans jamais charger plus de cinq documents en mémoire.

1. Utilisez `async for`, pas `to_list`.
2. Réglez la taille de lot du curseur, et affichez un point à chaque aller-retour réseau.
3. Question : sur quinze documents, combien d'allers-retours voyez-vous, et pourquoi ce nombre n'est-il pas trois ?

<details>
<summary>Voir la correction</summary>

```python
    async def lister_toutes(self) -> list[str]:
        """Parcourt toute la collection en flux, cinq documents a la fois."""
        noms = []
        curseur = self.col.find({}, {"_id": 0, "nom": 1}).batch_size(5)
        async for document in curseur:
            noms.append(document["nom"])
        return noms
```

```bash
docker compose exec api python -c "
import asyncio
from db import fermer, get_db
from repository import DepotPokedex

async def m():
    print(await DepotPokedex(get_db()).lister_toutes())
    await fermer()

asyncio.run(m())
"
```

3. **Quatre**, pas trois. Le premier lot est ramené par la commande `find` elle-même, les suivants par des `getMore`. Quinze documents en lots de cinq donnent donc `find` + trois `getMore`, dont le dernier revient vide et sert à signaler l'épuisement du curseur.

Deux choses à en retenir :

- **`batch_size` ne limite pas le résultat**, il règle la taille des allers-retours. C'est `limit` qui borne.
- **`async for` ne charge jamais tout**, et c'est la seule façon correcte de traiter une collection qui ne tient pas en mémoire. `to_list(None)` sur dix millions de documents fait exploser le conteneur.

</details>

---

## ✅ Ce qu'il faut retenir

1. `find()` **n'est pas** une coroutine : elle rend un curseur, et c'est `to_list` ou `async for` qui s'attend.
2. Le filtre `{"eteinte_le": {"$exists": False}}` est posé **dans le dépôt**, une fois par méthode : impossible de l'oublier ailleurs.
3. `{"champ": None}` n'est pas `{"champ": {"$exists": False}}`.
4. `ObjectId` n'est pas sérialisable : on le projette dehors, ou on le convertit. L'erreur n'apparaît que dans les journaux.
5. On pagine par **curseur** (`numero > dernier`), jamais par `skip`.

→ **[Chapitre 04 - Ouvrir une fiche](04-ouvrir-une-fiche.md)**
