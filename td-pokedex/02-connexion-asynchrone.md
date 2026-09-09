[← Chapitre 01](01-mise-en-route.md) · [Sommaire](README.md) · [Chapitre suivant →](03-lire-la-liste.md)

# Chapitre 02 - Se connecter en asynchrone

> 🎯 **Objectif** : comprendre `AsyncMongoClient`, et faire dire au bandeau la vraie version du serveur.
> ⏱️ **Durée** : 25 minutes.
> 📁 **On complète** : `repository.py`, méthode `sante()`.
> 📋 **Prérequis** : [étape 05](../05-se-connecter-en-python.md) du cours.

Le cours utilise `MongoClient`, synchrone. FastAPI est asynchrone : on passe à `AsyncMongoClient`, intégré à PyMongo depuis la 4.9. L'API est **la même**, avec des `await`.

---

## 2.1 Lire `db.py`

Vous n'avez pas à l'écrire. Vous devez le comprendre - deux commentaires portent tout le chapitre.

```python
# db.py
_client: AsyncMongoClient | None = None


def get_client() -> AsyncMongoClient:
    """Un seul client par processus : il est sur, et il porte le pool.

    Il est cree paresseusement, et non a l'import : un AsyncMongoClient se lie a
    la boucle asyncio dans laquelle il est cree. Construit au niveau module, le
    premier `await` leverait "attached to a different loop".
    """
    global _client
    if _client is None:
        uri = os.environ.get("MONGODB_URI")
        if not uri:
            raise RuntimeError(
                "MONGODB_URI est absent : copiez .env.example en .env")
        _client = AsyncMongoClient(
            uri,
            serverSelectionTimeoutMS=5_000,   # echouer vite si le serveur manque
            connectTimeoutMS=5_000,
            tz_aware=True,                    # datetime "aware", en UTC
            appname="pokedex",
        )
    return _client
```

> ⚠️ **`AsyncMongoClient` se lie à sa boucle asyncio.** Sa construction ne s'attend pas - `AsyncMongoClient(uri)`, sans `await` - mais l'objet mémorise la boucle qui l'a créé. Si vous l'instanciez au niveau du module, il naît **hors** de toute boucle, et le premier `await` lève :
>
> ```
> RuntimeError: Cannot use AsyncMongoClient in different event loop.
> ```
>
> D'où la construction paresseuse. Le même piège frappe les tests : `pytest-asyncio` ouvre une boucle **par test**, c'est pourquoi la fixture de `test_pokedex.py` referme le client à chaque fois.

Le reste est identique au cours : un client par processus, des timeouts explicites, `tz_aware=True`.

---

## 2.2 La connexion reste paresseuse

`get_client()` ne se connecte à rien. Il construit un objet, prépare un pool, et rend la main. Tant que vous n'envoyez pas une commande, vous ne savez **pas** si MongoDB répond.

C'est la leçon du § 5.5 du cours, et elle est encore plus visible ici : au chapitre 01, l'API a démarré normalement alors même que le dépôt ne parlait pas à la base.

Une seule commande tranche :

```python
await client.admin.command("ping")
```

---

## 2.3 Ce que doit renvoyer `sante()`

Le bandeau en haut de l'interface affiche `MongoDB 8.0.30 - 15 espèces`, ou `base hors ligne`. Il consomme cette forme :

```json
{"mongo": "ok", "version": "8.0.30", "especes": 15}
```

Trois informations, trois appels :

| | |
|---|---|
| le serveur répond ? | `await client.admin.command("ping")` |
| quelle version ? | `await client.server_info()` |
| combien d'espèces ? | `await self.col.count_documents({})` |

### À faire - `repository.py`

Remplacez le corps de `sante()` :

```python
    async def sante(self) -> dict[str, Any]:
        """Force la connexion : sans le ping, le client reste paresseux."""
        await self.db.client.admin.command("ping")
        info = await self.db.client.server_info()
        return {"mongo": "ok", "version": info["version"],
                "especes": await self.col.count_documents({})}
```

