[← Étape 10](10-schema-souple.md) · [Sommaire](README.md) · [Étape suivante →](12-index-et-performances.md)

# Étape 11 - Modéliser en documentaire

> 🎯 **Objectif** : savoir décider, pour chaque relation, entre **imbriquer** et **référencer**, et connaître les patterns qui résolvent les cas difficiles.
> ⏱️ **Durée** : 45 minutes.
> 📁 **On crée** : `boutique/commandes.py`.

---

## 11.1 La seule vraie question

MongoDB n'offre que deux façons de relier des données. Tout le reste en découle.

### Imbriquer (*embedding*)

Le sous-objet vit **dans** le document parent.

```json
{
  "_id": ObjectId("..."),
  "numero": "CMD-2026-0001",
  "client": { "id": 7, "nom": "Dupont", "email": "dupont@example.com" },
  "lignes": [
    { "sku": "KBD-0010", "libelle": "Clavier TKL", "quantite": 1, "prix": 119.00 }
  ],
  "total": 119.00
}
```

✅ une seule lecture, aucune jointure · atomicité gratuite sur l'ensemble
❌ duplication si l'objet est partagé · le document grossit

### Référencer

On stocke une clé, et on résout en deuxième requête (ou avec `$lookup`).

```json
{ "_id": ObjectId("..."), "numero": "CMD-2026-0001", "client_id": 7 }
```

✅ pas de duplication · entités partagées · documents bornés
❌ deux requêtes, ou un `$lookup` plus coûteux qu'un `JOIN` SQL bien indexé

---

## 11.2 Les cinq questions qui décident

| Question | Si oui → |
|---|---|
| Les données sont-elles **toujours lues ensemble** ? | imbriquer |
| Le sous-objet est-il **partagé** entre plusieurs parents ? | référencer |
| Le tableau peut-il **croître sans limite** ? | référencer |
| Le sous-objet change-t-il **beaucoup plus souvent** que le parent ? | référencer |
| Faut-il modifier l'ensemble de façon **atomique** ? | imbriquer |

### Par cardinalité

| Relation | Choix par défaut | Exemple |
|---|---|---|
| **1 ↔ 1** | imbriquer | une adresse de livraison dans une commande |
| **1 ↔ peu** (borné, quelques dizaines) | imbriquer | les lignes d'une commande |
| **1 ↔ beaucoup** (des milliers) | référencer côté "many" | les commandes d'un client |
| **1 ↔ énormément** (non borné) | référencer, et jamais l'inverse | les événements d'un capteur |
| **plusieurs ↔ plusieurs** | référencer des deux côtés, ou tableau d'ID du côté le moins volumineux | produits ↔ catégories |

> **Le garde-fou absolu** : un document ne peut pas dépasser **16 Mo**. Tout tableau qui grandit avec le temps - commandes, événements, messages, avis - doit être soit borné (pattern *Subset*), soit référencé. "Ça tiendra bien" n'est pas une décision d'architecture.

---

## 11.3 Mise en pratique : la collection `commandes`

### À faire - `commandes.py`

```python
from datetime import datetime, timezone

from bson import Decimal128

from db import get_db

db = get_db()

commande = {
    "numero": "CMD-2026-0001",
    "statut": "payee",
    "cree_le": datetime.now(timezone.utc),

    # 1↔1 : imbriqué. L'adresse d'une commande lui appartient et ne change plus.
    "livraison": {"ligne1": "12 rue des Lilas", "ville": "Lyon", "cp": "69003"},

    # Extended Reference : l'identifiant + les 2 champs qu'on affiche toujours.
    "client": {"id": 7, "nom": "Dupont", "email": "dupont@example.com"},

    # 1↔peu : imbriqué. Avec le libellé et le prix FIGÉS au moment de l'achat.
    "lignes": [
        {"sku": "KBD-0010", "libelle": "Clavier TKL silencieux",
         "quantite": 1, "prix_unitaire": Decimal128("119.00")},
        {"sku": "SCR-0011", "libelle": "Ecran 24 pouces",
         "quantite": 2, "prix_unitaire": Decimal128("179.00")},
    ],

    # Computed : pré-calculé à l'écriture, jamais recalculé à l'affichage.
    "total": Decimal128("477.00"),
    "nb_articles": 3,
}

db.commandes.insert_one(commande)

# La page "détail commande" : UNE requête, aucune jointure
print(db.commandes.find_one({"numero": "CMD-2026-0001"}))

# "Les commandes de ce client" : on interroge par la référence dénormalisée
db.commandes.create_index([("client.id", 1), ("cree_le", -1)], name="client_date")
for c in db.commandes.find({"client.id": 7}).sort("cree_le", -1).limit(10):
    print(c["numero"], c["total"], c["client"]["nom"])
```

