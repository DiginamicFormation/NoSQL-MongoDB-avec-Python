[← Sommaire du TD](README.md) · [Sommaire du cours](../README.md) · [Chapitre suivant →](02-connexion-asynchrone.md)

# Chapitre 01 - Mise en route : trois conteneurs et un mensonge

> 🎯 **Objectif** : démarrer le Pokédex, charger les 15 espèces, et constater que l'écran ne lit pas encore la base.
> ⏱️ **Durée** : 20 minutes.
> 📁 **On complète** : rien - ce chapitre se lit.
> 📋 **Prérequis** : étapes 01 à 12 du cours, Docker Compose v2, les ports 8080 et 8000 libres.

Le projet vous est livré **qui marche**. C'est justement le problème, et c'est tout le sujet du TD.

---

## 1.1 Démarrer

```bash
cd td-pokedex/bootstrap
cp .env.example .env
docker compose up -d
docker compose ps
```

Attendez que `pokedex-mongo` affiche `(healthy)`. Puis ouvrez `http://localhost:8080`.

Vous voyez treize cartes, des filtres, un onglet Carte, un onglet Statistiques. Tout répond.

> ⚠️ **Le `.env` oublié ne fait rien planter.** L'API démarre quand même et sert ses réponses en dur : vous ne vous en apercevrez qu'au chapitre 02. Vérifiez maintenant :
> ```bash
> docker compose exec api env | grep MONGODB
> ```

---

## 1.2 Charger les espèces

```bash
docker compose exec api python importer_especes.py
```

```
15 especes importees, 0 mises a jour - 15 au total
```

Relancez la même commande :

```
0 especes importees, 0 mises a jour - 15 au total
```

Zéro doublon. C'est l'import **réexécutable** de l'[étape 09](../09-crud-supprimer.md) : un `bulk_write` de `UpdateOne(..., upsert=True)` sur le numéro. Ouvrez `api/importer_especes.py`, il tient en trente lignes - et il fait, en plus simple, ce que vous écrirez au chapitre suivant.

---

## 1.3 Le mensonge

La base contient quinze espèces. Comptez celles que l'écran affiche : **treize**.

Vérifiez que la base dit bien quinze :

```bash
docker compose exec mongo mongosh -u app -p app-password \
  --authenticationDatabase pokedex pokedex \
  --quiet --eval 'db.especes.countDocuments({})'
```

```
15
```

Puis insérez une espèce à la main :

```javascript
db.especes.insertOne({
  numero: 500, nom: "Dev Rust", famille: "backend",
  langages: ["rust"], stade: 0, evolutions: [], habitats: [],
  schema_version: 1
});
```

Rechargez la page. **Rien ne bouge.**

L'interface ne lit pas MongoDB. Elle lit `api/fixtures.py`, un fichier de constantes Python.

```python
# fixtures.py
SANTE = {'mongo': 'ok', 'version': '8.0.30', 'especes': 15}

LISTE = [{'numero': 1,
  'evolutions': [{'titre': 'Pythonet'}, ...],
  ...
```

Et dans le dépôt :

```python
# repository.py
    async def lister(self, famille=None, q=None, eteintes=False,
                     apres=None, taille=20) -> list[dict[str, Any]]:
        """Liste paginee par curseur (pas de skip).

        TODO chapitre 03 : construisez le filtre, puis find + sort + limit.
        """
        return fixtures.LISTE[:taille]             # <- a supprimer au chapitre 03
```

Supprimez le `Dev Rust` que vous venez d'insérer, il n'est pas conforme :

```javascript
db.especes.deleteOne({ numero: 500 });
```

---

## 1.4 Pourquoi une fixture, et pas un `NotImplementedError`

Un `raise NotImplementedError` aurait mis 500 partout. Vous auriez codé sans jamais savoir à quoi ressemble le résultat correct.

Avec la fixture, vous avez en permanence **le comportement cible sous les yeux**. Quand vous remplacerez `return fixtures.LISTE` par une vraie requête, l'écran ne devra **pas bouger** - sauf sur les deux espèces éteintes, et ce sera précisément le signe que vous avez juste.

Les fixtures ont été extraites des vraies réponses du programme fini. Elles ne sont pas inventées.

---

## 1.5 Les 18 marqueurs

```bash
docker compose exec api sh -c "grep -c 'chapitre 0.$' repository.py"
```

```
18
```

C'est votre barre de progression. Vous la relancerez à la fin de chaque chapitre.

| Méthode | Chapitre |
|---|---|
| `sante` | 02 |
| `lister`, `compter` | 03 |
| `par_numero`, `decouper` | 04 |
| `initialiser`, `creer` | 05 |
| `modifier`, `evoluer` | 06 |
| `eteindre`, `eteindre_definitivement`, `restaurer` | 07 |
| `autour_de`, `dans_la_zone` | 08 |
| `statistiques`, `auditer`, `decrire_schema`, `plan_de_requete` | 09 |

---

## 1.6 Le tour du propriétaire

```
bootstrap/
├── compose.yaml              trois services : mongo, api, web
├── init/01-init.js           l'utilisateur applicatif, joue au 1er demarrage
├── api/
│   ├── app.py                les routes FastAPI                    ⇦ ne pas toucher
│   ├── db.py                 le client unique                      ⇦ a lire au ch. 02
│   ├── modeles.py            Pydantic + la serialisation BSON      ⇦ ne pas toucher
│   ├── repository.py         TOUTES les requetes MongoDB           ⇦ VOTRE TRAVAIL
│   ├── provision.py          la validation JSON Schema             ⇦ au chapitre 09
│   ├── fixtures.py           les reponses en dur                   ⇦ retrecit
│   └── test_pokedex.py       27 tests                              ⇦ ne pas toucher
└── web/                      l'interface Svelte, deja construite   ⇦ ne pas toucher
```

