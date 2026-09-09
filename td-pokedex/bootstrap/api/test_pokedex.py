"""Tests du Pokedex, chapitre par chapitre.

Fourni : vous n'avez pas a modifier ce fichier. Il est votre juge de paix.

    docker compose exec api pytest -v
    docker compose exec api pytest -k chapitre03      # le chapitre en cours

Chaque test travaille sur une base jetable `pokedex_test`, supprimee ensuite.

Les tests ne se contentent pas du code HTTP : ils verifient l'etat de la base.
Une route encore branchee sur une fixture repond juste, mais n'ecrit rien - et
c'est l'assertion Mongo qui la demasque.
"""
from __future__ import annotations

import os

import pytest
from bson import Decimal128

from db import fermer, get_client
from repository import (DepotPokedex, DocumentInvalide, EspeceDejaExistante,
                        EspeceIntrouvable, EvolutionImpossible)

BASE_TEST = "pokedex_test"


def evolutions(prefixe: str = "Test") -> list[dict]:
    return [{"niveau": n, "titre": f"{prefixe} {n}", "annees_xp": i * 3,
             "salaire": str(30000 + i * 12000), "attaques": []}
            for i, n in enumerate(["junior", "mature", "senior", "gourou"])]


def habitat(lieu: str, lon: float, lat: float) -> dict:
    # GeoJSON : [longitude, latitude], dans cet ordre.
    return {"lieu": lieu, "point": {"type": "Point", "coordinates": [lon, lat]}}


PARIS = habitat("Paris", 2.3522, 48.8566)
LYON = habitat("Lyon", 4.8357, 45.7640)
MARSEILLE = habitat("Marseille", 5.3698, 43.2965)


@pytest.fixture
async def depot():
    """Un depot neuf par test, sur une base jetable.

    Le client est ferme a la fin de CHAQUE test : pytest-asyncio ouvre une
    boucle asyncio par test, et un AsyncMongoClient reste lie a la boucle qui
    l'a cree. Sans cette fermeture, le deuxieme test leverait
    "Cannot use AsyncMongoClient in different event loop".
    """
    os.environ.setdefault("MONGODB_URI",
                          "mongodb://app:app-password@mongo:27017/pokedex"
                          "?authSource=pokedex")
    client = get_client()
    depot = DepotPokedex(client[BASE_TEST])
    await depot.initialiser()
    yield depot
    await client.drop_database(BASE_TEST)
    await fermer()


# ------------------------------------------------------------- chapitre 01
async def test_chapitre01_import_reexecutable(depot):
    catalogue = [{"numero": 1, "nom": "Dev Python", "famille": "backend",
                  "stade": 0, "evolutions": evolutions(), "habitats": [PARIS],
                  "schema_version": 1}]
    assert await depot.importer(catalogue) == (1, 0)       # creee
    await depot.importer(catalogue)                        # relance : pas de doublon
    assert await depot.compter() == 1

    cree_le = (await depot.par_numero(1))["cree_le"]
    await depot.importer([{**catalogue[0], "nom": "Dev Python 3"}])
    espece = await depot.par_numero(1)
    assert espece["nom"] == "Dev Python 3"
    assert espece["cree_le"] == cree_le          # $setOnInsert : date preservee


# ------------------------------------------------------------- chapitre 02
async def test_chapitre02_sante(depot):
    sante = await depot.sante()
    assert sante["mongo"] == "ok"
    assert sante["version"].startswith("8.")
    assert sante["especes"] == 0


# ------------------------------------------------------------- chapitre 03
async def test_chapitre03_lister_filtre_et_pagination(depot):
    for i in range(1, 6):
        await depot.creer(i, f"Dev {i}", "backend", evolutions(), habitats=[PARIS])
    await depot.creer(10, "Dev React", "frontend", evolutions(), habitats=[LYON])

    assert len(await depot.lister()) == 6
    assert len(await depot.lister(famille="backend")) == 5
    assert len(await depot.lister(taille=2)) == 2

    page1 = await depot.lister(taille=2)
    page2 = await depot.lister(apres=page1[-1]["numero"], taille=2)
    assert {e["numero"] for e in page1} & {e["numero"] for e in page2} == set()


async def test_chapitre03_recherche_par_nom_ou_langage(depot):
    await depot.creer(1, "Dev Python", "backend", evolutions(), langages=["python"])
    await depot.creer(2, "Dev Java", "backend", evolutions(), langages=["java"])
    assert len(await depot.lister(q="python")) == 1
    assert len(await depot.lister(q="dev")) == 2


async def test_chapitre03_la_liste_ne_renvoie_pas_id(depot):
    """_id est un ObjectId : il n'est pas serialisable en JSON."""
    await depot.creer(1, "Dev Python", "backend", evolutions())
    assert "_id" not in (await depot.lister())[0]


