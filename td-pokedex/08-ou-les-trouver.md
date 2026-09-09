[← Chapitre 07](07-eteindre-une-espece.md) · [Sommaire](README.md) · [Chapitre suivant →](09-agreger-et-verrouiller.md)

# Chapitre 08 - Où les trouver ?

> 🎯 **Objectif** : interroger MongoDB par la géographie - un rayon, puis un rectangle - et brancher la carte Leaflet dessus.
> ⏱️ **Durée** : 35 minutes.
> 📁 **On complète** : `repository.py`, méthodes `autour_de()` et `dans_la_zone()`, plus l'index `2dsphere`.
> 📋 **Prérequis** : [étape 12](../12-index-et-performances.md), chapitre 07 terminé.

C'est la seule notion du TD que le cours n'aborde pas. MongoDB sait interroger la Terre, et il le fait avec le même vocabulaire que le reste : un filtre, un index.

---

## 8.1 GeoJSON, et l'ordre des coordonnées

Chaque espèce porte des habitats :

```json
"habitats": [
  { "lieu": "Station F, Paris",
    "point": { "type": "Point", "coordinates": [2.3708, 48.8352] } },
  { "lieu": "Toulouse",
    "point": { "type": "Point", "coordinates": [1.4442, 43.6047] } }
]
```

`point` est un objet **GeoJSON** (RFC 7946) : un `type`, et un tableau `coordinates`.

> ⚠️ **GeoJSON, c'est `[longitude, latitude]`.** Dans cet ordre, et c'est l'inverse de tout ce que vous avez l'habitude de lire : Google Maps, Leaflet et les GPS annoncent la latitude d'abord.
>
> ```python
> [2.3708, 48.8352]     # ✅ Paris  : longitude 2.37 E, latitude 48.83 N
> [48.8352, 2.3708]     # ❌ quelque part au large de la Somalie
> ```
>
> **L'inversion ne lève aucune erreur.** Longitude 48 et latitude 2 sont des coordonnées parfaitement valides. Le document est accepté, indexé, interrogeable - il est simplement au mauvais endroit sur Terre. Le seul symptôme est un `$near` qui ne ramène rien, ou un marqueur en pleine mer. La carte du chapitre le rend visible immédiatement, et c'est bien pour cela qu'on en a une.

Le front fait la conversion à chaque marqueur :

```javascript
// Carte.svelte
const [lon, lat] = habitat.point.coordinates;   // GeoJSON : lon, lat
L.circleMarker([lat, lon], { ... })             // Leaflet  : lat, lon
```

---

## 8.2 L'index `2dsphere`

### À faire - `repository.py`

Ajoutez dans `initialiser()` :

```python
            # 2dsphere : indispensable a $near et $geoWithin. Multikey, car
            # habitats est un tableau.
            IndexModel([("habitats.point", GEOSPHERE)], name="geo_habitats"),
```

`GEOSPHERE` est importé depuis `pymongo` en haut du fichier, à côté de `ASCENDING`.

Deux choses en une ligne :

- **`2dsphere`**, pas `2d` : `2d` traite le plan comme une feuille de papier, `2dsphere` calcule sur une sphère. Sur des distances françaises l'écart est de quelques centaines de mètres ; entre deux continents il devient absurde.
- **`habitats.point`** indexe un champ situé dans un tableau : l'index est **multiclé**. Une espèce avec trois habitats produit trois entrées, et un seul habitat dans le rayon suffit à la faire ressortir.

> ⚠️ **`$near` sans index `2dsphere` échoue, il ne se dégrade pas.** Contrairement à une requête ordinaire, qui se rabat sur un `COLLSCAN`, une requête géographique refuse de s'exécuter :
>
> ```
> pymongo.errors.OperationFailure: error processing query: ... GEONEAR field=habitats.point
> code = 291, codeName = NoQueryExecutionPlans
> ```
>
> Retenez le **291** : c'est toujours un index géographique manquant.

---

## 8.3 `autour_de()` - le rayon

