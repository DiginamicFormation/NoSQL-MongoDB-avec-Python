[← Étape 01](01-nosql-en-bref.md) · [Sommaire](README.md) · [Étape suivante →](03-lancer-mongodb.md)

# Étape 02 - MongoDB, découverte

> 🎯 **Objectif** : savoir d'où vient MongoDB, traduire son vocabulaire depuis MySQL, et comprendre ce qu'est réellement un document.
> ⏱️ **Durée** : 45 minutes. Toujours pas de manipulation - on installe à l'étape suivante.

---

## 2.1 Rapide historique

MongoDB (de *humongous*, "énorme") naît d'un accident heureux. En 2007, la société **10gen** - fondée par Dwight Merriman, Eliot Horowitz et Kevin Ryan, venus de DoubleClick - développe une plateforme applicative de type PaaS. Sa couche de stockage se révèle plus intéressante que le reste : en **2009**, 10gen abandonne le PaaS et publie la base seule, en open source.

| Année | Jalon | Ce que ça change |
|---|---|---|
| 2007 | 10gen démarre le projet | à l'origine, une brique d'un PaaS |
| **2009** | **MongoDB 1.0**, open source | la base devient le produit |
| 2010 | replica sets, sharding | la haute disponibilité arrive |
| 2013 | 10gen devient **MongoDB Inc.** | industrialisation |
| **2015** | **3.0 - moteur WiredTiger** | verrous au niveau **document** et compression : le vrai tournant en performance |
| 2015-2016 | `$lookup`, `$graphLookup`, vues | l'agrégation devient un langage complet |
| **2016** | **MongoDB Atlas** | le managé devient le mode de déploiement majoritaire |
| 2017 | 3.6 : **change streams** · entrée en bourse (NASDAQ : MDB) | temps réel natif |
| **2018** | **4.0 : transactions ACID multi-documents** · licence **SSPL** | l'objection technique n°1 tombe, une objection juridique apparaît |
| 2019 | 4.2 : transactions sur cluster shardé, chiffrement côté client | exploitation à grande échelle |
| 2021 | 5.0 : collections *time series*, API versionnée, `w: majority` par défaut | l'IoT et la stabilité d'API |
| 2022-2023 | 6.0 / 7.0 : Queryable Encryption · **Atlas Vector Search** | conformité, puis IA |
| **2024** | **8.0** : gains de performance, sharding amélioré | la version de ce cours |
| 2025-2026 | rachat de **Voyage AI**, minor releases 8.1 → 8.3, fin de vie du driver **Motor** | MongoDB se positionne sur les applications IA |

Deux enseignements pratiques :

1. **La licence SSPL (2018)** n'est pas reconnue open source par l'OSI. MongoDB a été retiré des dépôts de plusieurs distributions Linux, et des "compatibles" sont apparus chez les hébergeurs (AWS DocumentDB, Azure Cosmos DB API MongoDB) : ils n'implémentent qu'**une partie** de l'API, souvent avec du retard. Si votre code doit tourner sur un compatible, vérifiez ce qui est supporté **avant** de coder. Pour un usage applicatif normal - vous utilisez MongoDB, vous ne le revendez pas comme service - la SSPL ne vous impose rien.
2. **MongoDB ne ressemble plus à sa réputation.** Les critiques que vous lirez ("perd des données", "pas de transactions", "pas de schéma") visent les versions 2.x : avant WiredTiger, avant les transactions, avant `w: "majority"` par défaut. Regardez toujours la date et la version d'un article.

---

## 2.2 MongoDB vs MySQL, sur un cas concret

Le meilleur moyen de comprendre MongoDB quand on vient de MySQL est de modéliser **le même besoin** des deux côtés. Prenons une commande de boutique - client, lignes, adresse de livraison - affichée en entier sur une page "détail commande".

### Le vocabulaire, terme à terme

