[← Chapitre 03](03-lire-la-liste.md) · [Sommaire](README.md) · [Chapitre suivant →](05-creer-une-espece.md)

# Chapitre 04 - Ouvrir une fiche

> 🎯 **Objectif** : une seule route qui affiche correctement un data scientist **et** un dev Svelte, alors qu'ils n'ont pas les mêmes champs.
> ⏱️ **Durée** : 25 minutes.
> 📁 **On complète** : `repository.py`, méthodes `par_numero()` et `decouper()`.
> 📋 **Prérequis** : [étape 07](../07-crud-lire.md) et [étape 10](../10-schema-souple.md), chapitre 03 terminé.

C'est ici que l'hétérogénéité cesse d'être une théorie.

---

## 4.1 `par_numero()`

```python
    async def par_numero(self, numero: int,
                         inclure_eteintes: bool = False) -> dict[str, Any]:
        filtre: dict[str, Any] = {"numero": int(numero)}
        if not inclure_eteintes:
            filtre["eteinte_le"] = {"$exists": False}
        document = await self.col.find_one(filtre)
        if document is None:
            raise EspeceIntrouvable(f"aucune espece numero {numero}")
        return en_json(document)
```

Trois choses à remarquer.

**`int(numero)`** n'est pas de la paranoïa.

> ⚠️ **`"1"` ne correspond jamais à `1`.** MongoDB est typé : une chaîne et un entier sont deux valeurs différentes. `find_one({"numero": "1"})` renvoie `None` - **zéro résultat, et zéro message d'erreur**. C'est la panne la plus coûteuse de MongoDB, parce qu'elle ressemble à une donnée manquante. FastAPI type déjà le paramètre de chemin, mais le dépôt ne doit compter sur personne : c'est lui la frontière.

**`find_one` renvoie `None`**, elle ne lève pas. C'est au dépôt de transformer ce `None` en `EspeceIntrouvable` - que `app.py` traduira en 404, sans que vous écriviez le nombre 404 nulle part.

**`en_json(document)`** convertit ce que JSON ne connaît pas.

> ⚠️ **`Decimal128` non plus n'est pas sérialisable, et la projection ne sauve pas.** Pour la liste, on jetait `_id` avec `{"_id": 0}`. Ici on veut la fiche entière, salaires compris - et chaque salaire est un `Decimal128`, enfoui dans `evolutions`. Il faut donc **convertir**, pas exclure. `en_json()` de `modeles.py` le fait récursivement : `ObjectId` et `Decimal128` en chaînes, `datetime` en ISO.

---

## 4.2 `decouper()` - le noyau commun et le reste

Comparez deux documents de la même collection :

```json
{ "numero": 8,  "nom": "Dev Svelte",     "famille": "frontend",
  "bundler": "vite", "reactivite": "compilation", "taille_bundle_ko": 12 }

{ "numero": 10, "nom": "Data scientist", "famille": "data",
  "librairies": ["pandas", "scikit-learn"], "gpu_requis": false,
  "niveau_maths": 4 }
```

Aucun champ spécifique en commun. Une interface qui ferait `document["bundler"]` planterait une fois sur deux.

La réponse du cours (§ 10.6) : on sépare ce sur quoi le code s'appuie de ce qu'il se contente d'afficher.

```python
CHAMPS_COMMUNS = {"_id", "numero", "nom", "famille", "langages", "stade", "xp",
                  "evolutions", "habitats", "cree_le", "maj_le", "eteinte_le",
                  "schema_version"}
```

### À faire - `repository.py`

```python
    @staticmethod
    def decouper(document: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        """Separe le noyau commun des champs specifiques a la famille."""
        commun = {k: v for k, v in document.items() if k in CHAMPS_COMMUNS}
        specifique = {k: v for k, v in document.items() if k not in CHAMPS_COMMUNS}
        return commun, specifique
```

Six lignes, et l'interface affiche n'importe quelle famille sans jamais nommer un seul champ spécifique. `app.py` s'en sert ainsi :

```python
# app.py
@app.get("/api/especes/{numero}")
async def fiche(requete: Request, numero: int) -> dict[str, Any]:
    document = await depot(requete).par_numero(numero)
    commun, specifique = DepotPokedex.decouper(document)
    return {**commun, "specifique": specifique}
```

Ajoutez demain une famille `mobile` avec un champ `plateformes` : **aucune ligne à changer**, ni ici, ni dans le front. C'est ce qu'on achète en acceptant un schéma souple.

---

## 4.3 Imbriquer ou référencer ? Le cas des évolutions

Les quatre stades sont **dans** le document, pas dans une collection à part. Passons-y les cinq questions du § 11.2.

**Combien ?** Exactement quatre. Pas « quelques-uns », pas « en général peu » : **quatre, par définition du jeu**. Une espèce n'aura jamais un cinquième stade. C'est le critère décisif - une cardinalité bornée **par nature**, pas par habitude.

**Lues avec le parent ?** Toujours. La fiche affiche la chaîne entière, on ne consulte jamais un stade isolé.

**Écrites en concurrence ?** Jamais. `evoluer()` touche `stade`, jamais `evolutions`.

**Quelle taille ?** Environ 350 octets par stade, 1,5 Ko par document. La limite des 16 Mo est à sept ordres de grandeur.

**Interrogées seules ?** Rarement, et un index multiclé sur `evolutions.salaire` suffirait :