```python
    async def autour_de(self, lon: float, lat: float, km: float,
                        taille: int = 50) -> list[dict[str, Any]]:
        """Especes observees dans un rayon.

        $near trie par distance croissante, et exige un index 2dsphere.
        $maxDistance est en METRES.
        """
        curseur = self.col.find({
            "habitats.point": {
                "$near": {
                    "$geometry": {"type": "Point", "coordinates": [lon, lat]},
                    "$maxDistance": km * 1000,
                }
            },
            "eteinte_le": {"$exists": False},
        }, PROJECTION_RESUME).limit(taille)
        return en_json(await curseur.to_list(taille))
```

**`$near` trie tout seul**, par distance croissante. C'est le seul opérateur de requête qui impose un ordre : inutile d'ajouter un `.sort()`, il serait refusé.

> ⚠️ **`$maxDistance` est en mètres.** Toujours, quelle que soit l'unité qui vous arrange. Un `$maxDistance: 50` cherche dans un rayon de cinquante **mètres**, et ne ramène jamais rien. D'où le `km * 1000`, écrit une fois, dans le dépôt.

> ⚠️ **`$near` doit être au premier niveau du filtre.** Le glisser dans un `$or` donne :
>
> ```
> pymongo.errors.OperationFailure: geo $near must be top-level expr
> ```
>
> On peut le combiner avec d'autres conditions - ici `eteinte_le` - tant qu'elles sont frères et non imbriquées dans un `$or`.

---

## 8.4 `dans_la_zone()` - le rectangle visible

Le bouton **Chercher dans la zone visible** envoie les quatre bornes de la carte. La question n'est plus « à quelle distance », mais « dans ce cadre ».

```python
    async def dans_la_zone(self, ouest: float, sud: float, est: float,
                           nord: float, taille: int = 100) -> list[dict[str, Any]]:
        """Especes dont un habitat tombe dans le rectangle visible sur la carte.

        $geoWithin ne trie pas et ne limite pas la distance : c'est la requete
        "ce que je vois a l'ecran".
        """
        boite = [[[ouest, sud], [est, sud], [est, nord], [ouest, nord],
                  [ouest, sud]]]
        curseur = self.col.find({
            "habitats.point": {
                "$geoWithin": {"$geometry": {"type": "Polygon",
                                             "coordinates": boite}}
            },
            "eteinte_le": {"$exists": False},
        }, PROJECTION_RESUME).sort("numero", ASCENDING).limit(taille)
        return en_json(await curseur.to_list(taille))
```

> ⚠️ **Un anneau GeoJSON se ferme.** Le premier point doit être répété en dernier - cinq points pour un rectangle, pas quatre. Sinon :
>
> ```
> Loop is not closed
> ```
>
> Et l'imbrication est double : `coordinates` d'un `Polygon` est une **liste d'anneaux** (le premier est le contour, les suivants sont des trous). D'où les trois crochets ouvrants.

Deux différences avec `$near`, qui expliquent pourquoi les deux existent :

| | `$near` | `$geoWithin` |
|---|---|---|
| trie | par distance | pas du tout |
| exige un index | oui | non, mais bien plus rapide avec |
| répond à | « le plus proche de moi » | « tout ce qui est là-dedans » |

---

## 8.5 Vérifier

Ouvrez l'onglet **Carte**. Une carte OpenStreetMap, un marqueur par habitat, coloré par famille, et un cercle vert.

**Cliquez sur Lyon** : le cercle s'y déplace, et la grille en dessous ne montre plus que les espèces du rayon. Faites glisser le curseur **rayon** : la liste s'élargit.

```bash
curl -s "localhost:8000/api/autour?lon=4.8357&lat=45.7640&km=50" \
  | grep -o '"nom":"[^"]*"'
```

```
"nom":"Dev Java"
"nom":"Dev React"
"nom":"Dev Svelte"
```

Trois espèces, dans l'ordre des distances. Élargissez :

```bash
curl -s "localhost:8000/api/autour?lon=4.8357&lat=45.7640&km=100" \
  | grep -c '"numero"'
```

```
5
```

Puis la zone. Cadrez l'Île-de-France et cliquez **Chercher dans la zone visible** :

```bash
curl -s "localhost:8000/api/zone?ouest=1.8&sud=48.5&est=2.8&nord=49.1" \
  | grep -c '"numero"'
```

```
10
```

