[← Étape 03](03-lancer-mongodb.md) · [Sommaire](README.md) · [Étape suivante →](05-se-connecter-en-python.md)

# Étape 04 - Premiers pas dans mongosh

> 🎯 **Objectif** : faire un CRUD complet **à la main**, dans le shell, avant d'écrire la moindre ligne de Python. Et constater de ses propres yeux que deux documents d'une même collection peuvent être différents.
> ⏱️ **Durée** : 40 minutes.
> 📋 **Prérequis** : la pile Compose de l'étape 03 tourne (`docker compose ps` → `healthy`).

Pourquoi passer par le shell ? Parce que les messages d'erreur y sont immédiats, sans couche Python entre vous et le serveur. Tout ce que vous tapez ici a un équivalent direct en PyMongo, que vous retrouverez à partir de l'étape 06.

---

## 4.1 Entrer dans le shell

```bash
docker compose exec mongo mongosh -u admin -p change-moi --authenticationDatabase admin
```

Vous obtenez une invite `test>`. Le shell est un **interpréteur JavaScript** : tout ce qui est valide en JS l'est ici.

```javascript
show dbs                 // les bases existantes
use boutique             // on se place sur "boutique" - elle n'existe pas encore, c'est normal
db                       // affiche la base courante
```

> ⚠️ **`use boutique` ne crée rien.** Ni la base, ni la collection. Elles n'existeront qu'à la **première écriture**. C'est le premier réflexe MongoDB à acquérir : les choses se créent en écrivant dedans.

---

## 4.2 Créer - `insertOne` et `insertMany`

### À faire

```javascript
db.produits.insertOne({
  sku: "KBD-0001",
  nom: "Clavier mécanique 60%",
  categorie: "clavier",
  prix: 89.90,
  stock: 12,
  tags: ["clavier", "mecanique"],
  cree_le: new Date()
})
```

Le shell répond :

```javascript
{ acknowledged: true, insertedId: ObjectId('66f0a1b2c3d4e5f600000001') }
```

La base `boutique`, la collection `produits` et le document existent désormais. Vérifiez :

```javascript
show dbs
show collections
db.produits.countDocuments({})
```

### Plusieurs documents d'un coup - et de formes différentes

```javascript
db.produits.insertMany([
  {
    sku: "SCR-0002", nom: "Ecran 27 pouces", categorie: "ecran",
    prix: 249.00, stock: 5,
    pouces: 27, resolution: "2560x1440", hz: 144,       // champs propres aux écrans
    cree_le: new Date()
  },
  {
    sku: "MSE-0003", nom: "Souris ergonomique", categorie: "souris",
    prix: 59.00, stock: 40,
    poids_g: 96, sans_fil: true,                        // champs propres aux souris
    cree_le: new Date()
  },
  {
    sku: "ABO-0004", nom: "Support Pro 1 an", categorie: "abonnement",
    prix: 190.00,                                       // ni stock, ni tags : c'est un service
    periodicite: "annuelle", renouvellement_auto: true,
    cree_le: new Date()
  }
])
```

### Ce qui vient de se passer

Regardez bien : **les quatre documents n'ont pas les mêmes champs.** L'écran a `pouces`, `resolution`, `hz` ; la souris a `poids_g` ; l'abonnement n'a même pas de `stock`. MongoDB les accepte sans broncher, dans la même collection.

C'est **la** spécificité du documentaire. Elle est utile - un catalogue hétérogène tient dans une seule collection, sans table d'attributs ni colonnes à `NULL` - et elle est piégeuse : votre code de lecture ne peut plus supposer qu'un champ existe. L'[étape 10](10-schema-souple.md) est entièrement consacrée à cette question.

---

## 4.3 Lire - `find`

```javascript
db.produits.find()                                  // tout
db.produits.findOne({ sku: "KBD-0001" })            // un seul document, ou null
db.produits.find({ categorie: "clavier" })          // égalité
db.produits.find({ prix: { $lt: 100 } })            // opérateur : strictement inférieur
db.produits.find({ prix: { $gte: 50, $lte: 250 } }) // encadrement
db.produits.find({ categorie: { $in: ["clavier", "souris"] } })
db.produits.find({ tags: "mecanique" })             // dans un tableau = "contient"
```