**Une seule règle d'architecture**, celle de l'[étape 13](../13-projet-final.md) : `app.py` n'importe jamais `pymongo`. Toutes les requêtes vivent dans `repository.py`, et elles seules. C'est pourquoi les trous sont dans le dépôt et pas dans les routes.

Ouvrez `app.py` **une fois**, pour lire ceci :

```python
# app.py
CODES_HTTP = {EspeceIntrouvable: 404, EspeceDejaExistante: 409,
              EvolutionImpossible: 409, DocumentInvalide: 422}


@app.exception_handler(ErreurPokedex)
async def traduire_erreur(requete: Request, exc: ErreurPokedex) -> JSONResponse:
    code = next((CODES_HTTP[classe] for classe in type(exc).__mro__
                 if classe in CODES_HTTP), 400)
    return JSONResponse(status_code=code, content={"erreur": str(exc)})
```

Vous levez une exception métier, l'API en fait un code HTTP, et le front l'affiche dans un bandeau rouge. Vous n'écrirez jamais de `status_code` vous-même.

> ⚠️ **Le nom du projet Docker est écrit en dur.** Compose le déduit d'habitude du nom du dossier parent - ici `NoSQL - Python`, avec des espaces et des majuscules, que Compose refuse. D'où le `name: pokedex` en tête de `compose.yaml`.

---

## 1.7 Le vocabulaire, une bonne fois

Trois mots se ressemblent, ne les confondez pas :

| | |
|---|---|
| `evolutions` | le **tableau** des quatre stades. Une donnée, fixe, imbriquée dans le document |
| `stade` | un **entier de 0 à 3** : où en est cette espèce dans sa chaîne |
| `evoluer()` | l'**action** qui incrémente `stade` |

Faire évoluer une espèce ne modifie jamais `evolutions`. Cela incrémente `stade`.

---

## 1.8 Les tests

```bash
docker compose exec api pytest -q
```

```
24 failed, 3 passed
```

C'est normal, et c'est même rassurant : les tests décrivent le programme **fini**. Ils sont votre juge de paix, et ils ne se contentent pas du code HTTP :

```python
async def test_chapitre05_creer_puis_lire(depot):
    await depot.creer(1, "Dev Python", "backend", evolutions(), xp=4200)
    espece = await depot.par_numero(1)
    assert espece["stade"] == 0
```

Une méthode encore branchée sur une fixture renvoie la bonne forme, mais n'écrit rien dans la base - et c'est l'assertion suivante qui la démasque.

---

## Exercice (5 min)

1. Trouvez, dans `donnees/especes.json`, la **seule** espèce qui n'a pas de champ `xp`. Qu'affiche l'interface à sa place ?
2. Trouvez les **deux** espèces qui portent un champ `eteinte_le`.
3. Une des quinze espèces a un champ mal nommé, et un `schema_version` différent des autres. Laquelle, et quels sont ces deux écarts ?

<details>
<summary>Voir la correction</summary>

```bash
docker compose exec api python -c "
import json
especes = json.load(open('donnees/especes.json', encoding='utf-8'))
print('sans xp  :', [e['nom'] for e in especes if 'xp' not in e])
print('eteintes :', [e['nom'] for e in especes if 'eteinte_le' in e])
print('anomalie :', [e['nom'] for e in especes if 'langages' not in e])
"
```

```
sans xp  : ['Dev Svelte']
eteintes : ['Dev Perl', 'Dev TurboPascal']
anomalie : ['Dev TurboPascal']
```

1. **Dev Svelte** n'a pas de champ `xp`. L'interface affiche `xp -`, et non `xp 0` : l'espèce est repérée, jamais capturée. La convention de l'[étape 10](../10-schema-souple.md) - champ absent n'est pas champ à zéro - est tenue de bout en bout, jusque dans les statistiques du chapitre 09.

2. **Dev Perl** (900) et **Dev TurboPascal** (901). Elles sont dans la base, mais l'interface ne les montre pas : c'est l'extinction logique du chapitre 07. Les numéros 900+ les rendent repérables d'un coup d'oeil.

3. **Dev TurboPascal** porte `language: "pascal"` - au singulier, et en chaîne - là où les quatorze autres ont `langages: [...]` en tableau. Et son `schema_version` vaut `0`, pas `1`.

C'est une dette technique **posée là exprès**. L'audit du chapitre 09 la trouvera tout seul, et c'est elle qui vous obligera à passer par `moderate/warn` avant `strict/error`.

</details>

---

## ✅ Ce qu'il faut retenir

1. Le projet marche dès le départ parce que le dépôt renvoie des **constantes**, pas des documents. L'écran ment.
2. **18 marqueurs** dans `repository.py`. Les compter est votre barre de progression.
3. **Toutes** les requêtes MongoDB vivent dans `repository.py` : `app.py` et le front ne bougeront plus jamais.
4. Vous levez des **exceptions métier** ; la traduction en 404, 409 ou 422 est déjà écrite.
5. `evolutions` est une donnée, `stade` un curseur, `evoluer()` une action. Ne les mélangez pas.

→ **[Chapitre 02 - Se connecter en asynchrone](02-connexion-asynchrone.md)**