# ------------------------------------------------------------- chapitre 04
async def test_chapitre04_fiche_et_champs_specifiques(depot):
    await depot.creer(8, "Dev Svelte", "frontend", evolutions(), habitats=[LYON],
                      bundler="vite", reactivite="compilation")
    espece = await depot.par_numero(8)
    assert espece["nom"] == "Dev Svelte"
    assert espece["bundler"] == "vite"

    commun, specifique = depot.decouper(espece)
    assert set(specifique) == {"bundler", "reactivite"}
    assert "evolutions" in commun


async def test_chapitre04_espece_sans_xp(depot):
    """Une espece jamais capturee n'a pas de champ xp : rien ne doit casser."""
    await depot.creer(8, "Dev Svelte", "frontend", evolutions())
    espece = await depot.par_numero(8)
    assert "xp" not in espece            # champ ABSENT, pas a zero
    assert espece.get("xp") is None


async def test_chapitre04_espece_introuvable(depot):
    with pytest.raises(EspeceIntrouvable):
        await depot.par_numero(999)


async def test_chapitre04_les_salaires_sont_serialisables(depot):
    """Decimal128 n'a pas d'equivalent JSON : en_json le convertit en chaine."""
    await depot.creer(1, "Dev Python", "backend", evolutions())
    espece = await depot.par_numero(1)
    assert isinstance(espece["evolutions"][0]["salaire"], str)
    assert not isinstance(espece["_id"], object.__class__)
    assert isinstance(espece["_id"], str)


# ------------------------------------------------------------- chapitre 05
async def test_chapitre05_creer_puis_lire(depot):
    await depot.creer(1, "Dev Python", "backend", evolutions(),
                      langages=["python"], xp=4200, habitats=[PARIS])
    espece = await depot.par_numero(1)
    assert espece["stade"] == 0                  # on nait toujours junior
    assert espece["xp"] == 4200
    assert espece["schema_version"] == 1


async def test_chapitre05_numero_unique(depot):
    await depot.creer(1, "Dev Python", "backend", evolutions())
    with pytest.raises(EspeceDejaExistante):
        await depot.creer(1, "Dev Autre", "backend", evolutions())


async def test_chapitre05_le_salaire_devient_decimal(depot):
    """Un salaire stocke en chaine sortirait de tout filtre numerique."""
    await depot.creer(1, "Dev Python", "backend", evolutions())
    brut = await depot.col.find_one({"numero": 1})
    assert isinstance(brut["evolutions"][0]["salaire"], Decimal128)


# ------------------------------------------------------------- chapitre 06
async def test_chapitre06_modifier(depot):
    await depot.creer(1, "Dev Python", "backend", evolutions())
    assert await depot.modifier(1, {"nom": "Dev Python 3"}) is True
    assert await depot.modifier(1, {"nom": "Dev Python 3"}) is False   # deja a jour
    assert (await depot.par_numero(1))["nom"] == "Dev Python 3"
    assert "maj_le" in await depot.par_numero(1)


async def test_chapitre06_modifier_refuse_les_operateurs(depot):
    """Protection contre l'injection d'operateurs venue d'un formulaire."""
    await depot.creer(1, "Dev Python", "backend", evolutions())
    with pytest.raises(DocumentInvalide):
        await depot.modifier(1, {"$set": {"stade": 3}})
    with pytest.raises(DocumentInvalide):
        await depot.modifier(1, {"numero": 2})


async def test_chapitre06_evolution(depot):
    await depot.creer(1, "Dev Python", "backend", evolutions())
    for attendu in (1, 2, 3):
        assert (await depot.evoluer(1))["stade"] == attendu
    with pytest.raises(EvolutionImpossible):
        await depot.evoluer(1)                       # on ne depasse pas gourou
    assert (await depot.par_numero(1))["stade"] == 3


async def test_chapitre06_evolution_concurrente(depot):
    """Quatre evolutions simultanees depuis junior : trois passent, une echoue.

    La condition metier est dans le filtre : sans elle, on sauterait des stades.
    """
    import asyncio

    await depot.creer(1, "Dev Python", "backend", evolutions())
    resultats = await asyncio.gather(*(depot.evoluer(1) for _ in range(4)),
                                     return_exceptions=True)
    reussites = [r for r in resultats if not isinstance(r, Exception)]
    assert len(reussites) == 3
    assert (await depot.par_numero(1))["stade"] == 3


# ------------------------------------------------------------- chapitre 07
async def test_chapitre07_extinction_logique(depot):
    await depot.creer(900, "Dev Perl", "backend", evolutions())
    await depot.eteindre(900)

    with pytest.raises(EspeceIntrouvable):
        await depot.par_numero(900)
    assert (await depot.par_numero(900, inclure_eteintes=True))["numero"] == 900
    assert await depot.compter() == 0
    # Le document est toujours la : c'est une extinction, pas une suppression.
    assert await depot.compter(inclure_eteintes=True) == 1

    await depot.restaurer(900)
    assert await depot.compter() == 1