Projection (quels champs renvoyer), tri, limite :

```javascript
db.produits.find(
  { prix: { $lt: 300 } },
  { nom: 1, prix: 1, _id: 0 }          // 1 = garder, 0 = exclure
).sort({ prix: -1 }).limit(3)
```

### Vérifier l'hétérogénéité, maintenant qu'elle est là

```javascript
db.produits.find({ hz: { $exists: true } })       // seulement les documents qui ONT le champ hz
db.produits.find({ stock: { $exists: false } })   // ceux qui n'ont PAS de stock → l'abonnement
db.produits.countDocuments({ hz: { $exists: true } })
```

Et le piège fondateur, à faire une bonne fois :

```javascript
db.produits.insertOne({ sku: "TST-9999", nom: "Test", remise: null })

db.produits.find({ remise: null })                    // 👀 combien de résultats ?
db.produits.find({ remise: { $exists: false } })      // et ici ?
```

> ⚠️ **`{remise: null}` retourne à la fois les documents où `remise` vaut `null` et ceux où le champ est absent.** C'est voulu, et c'est la source d'innombrables bugs. Pour distinguer :
> - champ absent : `{ remise: { $exists: false } }`
> - champ présent et valant null : `{ remise: { $type: "null" } }`

Nettoyez le document de test :

```javascript
db.produits.deleteOne({ sku: "TST-9999" })
```

---

## 4.4 Modifier - `updateOne`, `updateMany`

```javascript
db.produits.updateOne(
  { sku: "KBD-0001" },                                  // qui
  { $set: { prix: 79.90 }, $inc: { stock: -1 } }        // quoi
)
```

Réponse : `{ matchedCount: 1, modifiedCount: 1 }`.

```javascript
db.produits.updateMany(
  { categorie: "clavier" },
  { $addToSet: { tags: "promo" } }        // ajoute au tableau, sans doublon
)

db.produits.updateOne(
  { sku: "ABO-0004" },
  { $set: { support_telephonique: true } }   // 👈 on ajoute un champ à UN SEUL document
)
```

Cette dernière commande mérite un arrêt : **vous venez d'ajouter un champ à un seul document de la collection.** Il n'y a pas eu d'`ALTER TABLE`, les autres documents n'ont pas de colonne `support_telephonique` à `NULL` - ils n'ont tout simplement pas ce champ. C'est le mécanisme de base de toute évolution de schéma en MongoDB.

> ⚠️ **L'oubli du `$`.** `db.produits.updateOne({sku: "KBD-0001"}, {prix: 10})` provoque une erreur : *"Update document requires atomic operators"*. Une mise à jour est **partielle** et passe par des opérateurs. Pour remplacer entièrement un document, c'est `replaceOne` - vu à l'étape 08.

Les opérateurs à connaître :

| Opérateur | Effet |
|---|---|
| `$set` / `$unset` | définir / supprimer un champ |
| `$inc` / `$mul` | incrémenter / multiplier |
| `$rename` | renommer un champ |
| `$currentDate` | horodater |
| `$push` / `$pull` / `$addToSet` / `$pop` | manipuler un tableau |

---

## 4.5 Supprimer - `deleteOne`, `deleteMany`

```javascript
db.produits.deleteOne({ sku: "MSE-0003" })
db.produits.countDocuments({})
```

```javascript
// db.produits.deleteMany({})   // vide la collection (à ne pas exécuter maintenant)
// db.produits.drop()           // supprime la collection ET ses index
```

Réinsérez la souris, on en aura besoin :

```javascript
db.produits.insertOne({
  sku: "MSE-0003", nom: "Souris ergonomique", categorie: "souris",
  prix: 59.00, stock: 40, poids_g: 96, sans_fil: true, cree_le: new Date()
})
```

---