```python
{"evolutions": {"$elemMatch": {"niveau": "gourou",
                               "salaire": {"$gte": Decimal128("70000")}}}}
```

Quatre oui, un « rarement » : on imbrique.

**Le contre-exemple, dans le même sujet.** Imaginons qu'on enregistre les *captures* de l'utilisateur - « j'ai croisé un Dev React senior le 3 mars à Lyon ». Combien ? Aucune idée, et **ça grandit avec le temps**. Écrites en concurrence ? Oui. Lues avec le parent ? Non, on veut l'historique d'un joueur, pas celui d'une espèce. Trois réponses inverses : les captures iraient dans une collection séparée, avec `numero_espece` en référence.

C'est le contraste qui enseigne le critère. La règle récitée - « imbriquer si c'est petit » - ne dit rien : ce qui compte est de savoir si la borne existe **par nature** ou par chance.

---

## 4.4 Le champ absent

Ouvrez la fiche de **Dev Svelte** (numéro 8). L'interface affiche `xp -`.

```javascript
{ "numero": 8, "nom": "Dev Svelte", "stade": 0, ... }
```

Pas de `xp` du tout. L'espèce est repérée, jamais capturée - la notion ne s'applique pas. Un `xp: 0` dirait autre chose : capturée, mais encore vierge de toute expérience.

Le front écrit :

```javascript
<tr><th>xp</th><td>{fiche.xp ?? '-'}</td></tr>
```

> ⚠️ **`document["xp"]` lève `KeyError`.** Sur un schéma souple, jamais de crochets sur un champ optionnel : `document.get("xp")`, ou `?? ` côté JavaScript. C'est le § 7.7, et c'est la façon la plus courante de casser une application MongoDB en production.

---

## 4.5 Vérifier

```bash
curl -s localhost:8000/api/especes/8 | grep -o '"specifique":.*'
```

```
"specifique":{"bundler":"vite","reactivite":"compilation","taille_bundle_ko":12}
```

```bash
curl -s localhost:8000/api/especes/10 | grep -o '"specifique":.*'
```

```
"specifique":{"librairies":["pandas","scikit-learn","polars"],"gpu_requis":false,"niveau_maths":4}
```

Une route, deux formes. Puis les erreurs :

```bash
curl -s -o /dev/null -w "%{http_code}\n" localhost:8000/api/especes/999
curl -s localhost:8000/api/especes/8 | grep -o '"xp":[^,]*' || echo "pas de champ xp"
```

```
404
pas de champ xp
```

Dans l'interface, cliquez sur une carte : le panneau de droite s'ouvre, avec la chaîne d'évolutions - les stades atteints en clair, les suivants en gris - et le bloc **Particularités de la famille**.

```bash
docker compose exec api pytest -k chapitre04
```

```
4 passed
```

---

## Exercice (15 min)

Un formateur veut savoir quels champs spécifiques existent dans le Pokédex, famille par famille, sans les avoir codés en dur nulle part.

1. Écrivez `champs_par_famille()`, qui renvoie `{"frontend": ["bundler", ...], ...}`.
2. Parcourez la collection en flux, et servez-vous de `decouper()`.
3. Question : pourquoi ce calcul ne peut-il **pas** se faire à partir de `donnees/especes.json` ?

<details>
<summary>Voir la correction</summary>

```python
    async def champs_par_famille(self) -> dict[str, list[str]]:
        """Ce que chaque famille porte reellement, decouvert et non declare."""
        resultat: dict[str, set[str]] = {}
        async for document in self.col.find({}):
            _, specifique = self.decouper(document)
            resultat.setdefault(document["famille"], set()).update(specifique)
        return {famille: sorted(champs) for famille, champs in resultat.items()}
```

```
{'backend': ['frameworks', 'gestionnaire_paquets', 'language', 'type_statique'],
 'data': ['gpu_requis', 'librairies', 'niveau_maths'],
 'frontend': ['bundler', 'reactivite', 'taille_bundle_ko'],
 'infra': ['astreinte', 'nuages', 'outils'],
 'securite': ['certifications', 'chapeau', 'habilitation']}
```

Notez `language` chez `backend` : c'est l'anomalie de Dev TurboPascal, que vous aviez repérée au chapitre 01. Elle sort d'elle-même dès qu'on interroge la **réalité** plutôt que le modèle qu'on croit avoir.

3. Parce que le fichier JSON est l'**état initial**, pas l'état courant. Depuis le chapitre 03, la base a peut-être reçu des espèces créées à la main, ou modifiées. Une collection MongoDB n'a pas de schéma déclaré : la seule source de vérité sur sa forme est son contenu. C'est exactement ce que fera l'audit du chapitre 09, en une agrégation au lieu d'une boucle Python.

</details>

---

## ✅ Ce qu'il faut retenir

1. `"1"` ne correspond jamais à `1` : zéro résultat, zéro erreur. Le dépôt convertit lui-même.
2. `find_one` renvoie `None` ; c'est le dépôt qui en fait une `EspeceIntrouvable`.
3. `ObjectId` et `Decimal128` se **convertissent** quand on ne peut pas les exclure : `en_json()`.
4. `decouper()` sépare le noyau commun du reste : une route affiche toutes les familles, sans en nommer aucune.
5. On imbrique quand la cardinalité est bornée **par nature** - quatre stades - et on référence quand elle grandit avec le temps.

→ **[Chapitre 05 - Créer une espèce](05-creer-une-espece.md)**