| MySQL | MongoDB | Nuance importante |
|---|---|---|
| Base (`schema`) | Base (*database*) | équivalent |
| Table | **Collection** | aucune définition de colonnes |
| Ligne | **Document** | arborescent : sous-objets et tableaux |
| Colonne | **Champ** | typé **par document**, pas par collection |
| `PRIMARY KEY` | champ **`_id`** | obligatoire, unique, immuable, indexé d'office |
| `FOREIGN KEY` | *(rien)* | l'intégrité est à la charge de l'application |
| `JOIN` | `$lookup`, ou imbrication | l'idiome est d'imbriquer |
| `GROUP BY` | `$group` (pipeline d'agrégation) | plus expressif |
| Index B-tree | Index B-tree | même principe, plus d'options ([étape 12](12-index-et-performances.md)) |
| Réplication | **Replica set** | bascule automatique intégrée |
| Client `mysql` | Shell `mongosh` | JavaScript au lieu de SQL |

### Côté MySQL : quatre tables

```sql
CREATE TABLE clients (
  id     INT PRIMARY KEY AUTO_INCREMENT,
  email  VARCHAR(255) NOT NULL UNIQUE,
  nom    VARCHAR(120) NOT NULL
);

CREATE TABLE commandes (
  id         INT PRIMARY KEY AUTO_INCREMENT,
  client_id  INT NOT NULL,
  statut     ENUM('panier','payee','expediee') NOT NULL,
  cree_le    DATETIME NOT NULL,
  FOREIGN KEY (client_id) REFERENCES clients(id)
);

CREATE TABLE lignes (
  id            INT PRIMARY KEY AUTO_INCREMENT,
  commande_id   INT NOT NULL,
  sku           VARCHAR(20) NOT NULL,
  libelle       VARCHAR(200) NOT NULL,
  quantite      INT NOT NULL,
  prix_unitaire DECIMAL(10,2) NOT NULL,
  FOREIGN KEY (commande_id) REFERENCES commandes(id) ON DELETE CASCADE
);

CREATE TABLE adresses (
  id          INT PRIMARY KEY AUTO_INCREMENT,
  commande_id INT NOT NULL,
  ligne1      VARCHAR(200), ville VARCHAR(100), cp VARCHAR(10),
  FOREIGN KEY (commande_id) REFERENCES commandes(id)
);
```

Pour afficher la page :

```sql
SELECT c.*, cl.nom, cl.email, l.sku, l.libelle, l.quantite, l.prix_unitaire, a.ville
FROM commandes c
JOIN clients  cl ON cl.id = c.client_id
JOIN lignes   l  ON l.commande_id = c.id
JOIN adresses a  ON a.commande_id = c.id
WHERE c.id = 42;
```

Quatre tables, trois jointures, et un résultat "à plat" qu'il faut recomposer côté application : les colonnes de la commande sont répétées sur chaque ligne.

### Côté MongoDB : un document

```json
{
  "_id": ObjectId("66f0a1b2c3d4e5f600000042"),
  "statut": "payee",
  "cree_le": ISODate("2026-09-06T09:12:00Z"),
  "client":    { "id": 7, "nom": "Dupont", "email": "dupont@example.com" },
  "livraison": { "ligne1": "12 rue des Lilas", "ville": "Lyon", "cp": "69003" },
  "lignes": [
    { "sku": "KBD-0001", "libelle": "Clavier 60%",     "quantite": 1, "prix_unitaire": 89.90 },
    { "sku": "SCR-0002", "libelle": "Ecran 27 pouces", "quantite": 2, "prix_unitaire": 249.00 }
  ],
  "total": 587.90
}
```

Pour afficher la page :

```javascript
db.commandes.findOne({ _id: ObjectId("66f0a1b2c3d4e5f600000042") })
```

**Une lecture, aucune recomposition.** Le document *est* la page. C'est le gain principal du modèle - et il se paie ailleurs.

### Les différences qui comptent

| Sujet | MySQL | MongoDB | Conséquence pour vous |
|---|---|---|---|
| **Schéma** | déclaré, imposé par le serveur | facultatif, validable à la demande | ajouter un champ = l'écrire, mais il faut gérer les anciens documents dans le code |
| **Évolution de structure** | `ALTER TABLE`, verrous, fenêtre de migration | rien à faire | déploiement continu bien plus simple |
| **Lecture d'un agrégat** | `JOIN` + recomposition | un `find_one` | moins de latence, moins de code |
| **Donnée partagée** | normalisée, source unique | dupliquée si imbriquée | il faut un propriétaire et un processus de mise à jour |
| **Intégrité référentielle** | `FOREIGN KEY`, cascade | aucune | les orphelins sont possibles : à vous de les empêcher |
| **Transactions** | natives, quotidiennes | possibles depuis 4.0, mais coûteuses | on préfère "1 document = 1 unité de cohérence" |
| **Requêtes analytiques** | SQL, très mature | pipeline d'agrégation, puissant mais différent | le reporting reste souvent plus simple en SQL |
| **Montée en charge** | verticale, réplicas en lecture | replica set intégré, sharding natif | la haute disponibilité est de série |
| **Typage** | par colonne, imposé | par document | `"12"` et `12` peuvent cohabiter (voir [étape 10](10-schema-souple.md)) |
| **Écritures concurrentes** | verrou ligne (InnoDB) | verrou document (WiredTiger) | comportement comparable |

### ⚠️ Le piège n°1 du développeur SQL

Modéliser MongoDB comme MySQL : une collection par table, des identifiants en guise de clés étrangères, et un `$lookup` à chaque lecture. On obtient alors **le pire des deux mondes** : pas d'intégrité référentielle *et* pas de gain en lecture.

> **Règle de conversion mentale** : ne demandez pas "quelles sont mes entités ?" mais "**quel écran dois-je servir, et en combien de requêtes ?**". Un document se dessine à partir d'une page, pas d'un diagramme entité-association. On y revient en détail à l'[étape 11](11-modeliser.md).

---

## 2.3 Le vocabulaire de MongoDB

```
Déploiement (un serveur mongod, un replica set, ou un cluster shardé)
└── Base de données          (≈ schema SQL)
    └── Collection           (≈ table)
        └── Document         (≈ ligne, mais arborescent, 16 Mo maximum)
            └── Champ        (≈ colonne, mais propre à chaque document)
```

Trois règles à connaître dès maintenant :

1. **Bases et collections sont créées implicitement**, à la première écriture. Aucun `CREATE TABLE` n'est nécessaire. (On en créera quand même explicitement à l'étape 10, pour poser la validation.)
2. **Chaque document a un `_id`** : obligatoire, unique dans la collection, immuable, indexé automatiquement. Si vous ne le fournissez pas, il est généré pour vous.
3. **Un document ne peut pas dépasser 16 Mo**, ni 100 niveaux d'imbrication.

