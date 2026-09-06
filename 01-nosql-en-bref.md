[← Sommaire](README.md) · [Étape suivante →](02-mongodb-decouverte.md)

# Étape 01 - Le NoSQL en bref

> 🎯 **Objectif** : poser le vocabulaire et comprendre l'échange que l'on accepte en quittant le relationnel.
> ⏱️ **Durée** : 20 minutes. C'est un rappel : pas de manipulation, on lit et on discute.

---

## 1.1 D'où vient le besoin

Le modèle relationnel (Codd, 1970) est excellent et le reste. Trois frictions ont poussé à chercher autre chose à partir des années 2007-2010 :

1. **L'impédance objet-relationnel.** Un objet métier "commande" est un arbre : un client, des lignes, une adresse, un paiement. En SQL on l'éclate sur cinq tables, puis on le recolle à chaque lecture avec des jointures et un ORM.
2. **La scalabilité horizontale.** Un SGBD relationnel grandit d'abord *verticalement* - une machine plus grosse. Répartir jointures et transactions sur cinquante machines coûte très cher.
3. **La rigidité du schéma.** `ALTER TABLE` sur une table de 500 millions de lignes, en production, alors que le produit change de forme toutes les deux semaines.

**NoSQL ne veut pas dire "sans SQL" mais *Not Only SQL***. On accepte de perdre des garanties (jointures universelles, schéma imposé par le serveur, parfois la cohérence immédiate) pour gagner ailleurs : débit, élasticité, souplesse de modèle.

## 1.2 Les quatre familles

| Famille | Modèle de données | Exemples | Usage typique |
|---|---|---|---|
| **Clé-valeur** | `clé → blob` | Redis, Valkey, DynamoDB | cache, sessions, compteurs |
| **Document** | `clé → document JSON/BSON` | **MongoDB**, Couchbase, Firestore | catalogues, CMS, profils, événements métier |
| **Colonnes larges** | `clé → familles de colonnes` | Cassandra, ScyllaDB | séries temporelles massives, écriture très forte |
| **Graphe** | nœuds + arêtes | Neo4j, Memgraph | réseaux sociaux, fraude, recommandation |

À côté existent les moteurs de recherche (Elasticsearch), les bases vectorielles (Qdrant, Milvus) et les bases de séries temporelles (InfluxDB). Les frontières s'estompent : PostgreSQL sait stocker du `jsonb`, MongoDB sait faire de la recherche plein texte et vectorielle.

**MongoDB appartient à la famille documentaire.** Une phrase à retenir, car elle explique presque toutes les décisions du reste du cours :

> **Le document est à la fois l'unité de stockage, l'unité de requête et l'unité d'atomicité.**

## 1.3 Les quatre spécificités du travail en documentaire

C'est le cœur de ce cours. Chacune est reprise en profondeur dans une étape dédiée.

### ① Deux documents d'une même collection peuvent être différents

C'est **la** spécificité qui surprend. Il n'y a pas de définition de colonnes : chaque document porte ses propres champs.

```json
{ "sku": "KBD-0001", "nom": "Clavier 60%",  "prix": 89.9,  "switches": "rouge" }
{ "sku": "SCR-0002", "nom": "Écran 27\"",   "prix": 249.0, "pouces": 27, "hz": 144 }
{ "sku": "ABO-0003", "nom": "Support Pro",  "prix": 19.0,  "periodicite": "mensuelle" }
```

Trois documents, une seule collection, trois formes différentes - et c'est **normal**, pas un accident. C'est ce qui permet de faire cohabiter des produits hétérogènes, et de faire évoluer une application sans migration bloquante.

Le revers : **votre code ne peut plus supposer qu'un champ existe.** `doc["hz"]` plantera sur le clavier. On apprendra à écrire des lectures qui tiennent la route à l'[étape 10](10-schema-souple.md).

### ② Le schéma n'a pas disparu - il a déménagé

Il est passé de la base vers **votre code**. Ce n'est pas moins de travail, c'est un travail déplacé : si personne ne décide de la forme des documents, chaque développeur invente la sienne et la collection devient un dépotoir en six mois. Les garde-fous existent (validation JSON Schema côté serveur, Pydantic côté Python) : on les posera à l'étape 10.

