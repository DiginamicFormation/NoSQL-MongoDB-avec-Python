"""Pokedex des developpeurs - l'API HTTP.

Fourni : vous n'avez pas a modifier ce fichier. Ouvrez-le une fois, pour lire
la traduction des exceptions metier en codes HTTP - c'est la seule frontiere
entre votre depot et le protocole.

    http://localhost:8080   l'interface
    http://localhost:8000/docs   la documentation interactive de l'API
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from db import fermer, get_db
from modeles import EspeceCreation, Modification
from repository import (DepotPokedex, DocumentInvalide, ErreurPokedex,
                        EspeceDejaExistante, EspeceIntrouvable,
                        EvolutionImpossible)

journal = logging.getLogger("pokedex")

CODES_HTTP: dict[type[ErreurPokedex], int] = {
    EspeceIntrouvable: 404,
    EspeceDejaExistante: 409,
    EvolutionImpossible: 409,
    DocumentInvalide: 422,
}


@asynccontextmanager
async def cycle_de_vie(app: FastAPI):
    """Ne JAMAIS planter si Mongo est absent.

    Au chapitre 01, le depot ne parle pas encore a la base : l'API doit servir
    ses fixtures meme sans MongoDB. On journalise, on continue.
    """
    try:
        app.state.depot = DepotPokedex(get_db())
    except Exception as exc:                      # noqa: BLE001
        journal.warning("MongoDB indisponible au demarrage : %s", exc)
        app.state.depot = None
    yield
    await fermer()


app = FastAPI(title="Pokedex des developpeurs", lifespan=cycle_de_vie)

# Le front est servi par nginx, qui proxifie /api : meme origine, donc pas de
# CORS. Ces origines servent a qui lance uvicorn a la main, ou teste via /docs.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8080", "http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def depot(requete: Request) -> DepotPokedex:
    return requete.app.state.depot


@app.exception_handler(ErreurPokedex)
async def traduire_erreur(requete: Request, exc: ErreurPokedex) -> JSONResponse:
    """Une seule frontiere entre le metier et le protocole.

    Le parcours de __mro__ plutot qu'un acces direct : une sous-classe que vous
    creeriez herite du code de sa classe mere, au lieu de retomber sur 400.
    """
    code = next((CODES_HTTP[classe] for classe in type(exc).__mro__
                 if classe in CODES_HTTP), 400)
    return JSONResponse(status_code=code, content={"erreur": str(exc)})


# ------------------------------------------------------------------ sante
@app.get("/api/sante")
async def sante(requete: Request) -> dict[str, Any]:
    try:
        return await depot(requete).sante()
    except Exception as exc:                      # noqa: BLE001
        return JSONResponse(status_code=503,
                            content={"mongo": "hors ligne", "erreur": str(exc)})


# ----------------------------------------------------------------- lecture
@app.get("/api/especes")
async def lister(requete: Request,
                 famille: str | None = None,
                 q: str | None = None,
                 eteintes: bool = False,
                 apres: int | None = None,
                 taille: int = Query(default=20, ge=1, le=100)) -> list[dict]:
    return await depot(requete).lister(famille, q, eteintes, apres, taille)


@app.get("/api/statistiques")
async def statistiques(requete: Request) -> list[dict]:
    return await depot(requete).statistiques()


@app.get("/api/audit")
async def audit(requete: Request) -> list[dict]:
    return await depot(requete).auditer()


@app.get("/api/schema")
async def schema(requete: Request) -> dict:
    return await depot(requete).decrire_schema()


# ------------------------------------------------------------- geospatial
@app.get("/api/autour")
async def autour(requete: Request,
                 lon: float = Query(ge=-180, le=180),
                 lat: float = Query(ge=-90, le=90),
                 km: float = Query(default=50, gt=0, le=2000)) -> list[dict]:
    return await depot(requete).autour_de(lon, lat, km)


@app.get("/api/zone")
async def zone(requete: Request,
               ouest: float, sud: float, est: float, nord: float) -> list[dict]:
    return await depot(requete).dans_la_zone(ouest, sud, est, nord)


# --------------------------------------------------- fiche et modifications
@app.get("/api/especes/{numero}")
async def fiche(requete: Request, numero: int) -> dict[str, Any]:
    document = await depot(requete).par_numero(numero)
    commun, specifique = DepotPokedex.decouper(document)
    return {**commun, "specifique": specifique}


@app.post("/api/especes", status_code=201)
async def creer(requete: Request, espece: EspeceCreation,
                reponse: Response) -> dict[str, Any]:
    numero = await depot(requete).creer(
        numero=espece.numero, nom=espece.nom, famille=espece.famille,
        evolutions=[e.model_dump() for e in espece.evolutions],
        langages=espece.langages, xp=espece.xp,
        habitats=[h.model_dump() for h in espece.habitats],
    )
    reponse.headers["Location"] = f"/api/especes/{numero}"
    return {"numero": numero}


@app.patch("/api/especes/{numero}")
async def modifier(requete: Request, numero: int,
                   corps: Modification) -> dict[str, Any]:
    return {"modifie": await depot(requete).modifier(numero, corps.champs)}


@app.post("/api/especes/{numero}/evolution")
async def evoluer(requete: Request, numero: int) -> dict[str, Any]:
    return await depot(requete).evoluer(numero)


@app.delete("/api/especes/{numero}", status_code=204)
async def eteindre(requete: Request, numero: int,
                   definitif: bool = False) -> Response:
    if definitif:
        await depot(requete).eteindre_definitivement(numero)
    else:
        await depot(requete).eteindre(numero)
    return Response(status_code=204)


@app.post("/api/especes/{numero}/restauration")
async def restaurer(requete: Request, numero: int) -> dict[str, Any]:
    await depot(requete).restaurer(numero)
    return {"restauree": True}