### L'`ObjectId`

C'est le type d'`_id` par défaut : 12 octets, composés de 4 octets de timestamp, 5 aléatoires par processus et 3 de compteur.

```javascript
ObjectId("66f0a1b2c3d4e5f600000042")
```

Deux conséquences pratiques :

- il est **approximativement croissant dans le temps** : trier par `_id` revient presque à trier par date de création, et `objectId.getTimestamp()` donne cette date - pas besoin d'un champ `cree_le` pour un simple ordre chronologique ;
- il est généré **côté client**, par le driver : votre application connaît l'identifiant avant même que le serveur ait répondu.

Vous pouvez aussi choisir un **`_id` métier** - un `sku`, un e-mail, un UUID. C'est parfaitement légitime, cela économise un index unique et rend les imports plus simples. Seule contrainte : il ne sera plus jamais modifiable.

---

## 2.4 BSON : ce que MongoDB stocke réellement

On écrit du JSON, MongoDB stocke du **BSON** (*Binary JSON*) : binaire, rapide à parcourir, **typé** et ordonné. D'où des types qui n'existent pas en JSON.

| Type BSON | En Python | À savoir |
|---|---|---|
| `ObjectId` | `bson.ObjectId` | identifiant par défaut |
| `String` | `str` | UTF-8 |
| `Int32` / `Int64` | `int` | le driver choisit selon la valeur |
| `Double` | `float` | flottant IEEE 754 |
| `Decimal128` | `bson.Decimal128` | **à utiliser pour les montants** |
| `Boolean` | `bool` | |
| `Date` | `datetime.datetime` | en millisecondes, **UTC**, sans fuseau stocké |
| `Array` | `list` | aucun type imposé aux éléments |
| `Object` | `dict` | sous-document |
| `Binary` | `bytes` | fichiers < 16 Mo, UUID |
| `Null` | `None` | **≠ champ absent** |

