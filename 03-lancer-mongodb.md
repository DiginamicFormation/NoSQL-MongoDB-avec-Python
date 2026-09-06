[← Étape 02](02-mongodb-decouverte.md) · [Sommaire](README.md) · [Étape suivante →](04-premiers-pas-mongosh.md)

# Étape 03 - Lancer MongoDB

> 🎯 **Objectif** : avoir un MongoDB qui tourne, en local avec Docker, puis dans le cloud avec Atlas.
> ⏱️ **Durée** : 30 minutes.
> 📁 **Vous travaillez dans** : le dossier `boutique/` créé au sommaire.

---

## 3.1 Le plus rapide : `docker run`

Pourquoi Docker ? Pas d'installation système, une version identique pour toute l'équipe, une remise à zéro instantanée, et plusieurs versions en parallèle. En 2026, c'est la façon normale de faire tourner une base en développement.

### À faire

```bash
docker run -d --name mongo-dev \
  -p 27017:27017 \
  -e MONGO_INITDB_ROOT_USERNAME=admin \
  -e MONGO_INITDB_ROOT_PASSWORD=motdepasse \
  -v mongo-data:/data/db \
  mongo:8.0
```

### Ce qui se passe

| Option | Rôle |
|---|---|
| `-d` | démarre en arrière-plan |
| `-p 27017:27017` | publie le port MongoDB sur votre machine |
| `-e MONGO_INITDB_ROOT_*` | crée le super-utilisateur **et active l'authentification** |
| `-v mongo-data:/data/db` | volume nommé : **sans lui, tout est perdu quand le conteneur est supprimé** |
| `mongo:8.0` | version épinglée - n'utilisez jamais `latest` |

Vérifiez :

```bash
docker ps                       # le conteneur doit être "Up"
docker logs mongo-dev | tail    # "Waiting for connections" en fin de log
```

Et connectez-vous au shell embarqué dans l'image :

```bash
docker exec -it mongo-dev mongosh -u admin -p motdepasse --authenticationDatabase admin
```

Vous devez obtenir une invite `test>`. Tapez `exit` pour sortir - on y reviendra à l'étape suivante.

> ⚠️ **`--authenticationDatabase admin`** : l'utilisateur `admin` est déclaré dans la base `admin`, pas dans votre base applicative. Oublier cette option donne un `Authentication failed` incompréhensible. C'est l'équivalent du paramètre `authSource` dans les URI (étape 05).

Nettoyage, maintenant qu'on a compris :

```bash
docker rm -f mongo-dev
```

---

## 3.2 La vraie configuration de dev : Docker Compose

Une ligne de commande de dix options ne se partage pas et ne se versionne pas. On passe à un fichier.

### À faire

Créez `compose.yaml` dans `boutique/` :

```yaml
name: boutique

services:
  mongo:
    image: mongo:8.0
    container_name: boutique-mongo
    restart: unless-stopped
    ports:
      - "127.0.0.1:27017:27017"       # accessible uniquement depuis votre machine
    environment:
      MONGO_INITDB_ROOT_USERNAME: ${MONGO_USER}
      MONGO_INITDB_ROOT_PASSWORD: ${MONGO_PASSWORD}
      MONGO_INITDB_DATABASE: ${MONGO_DB}
    volumes:
      - mongo-data:/data/db
      - ./init:/docker-entrypoint-initdb.d:ro
    healthcheck:
      test: ["CMD", "mongosh", "--quiet", "--eval", "db.adminCommand('ping').ok"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 20s

volumes:
  mongo-data:
```

Puis `.env` à côté :

```dotenv
MONGO_USER=admin
MONGO_PASSWORD=change-moi
MONGO_DB=boutique
```

Et `.gitignore` :

```gitignore
.env
.venv/
__pycache__/
```

Enfin, un script d'initialisation `init/01-init.js` - il crée l'**utilisateur applicatif** que Python utilisera :

```javascript
// Exécuté sur la base MONGO_INITDB_DATABASE, au tout premier démarrage
db.createUser({
  user: "app",
  pwd: "app-password",
  roles: [{ role: "readWrite", db: "boutique" }]
});
```

Démarrez :

