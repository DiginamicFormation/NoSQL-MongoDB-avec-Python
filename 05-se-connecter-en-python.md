[← Étape 04](04-premiers-pas-mongosh.md) · [Sommaire](README.md) · [Étape suivante →](06-crud-creer.md)

# Étape 05 - Se connecter en Python

> 🎯 **Objectif** : installer PyMongo, écrire un module de connexion propre et réutilisable, et savoir diagnostiquer une connexion qui échoue.
> ⏱️ **Durée** : 40 minutes.
> 📁 **On crée** : `boutique/.venv`, `boutique/.env`, `boutique/db.py`.

---

## 5.1 Quelle bibliothèque ?

| Bibliothèque | Rôle | Verdict |
|---|---|---|
| **PyMongo** | driver **officiel**, API synchrone **et** asynchrone | **c'est celle qu'on utilise** |
| Motor | ancien driver asynchrone | ❌ déprécié en 2025, fin de vie en 2026 - l'asynchrone se fait avec `AsyncMongoClient` de PyMongo |
| Beanie, ODMantic, MongoEngine | ODM ("ORM documentaire") | pratiques, mais construits **sur** PyMongo : apprenez PyMongo d'abord |
| PyMongoArrow | export vers pandas / Arrow | pour l'analytique |
| Django MongoDB Backend | backend officiel pour l'ORM Django | pour les projets Django |

Ce cours utilise **PyMongo seul**. Vous verrez exactement ce qui part sur le réseau, sans magie intermédiaire.

---

## 5.2 Installer

### À faire

```bash
cd boutique
python -m venv .venv
source .venv/bin/activate          # Windows : .venv\Scripts\activate
pip install "pymongo[srv]" python-dotenv
```

Ou avec `uv`, plus rapide :

```bash
uv init . && uv add "pymongo[srv]" python-dotenv
```

Vérifiez :

```bash
python -c "import pymongo; print(pymongo.version)"     # 4.18.x
```

### Pourquoi `[srv]` ?

C'est un "extra" qui installe `dnspython`, indispensable aux URI `mongodb+srv://` d'Atlas. Sans lui : `ConfigurationError: The "dnspython" module must be installed`. Autres extras utiles : `pymongo[snappy,zstd]` (compression réseau), `pymongo[encryption]`, `pymongo[aws]`.

> ⚠️ **N'installez jamais le paquet `bson` depuis PyPI.** Il entre en conflit avec le module `bson` livré avec PyMongo. Symptôme : `ImportError: cannot import name 'ObjectId' from 'bson'`. Remède : `pip uninstall bson` puis `pip install --force-reinstall pymongo`.

---

## 5.3 Comprendre l'URI de connexion

```
mongodb://app:app-password@localhost:27017/boutique?authSource=boutique
└──┬───┘ └──────┬────────┘ └──────┬───────┘ └──┬───┘ └────────┬────────┘
 schéma    identifiants        hôte:port      base         options
```

| Élément | Rôle |
|---|---|
| `mongodb://` | connexion directe aux hôtes listés |
| `mongodb+srv://` | découverte des nœuds par DNS SRV (Atlas) |
| `authSource=` | **la base où l'utilisateur est déclaré**, pas celle qu'on interroge |
| `directConnection=true` | ne pas découvrir la topologie (replica set mono-nœud en Docker) |
| `retryWrites` / `retryReads` | réessai automatique (activés par défaut) |
| `w=majority` | durabilité de l'écriture |
| `appName=` | identifie votre application dans les logs du serveur |

`authSource` est la cause n°1 des `Authentication failed` : notre utilisateur `app` a été créé dans la base `boutique` (script d'init de l'étape 03), donc `authSource=boutique`. Le compte `admin`, lui, vit dans la base `admin`, d'où `authSource=admin`.

### À faire - le fichier `.env`

```dotenv
MONGODB_URI=mongodb://app:app-password@localhost:27017/boutique?authSource=boutique
MONGODB_DB=boutique
```

Il est déjà dans `.gitignore` (étape 03). **Aucune chaîne de connexion ne doit apparaître dans le code.**

---

## 5.4 Le module de connexion

### À faire - `db.py`

