[← Chapitre 05](05-creer-une-espece.md) · [Sommaire](README.md) · [Chapitre suivant →](07-eteindre-une-espece.md)

# Chapitre 06 - Modifier, et faire évoluer

> 🎯 **Objectif** : mettre la règle métier **dans le filtre**, pour qu'aucune concurrence ne puisse la contourner.
> ⏱️ **Durée** : 30 minutes.
> 📁 **On complète** : `repository.py`, méthodes `modifier()` et `evoluer()`.
> 📋 **Prérequis** : [étape 08](../08-crud-modifier.md), chapitre 05 terminé.

C'est le chapitre le plus important du TD. Le reste est de la mécanique ; ici, il y a une idée.

---

## 6.1 `modifier()` et le piège de `$currentDate`

On veut renvoyer `True` si quelque chose a changé, `False` si la valeur était déjà bonne. La version naïve :

```python
        resultat = await self.col.update_one(
            {"numero": numero},
            {"$set": champs, "$currentDate": {"maj_le": True}},
        )
        return resultat.modified_count == 1
```

Elle renvoie **toujours** `True`.

> ⚠️ **`$currentDate` réécrit `maj_le` à chaque appel.** Le document est donc modifié même quand `$set` ne change rien, et `modified_count` vaut 1 dans tous les cas. MongoDB ne ment pas : le document *a* changé. C'est notre question qui était mal posée.

La réponse : mettre la condition « au moins un champ diffère » **dans le filtre**.

### À faire - `repository.py`

```python
    async def modifier(self, numero: int, champs: dict[str, Any]) -> bool:
        """Modifie des champs. Renvoie True si quelque chose a change."""
        interdits = [c for c in champs
                     if c.startswith("$") or "." in c or c in ("_id", "numero")]
        if interdits:
            raise DocumentInvalide(f"champs interdits : {interdits}")
        if not champs:
            await self.par_numero(numero)     # leve EspeceIntrouvable si absente
            return False
        filtre = {"numero": int(numero), "eteinte_le": {"$exists": False},
                  "$or": [{cle: {"$ne": valeur}} for cle, valeur in champs.items()]}
        try:
            resultat = await self.col.update_one(
                filtre, {"$set": champs, "$currentDate": {"maj_le": True}})
        except WriteError as exc:
            details = exc.details.get("errInfo", exc.details) if exc.details else exc
            raise DocumentInvalide(str(details)) from exc
        if resultat.matched_count == 0:
            await self.par_numero(numero)     # leve EspeceIntrouvable si absente
            return False                      # presente, mais deja a jour
        return True
```

Le `$or` de `$ne` dit : « le document ne correspond que si au moins un des champs demandés a une autre valeur ». Si rien ne diffère, `matched_count` vaut 0 - et il reste à distinguer les deux causes.

**`matched_count == 0` a deux causes**, et une seule seconde requête les sépare : soit l'espèce n'existe pas (`par_numero` lève), soit elle était déjà à jour (on renvoie `False`). Cette requête supplémentaire n'est payée **qu'en cas d'échec**.

### La liste des champs interdits

> ⚠️ **Une clé de formulaire qui commence par `$` est une injection d'opérateur.** Un `PATCH` avec `{"champs": {"$rename": {"nom": "pirate"}}}` se retrouverait dans un `$set` et le serveur l'interpréterait. On refuse aussi les clés contenant un point - qui atteindraient un sous-document - et `_id` comme `numero`, qui sont l'identité du document.

---

## 6.2 `evoluer()` - la condition métier dans le filtre

Une espèce passe de junior (0) à gourou (3), un stade à la fois. La règle : **on ne dépasse jamais gourou**.

La version qui semble correcte :

```python
# ❌ Lire, decider, ecrire : trois temps, et une fenetre entre chaque
espece = await self.col.find_one({"numero": numero})
if espece["stade"] >= 3:
    raise EvolutionImpossible(...)
await self.col.update_one({"numero": numero}, {"$inc": {"stade": 1}})
```

Entre le `find_one` et le `update_one`, une autre requête peut passer. Deux clics simultanés depuis le stade senior donnent `stade = 4` : un stade qui n'existe pas.

