[← Chapitre 04](04-ouvrir-une-fiche.md) · [Sommaire](README.md) · [Chapitre suivant →](06-modifier-et-evoluer.md)

# Chapitre 05 - Créer une espèce

> 🎯 **Objectif** : écrire dans MongoDB, poser l'index unique qui rend le doublon impossible, et traduire les erreurs du driver en erreurs métier.
> ⏱️ **Durée** : 30 minutes.
> 📁 **On complète** : `repository.py`, méthodes `initialiser()` et `creer()`.
> 📋 **Prérequis** : [étape 06](../06-crud-creer.md) et [étape 12](../12-index-et-performances.md), chapitre 04 terminé.

Jusqu'ici on lisait. À partir de maintenant, on écrit - et l'écriture, elle, peut échouer.

---

## 5.1 L'index unique d'abord

Le formulaire **Nouvelle espèce** doit refuser un numéro déjà pris. On ne vérifie **pas** avec un `find_one` préalable :

```python
# ❌ Race condition : deux processus peuvent lire "absent" en meme temps
if await self.col.find_one({"numero": numero}):
    raise EspeceDejaExistante(...)
await self.col.insert_one(document)
```

C'est le § 6.4 du cours. La seule garantie est **l'index unique**, appliqué par le serveur, au moment de l'écriture.

### À faire - `repository.py`

Dans `initialiser()`, posez le premier index :

```python
    async def initialiser(self) -> list[str]:
        """Cree les index. Idempotent."""
        await self.col.create_indexes([
            IndexModel([("numero", ASCENDING)], unique=True, name="uniq_numero"),
        ])
        return [i["name"] async for i in await self.col.list_indexes()]
```

Vous ajouterez les autres au fil des chapitres : le TTL au 07, le `2dsphere` au 08, les index de requête au 09. **On pose un index quand il devient nécessaire, jamais avant** - et à chaque fois, vous saurez dire pourquoi.

Remarquez `list_indexes()` : c'est une coroutine qui rend un curseur asynchrone. D'où le `async for` **à l'intérieur** d'une compréhension, après un `await`.

> ⚠️ **Un index unique se pose sur une collection propre.** S'il existe déjà deux documents avec le même `numero`, `create_indexes` lève `DuplicateKeyError` - et l'index n'est **pas** créé. Votre 409 n'arrivera jamais, et rien ne vous préviendra. Purgez d'abord, indexez ensuite.

> ⚠️ **`create_indexes` est idempotent, mais pas tolérant.** Recréer le même index avec des options différentes lève `IndexOptionsConflict` (code 85). Il faut alors `drop_index` puis recréer. Vous rencontrerez ce cas au chapitre 07 si vous vous trompez sur le TTL.

---

## 5.2 `creer()`

```python
    async def creer(self, numero: int, nom: str, famille: str,
                    evolutions: list[dict[str, Any]],
                    langages: list[str] | None = None, xp: int | None = None,
                    habitats: list[dict[str, Any]] | None = None,
                    **specifiques: Any) -> int:
        """Cree une espece. Les champs propres a la famille passent en kwargs."""
        document: dict[str, Any] = {
            "numero": int(numero),
            "nom": nom,
            "famille": famille,
            "langages": list(langages or []),
            "stade": 0,                     # on nait toujours junior
            "evolutions": [{**e, "salaire": Decimal128(str(e["salaire"]))}
                           for e in evolutions],
            "habitats": list(habitats or []),
            "cree_le": datetime.now(timezone.utc),
            "schema_version": VERSION_SCHEMA,
            **specifiques,
        }
        if xp is not None:              # champ absent = "jamais capturee"
            document["xp"] = int(xp)
        try:
            await self.col.insert_one(document)
        except DuplicateKeyError as exc:
            raise EspeceDejaExistante(f"le numero {numero} est deja pris") from exc
        except WriteError as exc:
            details = exc.details.get("errInfo", exc.details) if exc.details else exc
            raise DocumentInvalide(str(details)) from exc
        return int(numero)
```

Quatre décisions à comprendre.

**`**specifiques`** : tout ce que l'appelant passe en plus atterrit dans le document. C'est ce qui permet de créer un `frontend` avec `bundler="vite"` sans que le dépôt connaisse le mot `bundler`. Le pendant de `decouper()` du chapitre 04, dans l'autre sens.

**`Decimal128(str(...))`** : un salaire n'est jamais un `float`.

```python
"salaire": Decimal128("72000")     # ✅ montant exact
"salaire": 72000.0                 # ❌ binaire : 0.1 + 0.2 != 0.3
"salaire": "72000"                 # ❌ chaine : sort de tout filtre numerique
```

Le `str()` autour est délibéré : `Decimal128` accepte une chaîne ou un `Decimal`, jamais un `float` sans perte. C'est le § 2.7.

**`if xp is not None`** : on n'écrit le champ que s'il a une valeur. Écrire `xp: None` créerait un troisième état - présent, mais nul - et ferait mentir toutes les statistiques du chapitre 09.

**`"stade": 0`** : le stade n'est pas un paramètre. Une espèce naît junior, et n'avance que par `evoluer()`. Une règle métier posée dans le dépôt vaut mieux qu'une convention respectée par tous les appelants.

> ⚠️ **`insert_one` mute le dictionnaire qu'on lui passe** : il y ajoute la clé `_id`. Renvoyer `document` tel quel après l'insertion réintroduirait l'`ObjectId` non sérialisable du chapitre 03. C'est pour cela que la méthode renvoie le numéro, pas le document.

> ⚠️ **`datetime.utcnow()` est naïf.** Il rend un `datetime` sans fuseau, incomparable avec les dates *aware* que `tz_aware=True` fait remonter. Toujours `datetime.now(timezone.utc)`.