## 4.6 Un premier index

```javascript
db.produits.createIndex({ sku: 1 }, { unique: true, name: "uniq_sku" })
db.produits.getIndexes()
```

Testez la contrainte :

```javascript
db.produits.insertOne({ sku: "KBD-0001", nom: "Doublon" })
// → MongoServerError: E11000 duplicate key error collection: boutique.produits index: uniq_sku
```

Retenez le code **`E11000`** : c'est *la* violation d'index unique, et vous la reverrez en Python sous la forme d'une exception `DuplicateKeyError`.

Un `_id` est indexé automatiquement ; tous les autres index sont à votre charge. On y consacre l'[étape 12](12-index-et-performances.md).

---

## 4.7 Mémo mongosh

```javascript
show dbs                          // bases
use maBase                        // changer de base
show collections                  // collections
db.maColl.countDocuments({})      // compter
db.maColl.findOne()               // un document au hasard, pour voir la forme
db.maColl.getIndexes()            // index
db.maColl.stats()                 // taille, nombre de documents
db.maColl.find().pretty()         // affichage lisible
db.maColl.find().explain("executionStats")   // plan d'exécution (étape 12)
db.dropDatabase()                 // ⚠️ supprime la base courante
exit
```

Astuce : le shell garde un historique (flèche haut) et complète avec `Tab`.

---

## Exercice (15 min)

Dans la collection `produits` :

1. Ajoutez un livre : `sku: "LIV-0005"`, nom, `categorie: "livre"`, prix 39, avec les champs `auteur`, `isbn` et `pages` - et **sans** champ `tags`.
2. Affichez tous les produits à moins de 100 €, triés du moins cher au plus cher, en ne montrant que `nom` et `prix`.
3. Comptez les produits qui **n'ont pas** de champ `tags`.
4. Passez tous les produits de la catégorie `ecran` en stock 0.
5. Ajoutez le tag `"nouveau"` à tous les produits créés aujourd'hui.

<details>
<summary>Voir la correction</summary>

```javascript
// 1
db.produits.insertOne({
  sku: "LIV-0005", nom: "Le guide MongoDB", categorie: "livre",
  prix: 39.00, stock: 7,
  auteur: "K. Chodorow", isbn: "978-1491954461", pages: 514,
  cree_le: new Date()
})

// 2
db.produits.find({ prix: { $lt: 100 } }, { nom: 1, prix: 1, _id: 0 }).sort({ prix: 1 })

// 3
db.produits.countDocuments({ tags: { $exists: false } })

// 4
db.produits.updateMany({ categorie: "ecran" }, { $set: { stock: 0 } })

// 5
const debutJour = new Date(); debutJour.setHours(0, 0, 0, 0);
db.produits.updateMany(
  { cree_le: { $gte: debutJour } },
  { $addToSet: { tags: "nouveau" } }
)
```

**Question 5, le point important** : le livre et l'abonnement n'avaient **pas** de champ `tags`. `$addToSet` ne s'en offusque pas - il **crée le tableau** avec l'élément dedans. Beaucoup d'opérateurs MongoDB fonctionnent ainsi sur un champ absent (`$set`, `$inc`, `$push`, `$addToSet`), ce qui rend les évolutions de schéma très simples… et rend d'autant plus nécessaire de savoir ce que contiennent réellement vos documents.

</details>

---

## ✅ Ce qu'il faut retenir

1. Base et collection se créent **à la première écriture** ; `use` ne crée rien.
2. Une requête est un **objet**, pas une chaîne : `{ prix: { $lt: 100 } }`.
3. Les documents d'une même collection **peuvent avoir des champs différents** - vous venez de le faire.
4. `{champ: null}` matche aussi les documents où le champ est **absent** ; utilisez `$exists` pour distinguer.
5. Une mise à jour utilise des opérateurs (`$set`, `$inc`, `$push`…) et ne touche que les champs visés.
6. `E11000` = violation d'index unique.

→ **[Étape 05 - Se connecter en Python](05-se-connecter-en-python.md)**