```bash
docker compose up -d
docker compose ps          # attendez l'état "healthy"
```

### Ce qui se passe

- `127.0.0.1:27017:27017` limite l'exposition à votre machine. Une base ouverte sur Internet est repérée et rançonnée en quelques heures : c'est un classique depuis 2017.
- Le `healthcheck` permet à d'autres services (et à vous) de savoir quand la base est **réellement prête**, pas seulement démarrée.
- Tout fichier `.js` ou `.sh` déposé dans `/docker-entrypoint-initdb.d` est joué **au premier démarrage uniquement**, quand `/data/db` est vide.
- L'utilisateur `app` a le rôle `readWrite` **sur une seule base**. C'est la règle : une application n'est jamais `root`.

> ⚠️ **"Mon script d'init ne fait rien."** Il n'est rejoué que si le volume est vide. Après modification :
> ```bash
> docker compose down -v && docker compose up -d     # -v supprime les données !
> ```

### Les commandes du quotidien

```bash
docker compose up -d              # démarrer
docker compose ps                 # état et santé
docker compose logs -f mongo      # suivre les logs
docker compose exec mongo mongosh -u admin -p change-moi --authenticationDatabase admin
docker compose down               # arrêter, en gardant les données
docker compose down -v            # ⚠️ arrêter ET tout effacer
```

---

## 3.3 Variante utile : le replica set mono-nœud

Un serveur MongoDB seul ne sait pas faire de **transactions multi-documents** ni de **change streams** : ces deux fonctions exigent un *replica set*. En développement, on en monte un à un seul nœud.

Vous n'en avez pas besoin pour le CRUD de ce cours - gardez cette section sous le coude pour le jour où vous verrez `Transaction numbers are only allowed on a replica set member`.

```yaml
name: boutique-rs

services:
  mongo:
    image: mongo:8.0
    container_name: boutique-mongo-rs
    command: ["--replSet", "rs0", "--bind_ip_all"]
    ports:
      - "127.0.0.1:27017:27017"
    volumes:
      - mongo-rs-data:/data/db
    healthcheck:
      # initialise le replica set au premier passage, puis sert de sonde
      test: >
        mongosh --quiet --eval "
          try { rs.status().ok }
          catch (e) { rs.initiate({_id:'rs0', members:[{_id:0, host:'localhost:27017'}]}).ok }
        "
      interval: 5s
      timeout: 10s
      retries: 30
      start_period: 5s

volumes:
  mongo-rs-data:
```

La chaîne de connexion devient alors :

```
mongodb://localhost:27017/?directConnection=true
```

> **Pourquoi `directConnection=true` ?** Le driver interroge normalement la topologie et utilise l'adresse annoncée par le replica set. `directConnection` court-circuite cette découverte : c'est la façon la plus fiable de joindre un replica set mono-nœud conteneurisé.
>
> Ce compose est **sans authentification** : un replica set authentifié exige un *keyfile* partagé entre les nœuds, hors sujet ici. Il n'écoute que sur `127.0.0.1`. En production : authentification, keyfile et TLS, sans exception.

---

## 3.4 L'autre chemin : MongoDB Atlas

**Atlas** est le service managé officiel : des clusters hébergés chez AWS, GCP ou Azure, avec sauvegardes, supervision et sécurité pris en charge. Le niveau **M0 est gratuit** et suffit largement pour ce cours.

### À faire

1. Créez un compte sur **cloud.mongodb.com** (une organisation, puis un projet).
2. **Build a Database** → **M0 Free** → fournisseur, puis **la région la plus proche** (par exemple AWS `eu-west-3`, Paris) → nommez le cluster.
3. **Database Access** → *Add New Database User* → authentification par mot de passe → rôle **`readWrite` sur votre base**, surtout pas `atlasAdmin`. Notez le mot de passe : il ne sera plus affiché.
4. **Network Access** → *Add IP Address* → "Add Current IP Address". `0.0.0.0/0` dépanne en formation mais **ne doit jamais rester** ailleurs.
5. **Connect** → *Drivers* → *Python* → copiez la chaîne `mongodb+srv://…`.
6. Menu "…" du cluster → **Load Sample Dataset** : installe `sample_mflix`, `sample_airbnb`… un excellent terrain d'entraînement, et le jeu de données de la documentation officielle.

