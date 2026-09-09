# Le projet bootstrap

Le squelette du TD. Il **fonctionne dès le premier démarrage**, parce que `api/repository.py` renvoie des réponses en dur rangées dans `api/fixtures.py`.

Les explications sont dans les chapitres, à côté : [sommaire du TD](../README.md).

---

## Démarrer

```bash
cp .env.example .env
docker compose up -d
docker compose ps                                    # attendre "healthy"
docker compose exec api python importer_especes.py
```

| | |
|---|---|
| Interface | `http://localhost:8080` |
| API | `http://localhost:8000/docs` |
| MongoDB | `mongodb://app:app-password@localhost:27018/pokedex?authSource=pokedex` |

Le port 27018 est délibéré : il ne heurte pas le MongoDB du cours, qui écoute sur 27017.

---

## Travailler

Vous n'éditez que **`api/repository.py`** et, au dernier chapitre, `api/provision.py`.

```bash
docker compose exec api sh -c "grep -c 'chapitre 0.$' repository.py"   # 18 -> 0
docker compose exec api pytest -k chapitre03                            # le chapitre en cours
docker compose exec api pytest -v                                       # tout
docker compose logs -f api                                              # les 500 sont ici
```

`uvicorn` tourne avec `--reload` : vos modifications sont prises en compte sans redémarrer le conteneur.

> Sous Windows, si `--reload` ne repère pas vos modifications, décommentez `WATCHFILES_FORCE_POLLING` dans `compose.yaml`.

---

## Repartir de zéro

```bash
docker compose exec api python importer_especes.py --reset   # recharge les données
docker compose down -v && docker compose up -d               # ⚠️ efface tout
```

---

## L'interface

Elle est **déjà construite** : `web/dist/` est versionné, servi par nginx, qui proxifie `/api` vers le conteneur `api` - même origine, donc aucune question de CORS.

Vous n'avez donc ni Node ni `npm install` à faire. Les sources restent dans `web/src/` pour les curieux :

```bash
cd web && npm install && npm run build && cd ..
docker compose up -d --build web
```

La carte utilise **Leaflet** et les tuiles **OpenStreetMap**. Si un proxy les bloque, la carte reste fonctionnelle - marqueurs et cercle sur fond gris.