### Les trois décisions de ce document, expliquées

1. **L'adresse est imbriquée** : elle appartient à cette commande et ne doit *surtout pas* suivre les changements d'adresse du client. Une commande est un **instantané**.
2. **Le client est en *Extended Reference*** : on garde son `id` (pour retrouver la fiche complète) plus les deux champs affichés partout (`nom`, `email`). La liste des commandes s'affiche donc sans aucune jointure.
3. **Le libellé et le prix sont recopiés dans les lignes.** Ce n'est pas de la redondance négligente : c'est une **obligation métier**. Si le prix du clavier change demain, la commande d'hier doit continuer d'afficher 119 €. En SQL, on est obligé de faire pareil - sauf qu'on l'oublie souvent.

---

## 11.4 Les patterns à connaître

| Pattern | Idée | Quand l'utiliser |
|---|---|---|
| **Extended Reference** | dupliquer les 2-3 champs du référencé qu'on affiche toujours | éviter un `$lookup` sur chaque ligne d'une liste |
| **Subset** | garder les N derniers éléments dans le parent, le reste dans une collection annexe | les 10 derniers avis d'un produit qui en a 5 000 |
| **Computed** | pré-calculer les agrégats à l'écriture (`total`, `nb_avis`, `note_moyenne`) | lectures ≫ écritures |
| **Bucket** | grouper N mesures par document (1 document = 1 heure de relevés) | IoT, séries temporelles |
| **Outlier** | traiter à part les 0,1 % de documents anormaux (`has_extras: true`) | l'utilisateur aux 2 millions d'abonnés |
| **Schema Versioning** | `schema_version` dans chaque document (étape 10) | migration sans interruption |
| **Attribute** | `[{k: "hz", v: 144}]` au lieu de champs variables | attributs hétérogènes, un seul index |

### Le pattern *Subset* en pratique

```python
# Les 5 derniers avis dans le produit, tous les avis dans leur propre collection
db.avis.insert_one({"produit_sku": "KBD-0010", "auteur": "alice", "note": 5,
                    "texte": "Parfait", "date": datetime.now(timezone.utc)})

db.produits.update_one(
    {"sku": "KBD-0010"},
    {"$push": {"derniers_avis": {"$each": [{"auteur": "alice", "note": 5}],
                                 "$slice": -5}},        # ne garde que les 5 derniers
     "$inc": {"nb_avis": 1}},                           # Computed
)
```

La fiche produit affiche `derniers_avis` et `nb_avis` **sans toucher** à la collection `avis`. La page "tous les avis", plus rare, fait une requête dédiée.

---

## 11.5 Dupliquer, oui - mais avec un propriétaire

Toute donnée dupliquée doit avoir **une source de vérité** et **un processus de mise à jour**. Sans cela, la dénormalisation devient de l'incohérence.

```python
# Le client change de nom : il faut propager dans les copies "vivantes"
db.clients.update_one({"_id": 7}, {"$set": {"nom": "Dupont-Martin"}})
db.commandes.update_many({"client.id": 7, "statut": "panier"},
                         {"$set": {"client.nom": "Dupont-Martin"}})
```