### Les trois pièges de typage à connaître tout de suite

> ⚠️ **1. `null` n'est pas "absent".**
> `{"remise": null}` (le champ existe, il vaut null) et `{}` (le champ n'existe pas) sont deux documents différents. Mais une requête `{"remise": null}` **retourne les deux**. Pour ne cibler que les documents où le champ manque : `{"remise": {"$exists": false}}`. On y revient à l'étape 10 - c'est la question qui revient toujours.

> ⚠️ **2. Ne stockez pas d'argent dans un `float`.**
> `0.1 + 0.2 != 0.3` en binaire. Utilisez `Decimal128`, ou stockez des centimes en entier. Un catalogue en `Double` finit toujours par produire une facture fausse d'un centime.

> ⚠️ **3. Les dates sont en UTC, sans fuseau.**
> Passez toujours des `datetime` *aware*, et ouvrez le client Python avec `tz_aware=True` (étape 05). Sinon le décalage se propage silencieusement dans toute l'application.

---

## Exercice (10 min)

Voici une table MySQL et son besoin d'affichage. Proposez le document MongoDB équivalent.

```sql
CREATE TABLE articles (id INT PRIMARY KEY, titre VARCHAR(200), corps TEXT, publie_le DATETIME);
CREATE TABLE tags (id INT PRIMARY KEY, nom VARCHAR(50));
CREATE TABLE articles_tags (article_id INT, tag_id INT);
CREATE TABLE commentaires (id INT PRIMARY KEY, article_id INT, auteur VARCHAR(80),
                           texte TEXT, poste_le DATETIME);
```

L'écran à servir : une page d'article, avec son titre, son corps, ses tags et ses **dix derniers** commentaires.

<details>
<summary>Voir la correction</summary>

```json
{
  "_id": ObjectId("..."),
  "titre": "Découvrir MongoDB",
  "corps": "...",
  "publie_le": ISODate("2026-09-06T08:00:00Z"),
  "tags": ["mongodb", "nosql", "python"],
  "nb_commentaires": 137,
  "derniers_commentaires": [
    { "auteur": "alice", "texte": "Très clair !", "poste_le": ISODate("2026-09-06T09:30:00Z") }
  ]
}
```

Les points clés :

- **les tags deviennent un simple tableau de chaînes** : la table de liaison `articles_tags` disparaît. Un index sur `tags` permettra quand même de chercher tous les articles d'un tag ;
- **les commentaires sont imbriqués, mais seulement les dix derniers** - c'est le pattern *Subset* (étape 11). Un article populaire pourrait en avoir 50 000 : les imbriquer tous ferait exploser le document (limite de 16 Mo) et ralentirait chaque lecture. Les autres vont dans une collection `commentaires` séparée ;
- `nb_commentaires` est **pré-calculé** : la page l'affiche sans compter quoi que ce soit (pattern *Computed*).

Si vous avez proposé quatre collections reflétant les quatre tables : c'est exactement le piège n°1 ci-dessus. Relisez le § 2.2.

</details>

---

## ✅ Ce qu'il faut retenir

1. MongoDB est né en 2009 ; tout ce qui compte techniquement (WiredTiger, transactions, `majority`) date de 2015 et après.
2. Table → **collection**, ligne → **document**, colonne → **champ**, `PRIMARY KEY` → **`_id`**, `JOIN` → imbrication.
3. Un document bien conçu correspond à un écran : on le lit d'un coup, sans jointure.
4. Pas de `FOREIGN KEY` : la cohérence entre collections est votre responsabilité.
5. BSON est typé : attention à `null` vs absent, aux montants en `float` et aux dates UTC.

→ **[Étape 03 - Lancer MongoDB](03-lancer-mongodb.md)** : on passe enfin à la pratique.