---

## 5.3 Les erreurs du driver deviennent des erreurs métier

C'est la règle d'architecture du TD. `app.py` ne connaît pas `DuplicateKeyError` ; il connaît `EspeceDejaExistante`, à qui il associe un 409.

| Erreur PyMongo | Code | Exception métier | HTTP |
|---|---|---|---|
| `DuplicateKeyError` | 11000 | `EspeceDejaExistante` | 409 |
| `WriteError` | 121 | `DocumentInvalide` | 422 |

Le `from exc` conserve la cause : dans les journaux, vous verrez les deux.

`WriteError` ne se déclenchera qu'au chapitre 09, quand le validateur JSON Schema sera posé. On l'écrit maintenant parce qu'on ne revient pas sur du code d'erreur trois chapitres plus tard.

---

## 5.4 Vérifier

Dans l'interface, cliquez **Nouvelle espèce** :

| | |
|---|---|
| numéro | `14` |
| nom | `Dev Zig` |
| famille | `backend` |
| langages | `zig` |

Créez. La carte apparaît - et surtout, **elle survit au rechargement de la page**. C'est la différence avec le chapitre 01.

Réessayez avec le numéro `1` : bandeau rouge, `le numero 1 est deja pris`.

```bash
curl -s -o /dev/null -w "%{http_code}\n" -X POST localhost:8000/api/especes \
  -H "Content-Type: application/json" -d '{
    "numero": 15, "nom": "Dev Elixir", "famille": "backend",
    "evolutions": [
      {"niveau":"junior","titre":"Elixounet","salaire":"35000"},
      {"niveau":"mature","titre":"Elixiste","salaire":"48000"},
      {"niveau":"senior","titre":"Alchimiste","salaire":"62000"},
      {"niveau":"gourou","titre":"Grand Oeuvre","salaire":"78000"}]}'
```

```
201
```

L'index est bien là :

```bash
docker compose exec mongo mongosh -u app -p app-password \
  --authenticationDatabase pokedex pokedex \
  --quiet --eval 'db.especes.getIndexes().map(i => i.name)'
```

```
[ '_id_', 'uniq_numero' ]
```

Et le type du salaire :

```bash
docker compose exec mongo mongosh -u app -p app-password \
  --authenticationDatabase pokedex pokedex --quiet \
  --eval 'typeof db.especes.findOne({numero:15}).evolutions[0].salaire'
```

```
object
```

Un objet, pas un `number` : c'est bien un `Decimal128`.

```bash
docker compose exec api pytest -k chapitre05
```

```
3 passed
```

Nettoyez avant de continuer :

```bash
docker compose exec api python importer_especes.py --reset
```

---

## Exercice (15 min)

Le formateur veut importer un lot d'espèces d'un coup, en tolérant que certaines soient déjà là.

1. Écrivez `creer_plusieurs(especes)` qui insère une liste et renvoie `(créées, refusées)`.
2. Une espèce en doublon ne doit **pas** interrompre les suivantes.
3. Question : pourquoi `insert_many(..., ordered=False)` est-il ici préférable à une boucle de `creer()` ?

<details>
<summary>Voir la correction</summary>

```python
    async def creer_plusieurs(self, especes: list[dict[str, Any]]) -> tuple[int, int]:
        """Insere un lot. ordered=False : un doublon n'arrete pas les suivants."""
        documents = [{
            "numero": int(e["numero"]), "nom": e["nom"], "famille": e["famille"],
            "langages": list(e.get("langages", [])), "stade": 0,
            "evolutions": [{**ev, "salaire": Decimal128(str(ev["salaire"]))}
                           for ev in e["evolutions"]],
            "habitats": list(e.get("habitats", [])),
            "cree_le": datetime.now(timezone.utc),
            "schema_version": VERSION_SCHEMA,
        } for e in especes]
        try:
            resultat = await self.col.insert_many(documents, ordered=False)
            return (len(resultat.inserted_ids), 0)
        except BulkWriteError as exc:
            erreurs = exc.details.get("writeErrors", [])
            return (exc.details.get("nInserted", 0), len(erreurs))
```

Deux détails qui font la différence :

- **`ordered=False`** ne se contente pas de continuer après une erreur : il autorise le serveur à **paralléliser**. C'est le § 6.6. Utilisez-le dès que l'ordre d'insertion n'a pas d'importance métier - c'est-à-dire presque toujours.
- **Le succès partiel arrive dans l'exception.** `BulkWriteError.details` porte `nInserted` : les documents valides sont bel et bien écrits. Un `except` qui se contente de journaliser vous ferait croire à un échec total.

3. Une boucle de `creer()` fait un aller-retour réseau **par espèce**, et ouvre autant de fenêtres où une autre écriture peut s'intercaler. `insert_many` en fait un seul, et le serveur applique l'index unique document par document. Sur cent espèces avec un Atlas distant, la différence se compte en secondes.

</details>

---

## ✅ Ce qu'il faut retenir

1. L'unicité se garantit par un **index unique**, jamais par un `find_one` préalable - ce serait une *race condition*.
2. Un montant est un `Decimal128`, construit depuis une **chaîne**. Jamais un `float`, jamais une chaîne stockée telle quelle.
3. Un champ optionnel **absent** ne s'écrit pas. Ne jamais poser `None` à la place.
4. `insert_one` **modifie** le dictionnaire passé : il y ajoute `_id`.
5. `DuplicateKeyError` et `WriteError` deviennent des exceptions métier dans le dépôt. Le code HTTP est décidé ailleurs.

→ **[Chapitre 06 - Modifier, et faire évoluer](06-modifier-et-evoluer.md)**