Dix espèces ont au moins un habitat en Île-de-France - dont **Dev Python**, qui est aussi à Toulouse et à Nantes. C'est l'index multiclé : un seul habitat dans la zone suffit.

Enfin, la preuve que les éteintes sont exclues : Dev Perl est à Paris 5e, Dev TurboPascal à Charleroi. Ni l'une ni l'autre n'apparaît.

```bash
docker compose exec api pytest -k chapitre08
```

```
4 passed
```

> ⚠️ **Si les tuiles ne s'affichent pas**, la carte reste grise mais **fonctionne** : marqueurs, cercle et requêtes sont intacts. Un proxy d'entreprise bloque simplement `tile.openstreetmap.org`. Ce n'est pas une panne du TD.

---

## Exercice (20 min)

Le front affiche les espèces proches, mais pas **à quelle distance** elles sont. `$near` connaît la distance - il s'en sert pour trier - mais ne la donne pas.

1. Trouvez l'étape d'agrégation qui, elle, la renvoie.
2. Écrivez `distances_depuis(lon, lat, km)` qui rend `[{"nom": ..., "km": ...}]`, arrondi au dixième.
3. Question : cette étape a deux contraintes que `$near` n'a pas. Lesquelles, et pourquoi ?

<details>
<summary>Voir la correction</summary>

```python
    async def distances_depuis(self, lon: float, lat: float,
                               km: float = 200) -> list[dict[str, Any]]:
        """$geoNear : le seul moyen d'obtenir la distance, et non juste l'ordre."""
        curseur = await self.col.aggregate([
            {"$geoNear": {
                "near": {"type": "Point", "coordinates": [lon, lat]},
                "distanceField": "distance_m",        # en metres, comme toujours
                "maxDistance": km * 1000,
                "query": {"eteinte_le": {"$exists": False}},
                "spherical": True,
            }},
            {"$project": {"_id": 0, "nom": 1,
                          "km": {"$round": [{"$divide": ["$distance_m", 1000]}, 1]}}},
        ])
        return [ligne async for ligne in curseur]
```

```bash
docker compose exec api python -c "
import asyncio
from db import fermer, get_db
from repository import DepotPokedex

async def m():
    for l in await DepotPokedex(get_db()).distances_depuis(4.8357, 45.7640):
        print(f\"{l['nom']:<18}{l['km']:>7} km\")
    await fermer()

asyncio.run(m())
"
```

```
Dev Java              1.9 km
Dev React             3.0 km
Dev Svelte            3.5 km
Dev Angular          94.4 km
Data scientist       94.4 km
```

Deux détails :

- **Le filtre va dans `query`**, pas dans un `$match` séparé. Un `$match` placé après ferait calculer les distances de toute la collection avant d'en jeter la moitié.
- **`spherical: True`** est obligatoire avec un index `2dsphere`, et c'est lui qui fait que `distanceField` sort en mètres.

3. `$geoNear` doit être la **toute première étape** du pipeline, et il ne peut y en avoir qu'**un seul**.

La raison est la même dans les deux cas : ce n'est pas un filtre appliqué à un flux de documents, c'est un **accès à l'index** qui produit le flux. Il joue le rôle du `find` - il ne peut donc rien avoir avant lui, et deux points de départ n'auraient pas de sens.

C'est aussi pourquoi `$near` ne peut pas vivre dans un `$or` : la même contrainte, exprimée du côté des requêtes.

</details>

---

## ✅ Ce qu'il faut retenir

1. GeoJSON, c'est **`[longitude, latitude]`** - l'inverse de Leaflet. L'erreur ne lève rien : elle déplace le point.
2. `$near` et `$geoWithin` exigent un index **`2dsphere`**. Sans lui, `$near` échoue avec le code **291**.
3. Les distances sont **toujours en mètres**.
4. `$near` trie par distance et doit être au premier niveau du filtre ; `$geoWithin` ne trie pas et accepte d'être imbriqué.
5. L'index sur `habitats.point` est **multiclé** : un seul habitat dans la zone suffit à faire ressortir l'espèce.

→ **[Chapitre 09 - Agréger, auditer, verrouiller](09-agreger-et-verrouiller.md)**