La bonne version ne lit pas avant d'écrire. Elle **décrit la condition au serveur**, qui l'applique dans la même opération atomique :

```python
    async def evoluer(self, numero: int) -> dict[str, Any]:
        """Passe l'espece au stade suivant, atomiquement.

        La condition metier est DANS le filtre : deux clics simultanes ne
        peuvent pas sauter un stade, et on ne depasse jamais gourou.
        """
        document = await self.col.find_one_and_update(
            {"numero": int(numero), "stade": {"$lt": len(STADES) - 1},
             "eteinte_le": {"$exists": False}},
            {"$inc": {"stade": 1}, "$currentDate": {"maj_le": True}},
            return_document=ReturnDocument.AFTER,
        )
        if document is None:
            # Seconde requete UNIQUEMENT en cas d'echec, pour affiner le message.
            await self.par_numero(numero)     # leve EspeceIntrouvable le cas echeant
            raise EvolutionImpossible(f"{numero} : deja au stade gourou")
        return en_json(document)
```

`{"stade": {"$lt": 3}}` dans le **filtre**, et non dans un `if` Python : c'est toute la différence. Si la condition n'est pas remplie, le document ne correspond pas, rien n'est écrit, et `find_one_and_update` renvoie `None`.

C'est le même schéma que le `reserver()` de l'[étape 13](../13-projet-final.md) : la condition métier dans le filtre, une seule opération, pas de transaction.

> ⚠️ **Sans `return_document=ReturnDocument.AFTER`, on renvoie l'état d'avant.** L'API répondrait 200 avec l'ancien stade, et la carte afficherait le stade précédent. Le bug ne se voit **pas** dans les journaux : il se voit à l'écran, et on l'attribue au front.

---

## 6.3 La preuve, en deux `curl`

Amenez une espèce au stade senior, puis lancez deux évolutions **en même temps** :

```bash
docker compose exec api python importer_especes.py --reset

curl -s -X POST localhost:8000/api/especes/8/evolution -o /dev/null   # junior  -> mature
curl -s -X POST localhost:8000/api/especes/8/evolution -o /dev/null   # mature  -> senior

# Depuis senior, deux evolutions simultanees :
curl -s -o /dev/null -w "%{http_code}\n" -X POST localhost:8000/api/especes/8/evolution &
curl -s -o /dev/null -w "%{http_code}\n" -X POST localhost:8000/api/especes/8/evolution &
wait
```

```
200
409
```

Un succès, un refus. Jamais deux succès. Vérifiez :

```bash
curl -s localhost:8000/api/especes/8 | grep -o '"stade":[0-9]*'
```

```
"stade":3
```

Trois, pas quatre. Le test `test_chapitre06_evolution_concurrente` fait la même chose avec quatre appels en parallèle depuis junior :

```python
    resultats = await asyncio.gather(*(depot.evoluer(1) for _ in range(4)),
                                     return_exceptions=True)
    reussites = [r for r in resultats if not isinstance(r, Exception)]
    assert len(reussites) == 3
    assert (await depot.par_numero(1))["stade"] == 3
```

---

## 6.4 Vérifier

Rechargez l'interface, ouvrez une fiche, cliquez **Faire évoluer** :

- le badge passe junior → mature → senior → gourou ;
- le titre affiché suit (`Pythonet`, `Pythonier`, `Serpython`, `Grand Serpent`) ;
- au quatrième clic, le bouton est grisé et affiche **Déjà gourou**.

Le `PATCH` :

```bash
curl -s -X PATCH localhost:8000/api/especes/1 \
  -H "Content-Type: application/json" -d '{"champs":{"nom":"Dev Python 3"}}'
curl -s -X PATCH localhost:8000/api/especes/1 \
  -H "Content-Type: application/json" -d '{"champs":{"nom":"Dev Python 3"}}'
```

```json
{"modifie":true}
{"modifie":false}
```

Et l'injection d'opérateur :

