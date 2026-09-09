# `source/` - la solution de référence

Le projet complet tel qu'il existe **à la fin de l'étape 13**. Il sert à se débloquer et à comparer - pas à être copié au début du cours : on n'apprend pas MongoDB en lisant du code qui marche déjà.

## Contenu

| Fichier | Étape | Rôle |
|---|---|---|
| `compose.yaml` | [03](../03-lancer-mongodb.md) | MongoDB 8.0 en local, port publié sur `127.0.0.1` seulement |
| `init/01-init.js` | [03](../03-lancer-mongodb.md) | crée l'utilisateur applicatif `app` (joué au **premier** démarrage) |
| `.env.example` | [05](../05-se-connecter-en-python.md) | à copier en `.env` - variantes Docker et Atlas |
| `db.py` | [05](../05-se-connecter-en-python.md) | un `MongoClient` unique, avec timeouts et `tz_aware` |
| `provision.py` | [10](../10-schema-souple.md) · [12](../12-index-et-performances.md) | validation JSON Schema + index (dont un TTL partiel) |
| `repository.py` | [13](../13-projet-final.md) | **toutes** les requêtes, et les exceptions métier |
| `app.py` | [13](../13-projet-final.md) | l'interface en ligne de commande |
| `test_repository.py` | [13](../13-projet-final.md) | les tests, sur une base jetable |

## Démarrer

```bash
cp .env.example .env
docker compose up -d
docker compose ps                 # attendre "healthy"

python -m venv .venv && source .venv/bin/activate    # Windows : .venv\Scripts\activate
pip install -r requirements.txt

python db.py                      # vérifie la connexion
python app.py init                # validation + index (--strict pour refuser
                                  # les documents non conformes)
python app.py seed                # catalogue de démonstration
```

## Utiliser

```bash
python app.py list
python app.py list --categorie clavier --max-prix 100
python app.py list --taille 3 --apres <_id>   # pagination par curseur
python app.py show ABO-0013       # un produit SANS champ stock
python app.py add MSE-0030 "Souris compacte" souris 39.00 --stock 25
python app.py set KBD-0010 nom "Clavier TKL v2"
python app.py reserve KBD-0010 2
python app.py delete LIV-0014     # suppression logique
python app.py audit               # les champs réellement présents, et leurs types
python app.py stats               # agrégation par catégorie
```

```bash
pytest -v                         # les tests (base boutique_test, supprimée après)
```

## Les points à regarder dans le code

1. **`db.py`** - un seul client, `@lru_cache`, timeouts explicites, `ping` au démarrage.
2. **`repository.py`** - aucune requête MongoDB ailleurs dans le projet. Les erreurs du driver (`DuplicateKeyError`, `WriteError`) deviennent des exceptions métier.
3. **La suppression logique est dans le dépôt** : le filtre `{"supprime_le": {"$exists": False}}` est appliqué une seule fois, impossible de l'oublier dans une vue.
4. **`reserver()`** met la condition métier **dans le filtre** de `find_one_and_update` : c'est ce qui rend l'opération atomique sans transaction.
5. **`stock` absent ≠ `stock: 0`** - la convention est tenue partout, jusque dans `statistiques()` qui compte les deux séparément (`$ifNull` et `$type`).
6. **`provision.py`** verrouille le **noyau commun** avec `additionalProperties: true` : les champs spécifiques à chaque famille restent libres.
7. **L'index TTL est partiel** : il ne concerne que les documents ayant réellement une date dans `supprime_le`.

## Remise à zéro

```bash
docker compose down -v && docker compose up -d     # ⚠️ efface toutes les données
python app.py init && python app.py seed
```