```python
"""Connexion unique à MongoDB, partagée par toute l'application."""
import os
from functools import lru_cache

from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.database import Database

load_dotenv()


@lru_cache(maxsize=1)          # ← un seul client par processus
def get_client() -> MongoClient:
    return MongoClient(
        os.environ["MONGODB_URI"],
        serverSelectionTimeoutMS=5_000,   # échouer vite si le serveur est absent
        connectTimeoutMS=5_000,
        tz_aware=True,                    # renvoie des datetime "aware" (UTC)
        uuidRepresentation="standard",
        appname=os.getenv("APP_NAME", "boutique"),
    )


def get_db() -> Database:
    return get_client()[os.environ.get("MONGODB_DB", "boutique")]


if __name__ == "__main__":
    client = get_client()
    client.admin.command("ping")
    print("Connecté à MongoDB", client.server_info()["version"])
    print("Bases visibles :", client.list_database_names())
```

```bash
python db.py
```

Résultat attendu :

```
Connecté à MongoDB 8.0.x
Bases visibles : ['boutique']
```

### Ce qui se passe, ligne par ligne

- **`serverSelectionTimeoutMS=5000`** : sans ce réglage, PyMongo attend **30 secondes** avant d'abandonner. En développement, c'est insupportable ; en production, ça masque les pannes.
- **`tz_aware=True`** : les dates relues sont des `datetime` avec fuseau (UTC). Sans cela, vous récupérez des datetimes naïfs et les comparaisons deviennent fausses au premier changement d'heure.
- **`appname`** : votre application est identifiable dans les logs serveur et dans le profiler Atlas. Gratuit, et précieux le jour d'un incident.
- **`@lru_cache`** : garantit **un seul client par processus**.

---

## 5.5 Les deux surprises de PyMongo

### Surprise n°1 : `MongoClient(...)` ne se connecte pas

La construction du client est **non bloquante**. Elle prépare un pool de connexions et lance la découverte de la topologie en tâche de fond. Un serveur éteint ou un mot de passe faux ne produit **aucune erreur sur cette ligne** - l'exception surgira à la première opération réelle, après le délai de `serverSelectionTimeoutMS`.

Faites l'expérience :

```bash
docker compose stop mongo
python db.py                      # observez : ~5 s d'attente, puis ServerSelectionTimeoutError
docker compose start mongo
```

C'est exactement pour cela que `db.py` fait un `ping` explicite au démarrage : **échouer tôt, avec un message clair**, plutôt qu'au milieu du traitement d'une requête utilisateur.

### Surprise n°2 : les crochets ne créent rien, et ne vérifient rien

```python
db = client["boutique"]
produits = db["produits"]
fantome = db["prodiuts"]          # faute de frappe volontaire
print(fantome.count_documents({}))   # → 0, aucune erreur
```

`client["…"]` et `db["…"]` sont de simples **poignées** : aucun aller-retour réseau, aucune vérification d'existence. Une faute de frappe dans un nom de collection ne lève donc jamais d'exception - elle renvoie silencieusement zéro résultat. C'est le bug n°1 des débutants, et il coûte parfois une demi-journée.

Le réflexe de vérification :

```python
print(get_db().list_collection_names())
```

---

## 5.6 Les quatre règles du cycle de vie

1. **Un seul `MongoClient` par processus**, créé au démarrage, partagé partout. Il est *thread-safe* et gère son pool. En créer un par requête HTTP est l'erreur de performance n°1 : chaque client rouvre des sockets, refait la découverte de topologie et l'authentification.
2. La connexion est **paresseuse** : ajoutez un `ping` au démarrage (§ 5.5).
3. **Ne partagez jamais un client entre processus** (`fork`). Avec Gunicorn ou uvicorn en multi-workers, créez-le **après** le fork.
4. **Fermez proprement** : `client.close()` à l'arrêt.

Exemple avec FastAPI, où les quatre règles sont respectées :

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from pymongo import MongoClient
import os

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.client = MongoClient(os.environ["MONGODB_URI"], tz_aware=True)
    app.state.db = app.state.client[os.environ["MONGODB_DB"]]
    app.state.client.admin.command("ping")     # échec au démarrage, pas en production
    yield
    app.state.client.close()