Notez le filtre `"statut": "panier"` : on ne met à jour que les commandes **non encore validées**. Les commandes payées gardent le nom qu'elles avaient au moment de l'achat - c'est un instantané, pas un cache.

Les trois façons de propager :

| Méthode | Principe | Quand |
|---|---|---|
| **À l'écriture** | l'application met à jour les copies dans la foulée | peu de copies, cohérence immédiate attendue |
| **Change stream** | un service écoute les modifications et propage | beaucoup de copies, découplage souhaité (nécessite un replica set) |
| **Traitement périodique** | un job recalcule les copies (`$merge`) | tolérance à quelques minutes de décalage |

**Avant de dupliquer, posez-vous la question** : cette copie doit-elle suivre l'original (c'est un cache → il faut un processus de propagation) ou figer une valeur historique (c'est un instantané → il ne faut surtout pas la mettre à jour) ? Les deux sont légitimes ; les confondre produit des bugs très difficiles à retrouver.

---

## 11.6 `$lookup` - la jointure, quand on ne peut pas l'éviter

```python
pipeline = [
    {"$match": {"numero": "CMD-2026-0001"}},
    {"$lookup": {
        "from": "clients",
        "localField": "client.id",
        "foreignField": "_id",
        "as": "client_complet",
    }},
    {"$unwind": "$client_complet"},      # $lookup renvoie toujours un tableau
]
for doc in db.commandes.aggregate(pipeline):
    print(doc["client_complet"])
```

Trois choses à savoir :

1. **`$lookup` n'est pas un `JOIN` SQL.** Il n'y a pas d'optimiseur de jointure : le serveur exécute une recherche dans la collection cible **pour chaque document en entrée**. Sans index sur `foreignField`, c'est un scan complet à chaque fois.
2. **Il renvoie toujours un tableau**, même pour une correspondance unique - d'où le `$unwind` systématique.
3. **En abuser est un signal.** Si toutes vos lectures passent par des `$lookup`, c'est que vous avez modélisé en tables. Revenez au § 11.2 : ces données sont-elles lues ensemble ? Alors imbriquez-les, ou dénormalisez les deux champs affichés (*Extended Reference*).

---

## 11.7 Les anti-patterns à ne pas reproduire

| Anti-pattern | Symptôme | Correctif |
|---|---|---|
| **Le modèle relationnel déguisé** | une collection par table, `$lookup` partout | repartir des écrans à servir |
| **Le tableau non borné** | `avis`, `evenements`, `messages` qui grossissent sans fin | *Subset* ou collection séparée |
| **Le document géant** | on approche des 16 Mo, chaque lecture rapatrie tout | scinder, projeter, référencer |
| **La collection fourre-tout** | une collection `donnees` avec un champ `type` et rien en commun | une collection par famille de requêtes |
| **Trop de collections** | 200 collections pour 200 nuances de la même chose | l'inverse du précédent : le documentaire aime les collections homogènes en *usage* |
| **Le champ tableau qu'on cherche toujours par index** | `{"tags.0": ...}`, positions codées en dur | un tableau n'a pas d'ordre stable garanti : cherchez par valeur |

> **Le juste équilibre** : une collection doit regrouper des documents **utilisés de la même façon**, même s'ils n'ont pas la même forme. Nos produits (claviers, écrans, livres, abonnements) partagent la même collection parce qu'ils sont listés, filtrés et affichés ensemble. Les commandes sont ailleurs parce qu'on ne les interroge jamais avec les produits.

---

## Exercice (20 min)

Modélisez un **blog** en MongoDB. Les besoins :

- une page article : titre, corps, auteur (nom + avatar), tags, et les 10 derniers commentaires ;
- une page auteur : sa biographie et la liste de ses 20 derniers articles ;
- un article peut avoir des milliers de commentaires ;
- un auteur peut changer de nom et d'avatar, et cela doit se voir **partout**.

Donnez : les collections, la forme des documents, et pour chaque relation la justification (imbriquer/référencer) ainsi que le processus de mise à jour des données dupliquées.

<details>
<summary>Voir la correction</summary>

**Trois collections : `articles`, `auteurs`, `commentaires`.**

```json
// articles
{
  "_id": ObjectId("..."),
  "slug": "decouvrir-mongodb",
  "titre": "Découvrir MongoDB",
  "corps": "...",
  "publie_le": ISODate("2026-09-06T08:00:00Z"),
  "auteur": { "id": ObjectId("..."), "nom": "Alice", "avatar": "/img/alice.png" },
  "tags": ["mongodb", "nosql"],
  "nb_commentaires": 137,
  "derniers_commentaires": [
    { "auteur": "bob", "texte": "Très clair !", "poste_le": ISODate("...") }
  ]
}

// auteurs
{ "_id": ObjectId("..."), "nom": "Alice", "avatar": "/img/alice.png", "bio": "..." }

// commentaires
{ "_id": ObjectId("..."), "article_id": ObjectId("..."), "auteur": "bob",
  "texte": "...", "poste_le": ISODate("...") }
```

**Les justifications, relation par relation :**

- **Tags → imbriqués** (tableau de chaînes, borné). La table de liaison du modèle SQL disparaît. Un index sur `tags` sert les pages "tous les articles du tag X".
- **Auteur → référencé + *Extended Reference***. La bio n'est pas dans l'article (elle n'y est jamais affichée), mais `nom` et `avatar` y sont dupliqués : la page article s'affiche en une requête.
- **Commentaires → collection séparée + *Subset***. Des milliers par article : les imbriquer tous ferait exploser le document. On garde les 10 derniers dans l'article (`$push` avec `$slice: -10`) et `nb_commentaires` en *Computed*.
- **Articles d'un auteur → référence inversée** : on interroge `articles` avec `{"auteur.id": ...}`, trié par `publie_le` décroissant, avec un index composé `{"auteur.id": 1, "publie_le": -1}`. On ne stocke **pas** la liste des articles dans l'auteur : elle serait non bornée.

**Le processus de mise à jour** - c'est la partie que l'on oublie le plus souvent :

```python
def renommer_auteur(auteur_id, nouveau_nom, nouvel_avatar):
    db.auteurs.update_one({"_id": auteur_id},
                          {"$set": {"nom": nouveau_nom, "avatar": nouvel_avatar}})
    db.articles.update_many({"auteur.id": auteur_id},
                            {"$set": {"auteur.nom": nouveau_nom,
                                      "auteur.avatar": nouvel_avatar}})
```

Ici, l'énoncé dit explicitement "cela doit se voir partout" : la copie est un **cache**, on la propage. Si l'énoncé avait dit "l'article doit garder le nom de l'auteur au moment de la publication", la copie serait un **instantané** et il ne faudrait rien propager. Même structure, décision opposée - d'où l'importance de poser la question.

**Sur un gros volume**, ce `update_many` peut toucher des milliers d'articles : on le lance en tâche de fond, ou on branche un change stream sur `auteurs`. C'est le prix assumé de la dénormalisation, et il se compare favorablement au coût d'un `JOIN` sur chaque affichage.

</details>

---

## ✅ Ce qu'il faut retenir

1. Deux outils seulement : **imbriquer** ou **référencer**. Cinq questions suffisent à choisir.
2. Ce qui est lu ensemble vit ensemble ; ce qui est partagé ou non borné est référencé.
3. Les 16 Mo par document ne sont pas une limite théorique : tout tableau qui grandit doit être borné.
4. La duplication est normale, à condition d'identifier **une source de vérité** et un processus de propagation.
5. Distinguez le **cache** (à propager) de l'**instantané** (à figer) : la structure est la même, la décision est inverse.
6. `$lookup` existe, mais son usage systématique révèle une modélisation relationnelle déguisée.

→ **[Étape 12 - Index et performances](12-index-et-performances.md)**
