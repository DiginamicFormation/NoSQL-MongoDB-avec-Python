"""Schemas d'entree Pydantic et serialisation BSON -> JSON.

Fourni : vous n'avez pas a modifier ce fichier.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from bson import Decimal128, ObjectId
from pydantic import BaseModel, Field

NIVEAUX = ["junior", "mature", "senior", "gourou"]
FAMILLES = ["backend", "frontend", "data", "securite", "infra"]


class Point(BaseModel):
    type: str = "Point"
    coordinates: list[float] = Field(min_length=2, max_length=2)


class Habitat(BaseModel):
    lieu: str
    point: Point


class Evolution(BaseModel):
    niveau: str
    titre: str
    annees_xp: int = 0
    salaire: str                       # converti en Decimal128 par le depot
    attaques: list[str] = []


class EspeceCreation(BaseModel):
    numero: int = Field(ge=1)
    nom: str = Field(min_length=2, max_length=100)
    famille: str
    langages: list[str] = []
    xp: int | None = None              # absent = espece jamais capturee
    evolutions: list[Evolution] = Field(min_length=4, max_length=4)
    habitats: list[Habitat] = []


class Modification(BaseModel):
    champs: dict[str, Any]


def en_json(valeur: Any) -> Any:
    """Rend un document BSON serialisable en JSON.

    ObjectId, Decimal128 et datetime n'ont pas d'equivalent JSON : sans cette
    conversion, FastAPI leve une erreur de serialisation et renvoie un 500 que
    l'on ne voit que dans les journaux de l'API.
    """
    if isinstance(valeur, ObjectId):
        return str(valeur)
    if isinstance(valeur, Decimal128):
        return str(valeur)
    if isinstance(valeur, datetime):
        return valeur.isoformat()
    if isinstance(valeur, dict):
        return {cle: en_json(v) for cle, v in valeur.items()}
    if isinstance(valeur, list):
        return [en_json(v) for v in valeur]
    return valeur