Le marqueur `# <- a supprimer au chapitre 02` disparaît avec la ligne `return fixtures.SANTE`.

`self.db.client` : depuis une base, on remonte à son client. Et `admin` parce que `ping` est une commande d'administration, qui ne vit pas dans la base applicative.

---

## 2.4 Vérifier

L'API se recharge toute seule (`uvicorn --reload`).

```bash
curl -s localhost:8000/api/sante
```

```json
{"mongo":"ok","version":"8.0.30","especes":15}
```

Rechargez `http://localhost:8080` : le bandeau affiche maintenant **15 espèces**, alors que la grille en montre treize. Le mensonge du chapitre 01 devient visible à l'écran, dans la même page.

Coupez la base :

```bash
docker compose stop mongo
curl -s -o /dev/null -w "%{http_code} en %{time_total}s\n" localhost:8000/api/sante
```

```
503 en 5.02s
```

Cinq secondes, pas un gel : c'est `serverSelectionTimeoutMS=5_000` qui a fait son travail. Le bandeau passe à **base hors ligne**, et le reste de l'interface continue de servir ses fixtures.

```bash
docker compose start mongo
docker compose exec api pytest -k chapitre02
```

> ⚠️ **Ne mettez jamais de `try/except` autour du `ping` dans le dépôt.** La traduction en 503 est déjà faite dans `app.py`. Un dépôt qui avale ses erreurs renvoie « tout va bien » à un serveur mort.

---

## Exercice (10 min)

`sante()` fait trois allers-retours réseau. Écrivez une variante `sante_rapide()` qui n'en fait qu'un seul, en interrogeant `hello` plutôt que `ping`.

1. Trouvez la commande d'administration qui renvoie déjà la version du serveur dans sa réponse.
2. Écrivez la méthode, et comparez les temps avec `time.perf_counter()`.
3. Question : pourquoi le dépôt garde-t-il quand même la version en trois appels ?

<details>
<summary>Voir la correction</summary>

```python
    async def sante_rapide(self) -> dict[str, Any]:
        """Un seul aller-retour : hello contient deja tout ce qu'on veut."""
        reponse = await self.db.client.admin.command("hello")
        return {"mongo": "ok",
                "version": reponse.get("version", "?"),
                "especes": await self.col.count_documents({})}
```

```python
import time

debut = time.perf_counter()
await depot.sante()
print(f"{(time.perf_counter() - debut) * 1000:.1f} ms")
```

En local, la différence se compte en une poignée de millisecondes - le pool est déjà chaud. Sur un Atlas à l'autre bout de l'Europe, chaque aller-retour coûte 30 à 80 ms : la variante devient trois fois plus rapide.

3. Deux raisons. D'abord `hello` ne garantit pas le champ `version` sur toutes les topologies - `server_info()`, lui, appelle `buildInfo`, dont c'est le contrat. Ensuite `ping` est la commande la plus légère du serveur, et c'est **elle seule** qui prouve que la connexion est vivante : `server_info()` peut répondre depuis un cache de topologie.

Sur une route de diagnostic appelée toutes les trente secondes, la lisibilité l'emporte. Sur une sonde de santé Kubernetes appelée toutes les secondes, on choisirait la variante rapide.

</details>

---

## ✅ Ce qu'il faut retenir

1. `AsyncMongoClient` remplace `MongoClient` : même API, avec `await`. Motor est mort.
2. Le client **se lie à la boucle asyncio qui le crée** : jamais au niveau du module, toujours paresseusement.
3. La connexion reste paresseuse. Seul `await client.admin.command("ping")` prouve que le serveur répond.
4. `serverSelectionTimeoutMS` transforme un gel en erreur en cinq secondes.
5. Le dépôt ne traduit rien en HTTP : il lève, `app.py` traduit.

→ **[Chapitre 03 - Lire la liste des espèces](03-lire-la-liste.md)**