### ③ On ne modélise pas les données, on modélise les requêtes

En SQL, on normalise d'abord, on requête ensuite. En documentaire, c'est l'inverse : on part de l'écran ou de l'endpoint à servir, et on range dans un même document ce qui sera **lu ensemble**. Un document bien conçu se lit en une requête, sans jointure ([étape 11](11-modeliser.md)).

Conséquence directe : **la duplication de données est un choix normal**, pas une faute. Elle a un prix - il faut décider qui est propriétaire de la donnée et comment on met à jour les copies.

### ④ Pas d'intégrité référentielle, pas de jointure gratuite

Il n'y a ni `FOREIGN KEY`, ni `ON DELETE CASCADE`. Rien n'empêche une commande de pointer vers un client supprimé : c'est votre application qui garantit la cohérence. Une "jointure" existe (`$lookup`), mais elle est plus coûteuse qu'un `JOIN` SQL bien indexé, et son usage massif est le signe d'une modélisation à revoir.

## 1.4 Cohérence : CAP en une minute

**CAP** : en cas de **P**artition réseau, un système distribué doit choisir entre **C**ohérence et disponibilité (**A**vailability). On ne choisit pas P : on la subit.

- MongoDB par défaut est **CP** : si le nœud primaire est isolé, il refuse les écritures le temps d'élire un remplaçant plutôt que de laisser les données diverger.
- Cassandra ou DynamoDB penchent **AP** : on écrit partout, on réconcilie ensuite.

Particularité utile de MongoDB : ce curseur est **réglable opération par opération** (`writeConcern`, `readConcern`, `readPreference`). On n'est pas "éventuellement cohérent" par fatalité - on le décide.

## 1.5 Quand *ne pas* choisir du documentaire

Restez sur un relationnel si :

- les données sont fortement **normalisées et très reliées** entre elles (comptabilité, ERP, référentiels partagés) ;
- les requêtes sont **imprévisibles et analytiques** - le documentaire s'optimise pour des accès connus à l'avance ;
- vous avez besoin d'**intégrité référentielle native** ;
- l'équipe et l'outillage sont entièrement SQL et le volume tient sur une machine.

> La bonne question n'est jamais "SQL ou NoSQL ?" mais **"quelles sont mes requêtes, à quelle fréquence, avec quelles garanties ?"**. Le reste en découle. Et beaucoup d'architectures saines utilisent les deux.

---

## Exercice (5 min)

Pour chacun de ces besoins, dites : documentaire ou relationnel, et pourquoi ?

1. Le catalogue d'une boutique en ligne : 40 000 produits de familles très différentes (vêtements, électronique, livres), affichés sur une fiche produit.
2. La comptabilité d'une PME : écritures, journaux, balances, clôtures annuelles.
3. Le stockage des événements d'une application mobile : 5 millions par jour, relus par période.
4. Un référentiel RH : salariés, contrats, services, historiques de poste, requêtes croisées imprévues.

<details>
<summary>Voir la correction</summary>

1. **Documentaire.** Les familles ont des attributs différents (spécificité ①), la fiche produit se lit d'un bloc, et le volume grossit par ajout de familles - exactement le point fort du modèle.
2. **Relationnel.** Intégrité stricte, écritures liées entre elles, obligations légales, requêtes analytiques transverses.
3. **Documentaire** (ou base de séries temporelles). Écriture massive, schéma d'événement variable selon le type, lecture par plage de dates.
4. **Relationnel.** Beaucoup d'entités reliées, requêtes croisées non anticipées : c'est le terrain du SQL.

</details>

---

## ✅ Ce qu'il faut retenir

1. NoSQL = *Not Only SQL* : quatre familles, MongoDB est **documentaire**.
2. Le document est l'unité de stockage, de requête **et** d'atomicité.
3. Dans une collection, **les documents peuvent avoir des formes différentes** - c'est une fonctionnalité, à condition de la maîtriser.
4. Le schéma n'a pas disparu, il est passé dans votre code.
5. On modélise les requêtes, pas les entités ; la duplication est un choix assumé, pas une faute.

→ **[Étape 02 - MongoDB, découverte](02-mongodb-decouverte.md)**