### La chaîne de connexion SRV

```
mongodb+srv://app:motdepasse@cluster0.ab1cd.mongodb.net/?retryWrites=true&w=majority&appName=Formation
```

| Élément | Rôle |
|---|---|
| `mongodb+srv://` | découvre les nœuds via un enregistrement DNS SRV - **nécessite le paquet `dnspython`** (étape 05) |
| `retryWrites=true` | réessaie automatiquement une écriture en cas de bascule |
| `w=majority` | l'écriture n'est acquittée qu'une fois répliquée sur la majorité des nœuds |
| `appName` | votre application apparaît sous ce nom dans les logs et le profiler Atlas |

> ⚠️ **Mot de passe avec des caractères spéciaux** (`@ : / ? # [ ] %`) : il doit être encodé pour l'URL. En Python : `urllib.parse.quote_plus(mdp)`.
>
> ⚠️ **Ne mettez jamais cette chaîne dans le code ni dans Git.** Variable d'environnement, fichier `.env` ignoré, ou gestionnaire de secrets.

### Local ou Atlas ?

| Critère | Docker local | Atlas M0 |
|---|---|---|
| Coût | gratuit | gratuit (512 Mo) |
| Fonctionne hors ligne | ✅ | ❌ |
| Replica set, transactions | à configurer (§ 3.3) | ✅ natif |
| Sauvegardes, supervision | à faire soi-même | ✅ |
| Réalisme production | moyen | élevé |

**En pratique** : on développe et on teste sur Docker, on déploie sur Atlas. Et **le code Python ne change pas** - seule la chaîne de connexion diffère. C'est le test décisif d'une application bien écrite, et on le vérifiera à l'étape 05.

---

## 3.5 Les outils à connaître

| Outil | Rôle |
|---|---|
| **mongosh** | le shell officiel (JavaScript) - déjà présent dans l'image Docker |
| **MongoDB Compass** | l'interface graphique officielle : explorer, éditer, visualiser un `explain` |
| **MongoDB for VS Code** | des *playgrounds* `.mongodb.js` directement dans l'éditeur |
| **Database Tools** | `mongodump`, `mongorestore`, `mongoimport`, `mongoexport` |

Installer **Compass** est vivement conseillé : voir ses documents s'afficher aide énormément à comprendre l'hétérogénéité de l'étape 10. Connectez-le avec `mongodb://admin:change-moi@localhost:27017/?authSource=admin`.

---

## Exercice (10 min)

1. Démarrez la pile Compose, puis **arrêtez-la et redémarrez-la**. Les données sont-elles toujours là ?
2. Faites `docker compose down -v`, redémarrez, et vérifiez ce qui a changé.
3. Trouvez, dans les logs, la ligne qui indique que le serveur écoute.

<details>
<summary>Voir la correction</summary>

1. `docker compose down && docker compose up -d` : les données sont conservées, elles vivent dans le **volume nommé** `mongo-data`, pas dans le conteneur.
2. `down -v` supprime le volume : la base repart vide, et le script `init/01-init.js` est **rejoué** (c'est la seule façon de le relancer). C'est utile pour repartir propre, et dangereux partout ailleurs.
3. `docker compose logs mongo | grep -i "waiting for connections"` - la ligne apparaît une fois l'initialisation terminée.

</details>

---

## ✅ Ce qu'il faut retenir

1. Un volume nommé, sinon les données disparaissent avec le conteneur.
2. Épinglez la version de l'image (`mongo:8.0`), publiez le port sur `127.0.0.1` seulement.
3. Les scripts de `docker-entrypoint-initdb.d` ne sont joués **qu'une fois**, sur un volume vide.
4. L'application utilise un compte `readWrite` sur **une seule base** ; jamais le compte root.
5. Transactions et change streams exigent un **replica set**, même à un seul nœud.
6. Atlas M0 est gratuit : seule l'URI change entre local et cloud.

→ **[Étape 04 - Premiers pas dans mongosh](04-premiers-pas-mongosh.md)**
