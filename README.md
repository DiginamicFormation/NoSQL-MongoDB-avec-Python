# MongoDB & Python

Un cours que l'on **suit clavier en main**, du premier conteneur Docker jusqu'à une petite application Python qui crée, lit, modifie et supprime des documents.

Deux objectifs, et seulement deux :

1. **Savoir écrire un CRUD complet** sur MongoDB en Python (PyMongo).
2. **Comprendre les spécificités du NoSQL documentaire** - à commencer par celle qui déroute le plus quand on vient de SQL : *dans une même collection, deux documents peuvent ne pas avoir les mêmes champs*.

---

## À qui s'adresse ce cours

- Vous programmez en Python (fonctions, dictionnaires, environnements virtuels).
- Vous connaissez un peu SQL (`SELECT`, `INSERT`, `UPDATE`, index).
- Vous n'avez **jamais** utilisé MongoDB, ou seulement effleuré.

**Versions de référence (septembre 2026)** : MongoDB 8.0 · PyMongo 4.18 · mongosh 2.x · Docker Engine 27+ / Compose v2 · Python ≥ 3.11.

---

## Le parcours

Chaque étape est un fichier. On les suit **dans l'ordre** : chacune s'appuie sur la base laissée par la précédente.

| # | Étape | Durée | Ce qu'on y fait |
|---|---|---|---|
| [01](01-nosql-en-bref.md) | Le NoSQL en bref | 20 min | rappel de cadrage : familles, ce qu'on gagne, ce qu'on perd |
| [02](02-mongodb-decouverte.md) | MongoDB, découverte | 45 min | histoire, comparaison avec MySQL sur un cas réel, vocabulaire, BSON |
| [03](03-lancer-mongodb.md) | Lancer MongoDB | 30 min | `docker run`, puis Docker Compose, puis Atlas |
| [04](04-premiers-pas-mongosh.md) | Premiers pas dans mongosh | 40 min | créer, chercher, modifier, supprimer **sans Python** |
| [05](05-se-connecter-en-python.md) | Se connecter en Python | 40 min | PyMongo, URI, `MongoClient`, diagnostic des pannes |
| [06](06-crud-creer.md) | CRUD 1/4 - **Créer** | 45 min | `insert_one`, `insert_many`, `_id`, erreurs d'écriture |
| [07](07-crud-lire.md) | CRUD 2/4 - **Lire** | 60 min | `find_one`, `find`, curseurs, filtres, projection, tri, pagination |
| [08](08-crud-modifier.md) | CRUD 3/4 - **Modifier** | 60 min | `update_one`, opérateurs, upsert, tableaux, `replace_one` |
| [09](09-crud-supprimer.md) | CRUD 4/4 - **Supprimer** et écrire en lot | 40 min | `delete_*`, suppression logique, `bulk_write` |
| [10](10-schema-souple.md) | **Vivre avec un schéma souple** | 60 min | documents hétérogènes, `null` vs absent, types mixtes, versionnage, validation |
| [11](11-modeliser.md) | Modéliser en documentaire | 45 min | imbriquer ou référencer, patterns, l'anti-patron du réflexe SQL |
| [12](12-index-et-performances.md) | Index et performances | 45 min | `explain`, règle ESR, index multikey, partiels, TTL |
| [13](13-projet-final.md) | Projet final | 2 h | une application CRUD complète, testée, de bout en bout |
| [14](14-annexes.md) | Annexes | - | SQL → MongoDB, erreurs fréquentes, glossaire, ressources |

Le dossier [`source/`](source/) contient la version de référence de tout ce qu'on écrit au fil des étapes. **Ne le copiez pas au début** : il sert à se débloquer et à comparer.

---

## Comment suivre une étape

Chaque fichier a toujours la même structure :

- 🎯 **Objectif** et durée ;
- des sections numérotées, avec du code **à taper** et l'explication de ce qui se passe ;
- des encadrés ⚠️ **Piège** - les erreurs que tout le monde commet, autant les commettre exprès ;
- un ou deux **exercices**, avec la solution repliée ;
- ✅ **Ce qu'il faut retenir** - cinq lignes maximum.

> Tapez le code, ne le copiez pas. Les fautes de frappe sont le meilleur professeur de MongoDB : la plupart des messages d'erreur du chapitre 5 viennent de là.

---

## Avant de commencer

Vérifiez ces quatre commandes. Si l'une échoue, réglez-la maintenant - l'étape 03 en dépend.

```bash
docker --version           # Docker Engine 27+ ou Docker Desktop
docker compose version     # v2.x
python --version           # 3.11 ou plus
pip --version              # ou : uv --version
```

Et créez le dossier de travail que l'on remplira étape après étape :

```bash
mkdir boutique && cd boutique
```

| Élément | Pourquoi |
|---|---|
| CPU avec support **AVX** | requis par MongoDB ≥ 5.0 |
| Accès à Docker Hub et PyPI | un proxy d'entreprise est le premier point de blocage |
| Compte **MongoDB Atlas** (gratuit) | pour l'étape 03, partie Atlas - la validation d'e-mail prend quelques minutes |
| **MongoDB Compass** (optionnel) | interface graphique officielle, très utile pour visualiser les documents |

---

## Ce que vous saurez faire à la fin

- Démarrer un MongoDB local avec Docker Compose, et un cluster Atlas gratuit.
- Vous y connecter depuis Python, proprement (un client, des timeouts, des secrets hors du code).
- Écrire les quatre opérations d'un CRUD, en connaissant les pièges de chacune.
- Lire et écrire des documents **qui n'ont pas tous la même forme**, sans que votre application casse.
- Choisir entre imbriquer et référencer, et justifier ce choix.
- Poser un index utile et vérifier avec `explain()` qu'il sert vraiment.

Bonne formation. → **[Étape 01 - Le NoSQL en bref](01-nosql-en-bref.md)**
