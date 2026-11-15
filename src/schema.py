"""
Modèles Pydantic pour la validation et la structuration des bilans comptables marocains (CGNC).
Prend en charge le nettoyage des valeurs numériques (virgules, espaces, nulls) et fournit
des méthodes de calcul et de vérification des équilibres comptables.
"""

from typing import List, Optional, Union
from pydantic import BaseModel, Field, field_validator


def clean_numeric(val: Union[float, int, str, None]) -> float:
    """Nettoie et convertit une valeur de montant comptable en float."""
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        # Suppression des espaces, espaces insécables, tirets comptables et devises
        v = val.strip().replace(" ", "").replace("\xa0", "").replace("DH", "").replace("dh", "")
        if v in ("", "-", "—", "N/A", "null", "None"):
            return 0.0
        # Remplacement de la virgule décimale française par un point
        v = v.replace(",", ".")
        try:
            return float(v)
        except ValueError:
            return 0.0
    return 0.0


class LigneActif(BaseModel):
    """Ligne élémentaire ou rubrique de l'Actif selon le CGNC."""
    poste: str = Field(..., description="Intitulé normalisé du poste comptable CGNC")
    brut: float = Field(default=0.0, description="Montant brut de l'exercice N")
    amortissements_provisions: float = Field(default=0.0, description="Amortissements et provisions cumulés de l'exercice N")
    net: float = Field(default=0.0, description="Montant net N = Brut - Amortissements/Provisions")
    exercice_precedent: float = Field(default=0.0, description="Montant net de l'exercice précédent N-1")

    @field_validator("brut", "amortissements_provisions", "net", "exercice_precedent", mode="before")
    @classmethod
    def coerce_float(cls, v):
        return clean_numeric(v)


class LignePassif(BaseModel):
    """Ligne élémentaire ou rubrique du Passif selon le CGNC."""
    poste: str = Field(..., description="Intitulé normalisé du poste comptable CGNC")
    exercice: float = Field(default=0.0, description="Montant de l'exercice N")
    exercice_precedent: float = Field(default=0.0, description="Montant de l'exercice précédent N-1")

    @field_validator("exercice", "exercice_precedent", mode="before")
    @classmethod
    def coerce_float(cls, v):
        return clean_numeric(v)


class BilanActif(BaseModel):
    """Structure complète de l'Actif du bilan (Modèle Normal CGNC)."""
    actif_immobilise: List[LigneActif] = Field(default_factory=list, description="Postes de l'Actif Immobilisé (Masse I)")
    total_actif_immobilise: Optional[LigneActif] = Field(default=None, description="Total I (Actif Immobilisé)")
    
    actif_circulant: List[LigneActif] = Field(default_factory=list, description="Postes de l'Actif Circulant hors trésorerie (Masse II)")
    total_actif_circulant: Optional[LigneActif] = Field(default=None, description="Total II (Actif Circulant)")
    
    tresorerie_actif: List[LigneActif] = Field(default_factory=list, description="Postes de Trésorerie - Actif (Masse III)")
    total_tresorerie_actif: Optional[LigneActif] = Field(default=None, description="Total III (Trésorerie - Actif)")
    
    total_general_actif: Optional[LigneActif] = Field(default=None, description="TOTAL GÉNÉRAL I + II + III")


class BilanPassif(BaseModel):
    """Structure complète du Passif du bilan (Modèle Normal CGNC)."""
    financement_permanent: List[LignePassif] = Field(default_factory=list, description="Postes du Financement Permanent (Masse I)")
    total_financement_permanent: Optional[LignePassif] = Field(default=None, description="Total I (Financement Permanent)")
    
    passif_circulant: List[LignePassif] = Field(default_factory=list, description="Postes du Passif Circulant hors trésorerie (Masse II)")
    total_passif_circulant: Optional[LignePassif] = Field(default=None, description="Total II (Passif Circulant)")
    
    tresorerie_passif: List[LignePassif] = Field(default_factory=list, description="Postes de Trésorerie - Passif (Masse III)")
    total_tresorerie_passif: Optional[LignePassif] = Field(default=None, description="Total III (Trésorerie - Passif)")
    
    total_general_passif: Optional[LignePassif] = Field(default=None, description="TOTAL GÉNÉRAL I + II + III")


class BilanMarocain(BaseModel):
    """Bilan comptable marocain complet (Actif + Passif)."""
    entreprise: Optional[str] = Field(default=None, description="Raison sociale ou dénomination de l'entreprise")
    exercice_clos_le: Optional[str] = Field(default=None, description="Date de clôture de l'exercice (ex: 31/12/2021)")
    unite: str = Field(default="DH", description="Unité monétaire (DH ou KDH)")
    actif: BilanActif = Field(default_factory=BilanActif)
    passif: BilanPassif = Field(default_factory=BilanPassif)