async def test_chapitre07_extinction_definitive(depot):
    await depot.creer(901, "Dev TurboPascal", "backend", evolutions())
    await depot.eteindre_definitivement(901)
    with pytest.raises(EspeceIntrouvable):
        await depot.par_numero(901, inclure_eteintes=True)


async def test_chapitre07_index_ttl_partiel(depot):
    """Le TTL ne doit viser que les documents ayant reellement une date."""
    index = {i["name"]: i async for i in await depot.col.list_indexes()}
    ttl = index["ttl_extinction"]
    assert ttl["expireAfterSeconds"] == 30 * 24 * 3600
    assert ttl["partialFilterExpression"] == {"eteinte_le": {"$type": "date"}}


# ------------------------------------------------------------- chapitre 08
async def test_chapitre08_autour_de(depot):
    await depot.creer(1, "Dev Lyon", "backend", evolutions(), habitats=[LYON])
    await depot.creer(2, "Dev Paris", "backend", evolutions(), habitats=[PARIS])
    await depot.creer(3, "Dev Sud", "backend", evolutions(), habitats=[MARSEILLE])

    proches = await depot.autour_de(4.8357, 45.7640, 50)
    assert [e["numero"] for e in proches] == [1]

    # $near trie par distance croissante : Lyon, puis Marseille, puis Paris.
    larges = await depot.autour_de(4.8357, 45.7640, 500)
    assert [e["numero"] for e in larges] == [1, 3, 2]


async def test_chapitre08_autour_ignore_les_eteintes(depot):
    await depot.creer(1, "Dev Lyon", "backend", evolutions(), habitats=[LYON])
    await depot.eteindre(1)
    assert await depot.autour_de(4.8357, 45.7640, 50) == []


async def test_chapitre08_dans_la_zone(depot):
    await depot.creer(1, "Dev Lyon", "backend", evolutions(), habitats=[LYON])
    await depot.creer(2, "Dev Paris", "backend", evolutions(), habitats=[PARIS])

    idf = await depot.dans_la_zone(ouest=1.8, sud=48.5, est=2.8, nord=49.1)
    assert [e["numero"] for e in idf] == [2]


async def test_chapitre08_habitats_multiples(depot):
    """Un habitat suffit : l'index 2dsphere est multikey."""
    await depot.creer(1, "Dev partout", "backend", evolutions(),
                      habitats=[PARIS, LYON, MARSEILLE])
    assert len(await depot.autour_de(2.3522, 48.8566, 20)) == 1
    assert len(await depot.autour_de(5.3698, 43.2965, 20)) == 1


# ------------------------------------------------------------- chapitre 09
async def test_chapitre09_statistiques(depot):
    await depot.creer(1, "Dev Python", "backend", evolutions(), xp=100)
    await depot.creer(8, "Dev Svelte", "frontend", evolutions())     # sans xp
    stats = {ligne["famille"]: ligne for ligne in await depot.statistiques()}

    assert stats["backend"]["xp_total"] == 100
    assert stats["frontend"]["xp_total"] == 0
    assert stats["frontend"]["sans_xp"] == 1        # absent n'est pas zero
    # $avg sur Decimal128 rendrait un Decimal128 : la conversion est faite
    # cote serveur, la valeur doit donc etre un nombre.
    assert isinstance(stats["backend"]["salaire_gourou_moyen"], (int, float))


async def test_chapitre09_audit_ne_depasse_jamais_cent_pour_cent(depot):
    await depot.creer(1, "Dev Python", "backend", evolutions())
    await depot.creer(900, "Dev Perl", "backend", evolutions())
    await depot.eteindre(900)          # l'audit balaie aussi les eteintes

    lignes = await depot.auditer()
    assert lignes
    assert all(ligne["taux"] <= 100 for ligne in lignes)
    champs = {ligne["champ"]: ligne for ligne in lignes}
    assert champs["numero"]["taux"] == 100
    assert champs["eteinte_le"]["taux"] == 50


async def test_chapitre09_audit_repere_les_types_mixtes(depot):
    await depot.creer(1, "Dev Python", "backend", evolutions(), langages=["python"])
    # Le document sale que l'on trouvera dans le vrai jeu de donnees.
    await depot.col.insert_one({"numero": 901, "nom": "Dev TurboPascal",
                                "famille": "backend", "stade": 3,
                                "evolutions": [], "langages": "pascal",
                                "schema_version": 0})
    champs = {ligne["champ"]: ligne for ligne in await depot.auditer()}
    assert champs["langages"]["types"] == ["array", "string"]


async def test_chapitre09_explain_utilise_un_index(depot):
    await depot.creer(1, "Dev Python", "backend", evolutions())
    plan = await depot.plan_de_requete({"famille": "backend"})
    assert "IXSCAN" in str(plan)         # famille_numero, pas un COLLSCAN