```bash
curl -s -o /dev/null -w "%{http_code} " -X PATCH localhost:8000/api/especes/1 \
  -H "Content-Type: application/json" -d '{"champs":{"$set":{"stade":3}}}'
curl -s -X PATCH localhost:8000/api/especes/1 \
  -H "Content-Type: application/json" -d '{"champs":{"$set":{"stade":3}}}'
```

```
422 {"erreur":"champs interdits : ['$set']"}
```

```bash
docker compose exec api pytest -k chapitre06
docker compose exec api python importer_especes.py --reset
```

```
4 passed
```

---

## Exercice (15 min)

On veut pouvoir **rétrograder** une espèce - un gourou qui n'a pas touché un clavier depuis trois ans redevient senior.

1. Écrivez `retrograder(numero)`, symétrique de `evoluer()`.
2. La règle « on ne descend pas en dessous de junior » doit être dans le filtre, pas dans un `if`.
3. Ajoutez une variante `definir_stade(numero, stade)` qui saute directement à un stade donné. Question : pourquoi celle-ci est-elle nettement plus dangereuse, et que faudrait-il pour la rendre sûre ?

<details>
<summary>Voir la correction</summary>

```python
    async def retrograder(self, numero: int) -> dict[str, Any]:
        """Recule d'un stade. La borne basse est dans le filtre."""
        document = await self.col.find_one_and_update(
            {"numero": int(numero), "stade": {"$gt": 0},
             "eteinte_le": {"$exists": False}},
            {"$inc": {"stade": -1}, "$currentDate": {"maj_le": True}},
            return_document=ReturnDocument.AFTER,
        )
        if document is None:
            await self.par_numero(numero)
            raise EvolutionImpossible(f"{numero} : deja au stade junior")
        return en_json(document)
```

```python
    async def definir_stade(self, numero: int, stade: int,
                            stade_attendu: int) -> dict[str, Any]:
        """Saute a un stade donne, mais seulement si l'etat lu est encore vrai.

        stade_attendu vient de la lecture faite par l'appelant : c'est lui qui
        rend l'operation sure.
        """
        if not 0 <= stade < len(STADES):
            raise DocumentInvalide(f"stade hors bornes : {stade}")
        document = await self.col.find_one_and_update(
            {"numero": int(numero), "stade": stade_attendu,
             "eteinte_le": {"$exists": False}},
            {"$set": {"stade": stade}, "$currentDate": {"maj_le": True}},
            return_document=ReturnDocument.AFTER,
        )
        if document is None:
            await self.par_numero(numero)
            raise EvolutionImpossible(
                f"{numero} : le stade a change depuis votre lecture")
        return en_json(document)
```

3. `$inc` est une opération **relative** : le serveur applique « ajoute 1 » à la valeur qu'il a, quelle qu'elle soit. Deux `$inc` concurrents donnent toujours un résultat cohérent.

`$set` est **absolu** : il écrase. Deux clients qui lisent `stade: 1`, décident tous deux « je passe à 2 » et écrivent, produisent une seule progression au lieu de deux - la classique *mise à jour perdue*.

Le remède est le **verrou optimiste** : on ajoute au filtre l'état qu'on croyait vrai (`stade_attendu`). Si un autre est passé entre-temps, le filtre ne correspond plus, rien n'est écrit, et l'appelant est prévenu qu'il doit relire. C'est le même mécanisme qu'un `ETag` en HTTP.

Règle générale : **préférez toujours un opérateur relatif quand il existe**, et n'utilisez `$set` sur une valeur concurrente qu'accompagné de la condition qui la protège.

</details>

---

## ✅ Ce qu'il faut retenir

1. `$currentDate` fait toujours varier `modified_count` : la condition « quelque chose a-t-il changé ? » doit vivre **dans le filtre**.
2. `find_one_and_update` avec la règle métier dans le filtre rend l'opération atomique **sans transaction**.
3. Lire, décider, écrire ouvre une fenêtre de concurrence. Décrivez la condition au serveur.
4. `ReturnDocument.AFTER`, sinon l'écran affiche l'état d'avant.
5. Une clé de formulaire commençant par `$` ou contenant un point est une injection : le dépôt les refuse.

→ **[Chapitre 07 - Éteindre une espèce](07-eteindre-une-espece.md)**
