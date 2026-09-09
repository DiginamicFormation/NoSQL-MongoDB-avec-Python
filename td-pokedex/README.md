# TD - Le Pokédex des développeurs

Un TD pas à pas : on remplit un backend **FastAPI + MongoDB** méthode par méthode, et on regarde l'interface changer à chaque chapitre.

> Le cours parle d'**étapes** (01 à 14), ce TD parle de **chapitres** (01 à 09). Les renvois `[étape 07](../07-crud-lire.md)` pointent vers le cours.

---

## Le principe

Le projet **fonctionne dès la première minute**, parce que `repository.py` renvoie des réponses en dur, rangées dans `fixtures.py`. L'écran est donc joli, et il ment.

Il reste **18 marqueurs** dans `repository.py`. Chaque chapitre en supprime deux ou trois, en les remplaçant par une vraie requête MongoDB. Le TD est fini quand il n'en reste aucun et que `fixtures.py` peut être effacé.

```bash
docker compose exec api sh -c "grep -c 'chapitre 0.$' repository.py"    # 18 -> 0
```

---

## Prérequis

Les étapes **01 à 12** du cours. Vous devez savoir ce qu'est un document, un filtre, un index, et pourquoi un champ peut être absent.

```bash
docker --version           # Docker Engine 27+
docker compose version     # v2.x
```

Rien d'autre : ni Python, ni Node sur votre machine. Tout tourne dans les conteneurs.

---

## Démarrer

```bash
cd td-pokedex/bootstrap
cp .env.example .env
docker compose up -d
docker compose ps                                    # attendre "healthy"
docker compose exec api python importer_especes.py   # charge les 15 espèces
```

| | |
|---|---|
| L'interface | http://localhost:8080 |
| L'API | http://localhost:8000/docs |
| MongoDB | `mongodb://app:app-password@localhost:27018/pokedex?authSource=pokedex` |

---

## Le parcours

| # | Chapitre | Durée | Ce qu'on écrit | Ce qui change à l'écran |
|---|---|---|---|---|
| [01](01-mise-en-route.md) | Mise en route | 20 min | rien - on lit | on découvre que l'écran ment |
| [02](02-connexion-asynchrone.md) | Se connecter en asynchrone | 25 min | `sante()` | le bandeau affiche la vraie version |
| [03](03-lire-la-liste.md) | Lire la liste | 30 min | `lister()`, `compter()` | 15 cartes deviennent 13, les filtres s'animent |
| [04](04-ouvrir-une-fiche.md) | Ouvrir une fiche | 25 min | `par_numero()`, `decouper()` | chaque espèce montre ses propres champs |
| [05](05-creer-une-espece.md) | Créer une espèce | 30 min | `creer()`, `initialiser()` | le formulaire crée pour de vrai |
| [06](06-modifier-et-evoluer.md) | Modifier, et faire évoluer | 30 min | `modifier()`, `evoluer()` | le bouton **Faire évoluer** fonctionne |
| [07](07-eteindre-une-espece.md) | Éteindre une espèce | 25 min | `eteindre()`, `restaurer()` | Perl et TurboPascal partent à la corbeille |
| [08](08-ou-les-trouver.md) | **Où les trouver ?** | 35 min | `autour_de()`, `dans_la_zone()` | la carte répond au cercle |
| [09](09-agreger-et-verrouiller.md) | Agréger, auditer, verrouiller | 35 min | 4 méthodes + `provision.py` | les trois derniers onglets s'allument |

**4 h 30** en tout. On les suit **dans l'ordre** : chaque chapitre s'appuie sur le précédent.

---

## Le sujet

Un Pokédex, mais pour développeurs. Chaque **espèce** a un numéro, une **famille**, une chaîne de **quatre évolutions** (junior, mature, senior, gourou), et des **habitats** géolocalisés.

| Famille | Espèces |
|---|---|
| `backend` | Dev Python, Java, PHP, Node, Ruby |
| `frontend` | Dev Angular, React, Svelte, Vue |
| `data` | Data scientist, Spécialiste IA |
| `securite` | Spécialiste cybersécurité |
| `infra` | DevOps |
| éteintes | Dev Perl (900), Dev TurboPascal (901) |

Chaque famille a **ses propres champs** : un `frontend` a un `bundler`, un `data` a un `gpu_requis`, un `securite` a un `chapeau`. C'est l'hétérogénéité de l'[étape 10](../10-schema-souple.md), sur un terrain neuf.

---

## Qui touche à quoi

```
bootstrap/
├── compose.yaml            fourni      trois conteneurs
├── init/01-init.js         fourni      l'utilisateur applicatif
├── api/
│   ├── app.py              fourni      les routes, la traduction des erreurs
│   ├── db.py               fourni      le client unique (à LIRE au ch. 02)
│   ├── modeles.py          fourni      Pydantic et la sérialisation BSON
│   ├── importer_especes.py fourni      le chargement des données
│   ├── donnees/            fourni      les 15 espèces
│   ├── fixtures.py         fourni      les réponses en dur - se supprime au ch. 09
│   ├── test_pokedex.py     fourni      votre juge de paix
│   ├── repository.py       ⇦ À ÉCRIRE  le TD, 18 marqueurs
│   └── provision.py        ⇦ À ÉCRIRE  la validation, au chapitre 09
└── web/                    fourni      l'interface Svelte, déjà construite
```

**Vous n'éditez que `repository.py` et `provision.py`.**

---

## Vérifier

Chaque chapitre a trois preuves : ce qui change dans l'interface, ce que répond `curl`, et son test.

```bash
docker compose exec api pytest -k chapitre03      # le chapitre en cours
docker compose exec api pytest -v                 # tout
```

Au départ, **24 tests sur 27 échouent**. C'est normal : ils décrivent le programme fini.

---

## Repartir de zéro

```bash
docker compose exec api python importer_especes.py --reset   # recharge les données
docker compose down -v && docker compose up -d               # ⚠️ efface tout
```

Bon courage. → **[Chapitre 01 - Mise en route](01-mise-en-route.md)**