app = FastAPI(lifespan=lifespan)
```

---

## 5.7 Diagnostiquer une connexion qui échoue

Le tableau à garder sous la main :

| Message | Cause probable | Correctif |
|---|---|---|
| `ServerSelectionTimeoutError: [Errno 111] Connection refused` | conteneur arrêté, mauvais port | `docker compose ps`, vérifier le mapping de ports |
| `Authentication failed` | mauvais mot de passe **ou** mauvais `authSource` | ajouter `?authSource=boutique` (ou `admin`) |
| `ConfigurationError: The "dnspython" module must be installed` | URI `mongodb+srv://` sans l'extra | `pip install "pymongo[srv]"` |
| `[SSL: CERTIFICATE_VERIFY_FAILED]` | certificats système absents (fréquent sur macOS) | installer les certificats, mettre à jour `certifi` |
| Atlas : timeout alors que tout semble bon | votre IP n'est pas autorisée | Network Access → *Add Current IP Address* |
| `Transaction numbers are only allowed on a replica set member` | serveur standalone | passer au compose replica set (§ 3.3) |
| Aucune erreur, mais **zéro résultat** | faute de frappe dans le nom de base ou de collection | `client.list_database_names()`, `db.list_collection_names()` |

La boîte à outils :

```python
client.list_database_names()        # bases visibles par cet utilisateur
db.list_collection_names()          # collections de la base
db.command("ping")                  # le serveur répond-il ?
client.server_info()["version"]     # version du serveur
db.command("connectionStatus")      # qui suis-je, quels rôles ai-je ?
```

---

## 5.8 Basculer sur Atlas : une variable, rien d'autre

C'est le test décisif du code que vous venez d'écrire. Remplacez **uniquement** l'URI dans `.env` :

```dotenv
MONGODB_URI=mongodb+srv://app:motdepasse@cluster0.ab1cd.mongodb.net/?retryWrites=true&w=majority
MONGODB_DB=boutique
```

```bash
python db.py
```

Si cela fonctionne sans toucher à `db.py`, votre configuration ne fuit pas dans le code. Si vous devez modifier autre chose, corrigez-le maintenant : le problème ne fera que grandir.

Pour transférer aussi les données :

```bash
mongodump --uri="mongodb://app:app-password@localhost:27017/boutique?authSource=boutique" --out=dump/
mongorestore --uri="mongodb+srv://app:motdepasse@cluster0.ab1cd.mongodb.net" \
             --nsFrom='boutique.*' --nsTo='boutique.*' dump/
```

Repassez ensuite sur l'URI locale pour la suite du cours.

---

## Exercice (10 min)

1. Écrivez `verifier.py` qui affiche : la version du serveur, la liste des bases, la liste des collections de `boutique`, et le nombre de documents dans `produits`.
2. Provoquez volontairement chacune des trois erreurs suivantes, et notez le message exact : mauvais mot de passe, mauvais port, mauvais nom de collection.

<details>
<summary>Voir la correction</summary>

```python
# verifier.py
from db import get_client, get_db

client, db = get_client(), get_db()

print("Serveur      :", client.server_info()["version"])
print("Bases        :", client.list_database_names())
print("Collections  :", db.list_collection_names())
print("Produits     :", db.produits.count_documents({}))
```

Les trois erreurs :

- **mauvais mot de passe** → `OperationFailure: Authentication failed` (au premier accès, pas à la construction du client) ;
- **mauvais port** (par exemple `27018`) → `ServerSelectionTimeoutError` après 5 secondes ;
- **mauvais nom de collection** → **aucune erreur**, `count_documents` renvoie `0`. C'est la surprise n°2, et la raison pour laquelle on vérifie avec `list_collection_names()`.

</details>

---

## ✅ Ce qu'il faut retenir

1. `pip install "pymongo[srv]"` - l'extra `srv` est requis pour Atlas.
2. **Un client par processus**, créé au démarrage, partagé, fermé à l'arrêt.
3. `MongoClient(...)` ne se connecte pas : faites un `ping` explicite, avec un `serverSelectionTimeoutMS` court.
4. `db["collection"]` ne crée rien et ne vérifie rien : une faute de frappe renvoie zéro résultat, sans erreur.
5. `authSource` = la base où l'utilisateur est déclaré. C'est la cause n°1 des `Authentication failed`.
6. L'URI vit dans `.env`, jamais dans le code : passer de Docker à Atlas ne doit changer qu'une ligne.

→ **[Étape 06 - CRUD 1/4 : Créer](06-crud-creer.md)**
