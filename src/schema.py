from typing import Literal
from pydantic import BaseModel, Field


class LigneBilan(BaseModel):
    rubrique: str = Field(
        description="Grande masse ou rubrique du CGNC (ex: IMMOBILISATIONS CORPORELLES, FINANCEMENT PERMANENT)"
    )
    poste: str = Field(
        description="Intitulé exact du poste comptable (ex: Terrains, Clients et comptes rattachés)"
    )
    montant_net_N: float | None = Field(
        description="Montant Net de l'exercice N (null si case vide ou tiret '-')"
    )
    montant_net_N1: float | None = Field(
        description="Montant Net de l'exercice N-1 (null si case vide ou tiret '-')"
    )
    est_sous_total: bool = Field(
        default=False,
        description="True si la ligne représente un sous-total de rubrique (ex: TOTAL I, TOTAL II)"
    )


class BilanMarocain(BaseModel):
    type_tableau: Literal["ACTIF", "PASSIF", "COMPLET"] = Field(
        description="Nature de la page extraite : ACTIF, PASSIF ou COMPLET si les deux figurent"
    )
    unite: Literal["DH", "MILLIERS_DH"] = Field(
        description="Unité monétaire indiquée en en-tête du tableau"
    )
    exercice_N: str | None = Field(description="Année ou date de clôture de l'exercice N")
    exercice_N1: str | None = Field(description="Année ou date de clôture de l'exercice N-1")
    lignes: list[LigneBilan] = Field(description="Liste ordonnée des postes et sous-totaux")
    total_general_N: float | None = Field(description="Total Général (Actif ou Passif) Net N")
    total_general_N1: float | None = Field(description="Total Général (Actif ou Passif) Net N-1")