"""
Module d'extraction par Vision-Language Model (VLM) via l'API OpenRouter.
Gère l'encodage optimisé des images en base64, la priorisation des modèles gratuits,
la stratégie de retry/fallback automatique et la sérialisation des bilans extraits.
"""

import os
import re
import json
import time
import base64
from pathlib import Path
from typing import Optional, Dict, Any, List

import cv2
import dotenv
from openai import OpenAI

from schema import BilanMarocain, BilanActif, BilanPassif, LigneActif, LignePassif

dotenv.load_dotenv()

# Modèles gratuits ordonnés par priorité (priorité demandée par l'utilisateur)
MODELS_PRIORITY = [
    "google/gemma-4-26b-a4b-it:free",
    "nvidia/nemotron-3.5-super-vl:free",
    "openrouter/free"
]


def encode_image_to_jpeg_base64(image_path: str, max_size: int = 2048, quality: int = 85) -> str:
    """
    Charge une image via OpenCV, ajuste sa dimension maximale si nécessaire pour optimiser la latence
    et le quota VLM sans perte de lisibilité des chiffres, puis l'encode en JPEG base64.
    """
    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(f"Impossible de charger l'image : {image_path}")
        
    height, width = img.shape[:2]
    if max(width, height) > max_size:
        scale = max_size / float(max(width, height))
        new_width = int(width * scale)
        new_height = int(height * scale)
        img = cv2.resize(img, (new_width, new_height), interpolation=cv2.INTER_AREA)
        
    encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), quality]
    success, buffer = cv2.imencode(".jpg", img, encode_params)
    if not success:
        raise ValueError(f"Échec de l'encodage JPEG pour : {image_path}")
        
    return base64.b64encode(buffer).decode("utf-8")


def repair_truncated_json(text: str) -> Optional[Dict[str, Any]]:
    """Tente de fermer et réparer un objet JSON tronqué par la limite de tokens."""
    s = text.strip()
    s = re.sub(r",\s*$", "", s)
    stack = []
    in_string = False
    escape = False
    
    for char in s:
        if char == '"' and not escape:
            in_string = not in_string
        elif not in_string:
            if char in "{[":
                stack.append(char)
            elif char == "}" and stack and stack[-1] == "{":
                stack.pop()
            elif char == "]" and stack and stack[-1] == "[":
                stack.pop()
        escape = (char == "\\" and not escape)
        
    if in_string:
        s += '"'
    s = re.sub(r",\s*$", "", s)
    
    while stack:
        opener = stack.pop()
        if opener == "{":
            s += "}"
        elif opener == "[":
            s += "]"
            
    try:
        return json.loads(s)
    except Exception:
        return None


def clean_and_extract_json(text: str) -> Dict[str, Any]:
    """
    Nettoie et extrait un objet JSON valide depuis la réponse brute d'un LLM/VLM.
    Utilise une stratégie multi-niveaux ultra-robuste :
    1. Blocs Markdown ```json ... ```
    2. Détection séquentielle de tous les dictionnaires valides via JSONDecoder
    3. Sélection prioritaire du dictionnaire racine le plus complet
    4. Réparation automatique des structures JSON tronquées
    """
    if not text:
        raise ValueError("La réponse du modèle est vide.")
        
    # Niveau 1 : Blocs markdown ```json ... ```
    matches = re.findall(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text, re.IGNORECASE)
    for m in reversed(matches):
        try:
            return json.loads(m.strip())
        except Exception:
            pass

    # Niveau 2 : Détection de tous les objets JSON via raw_decode
    decoder = json.JSONDecoder()
    candidates = []
    idx = 0
    while idx < len(text):
        pos = text.find("{", idx)
        if pos == -1:
            break
        try:
            obj, end_pos = decoder.raw_decode(text[pos:])
            if isinstance(obj, dict):
                candidates.append(obj)
                idx = pos + end_pos
                continue
        except Exception:
            pass
        idx = pos + 1
        
    if candidates:
        candidates_sorted = sorted(candidates, key=lambda d: len(str(d)), reverse=True)
        return candidates_sorted[0]

    # Niveau 3 : Tentative de réparation de JSON tronqué
    first_brace = text.find("{")
    if first_brace != -1:
        repaired = repair_truncated_json(text[first_brace:])
        if repaired and isinstance(repaired, dict):
            return repaired

    raise ValueError(f"Impossible d'extraire un JSON valide : {text[:250]}...")


class VLMExtractor:
    """Client d'extraction VLM avec gestion des retries et du fallback multi-modèles."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY non configurée dans l'environnement ou .env.")
            
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=self.api_key,
            default_headers={
                "HTTP-Referer": "https://ensam-casablanca.ma",
                "X-Title": "TP3 Extraction Bilan CGNC"
            }
        )

    def extract_from_image(
        self,
        image_path: str,
        prompt_text: str,
        max_retries: int = 2
    ) -> Dict[str, Any]:
        """
        Envoie une image avec le prompt au VLM avec basculement automatique
        vers les modèles de secours en cas d'erreur 429 / 404 / 500.
        """
        img_b64 = encode_image_to_jpeg_base64(image_path)
        data_url = f"data:image/jpeg;base64,{img_b64}"
        
        last_error = None
        
        for model in MODELS_PRIORITY:
            for attempt in range(max_retries):
                print(f"  [VLM] Tentative avec '{model}' (essai {attempt+1}/{max_retries})...", flush=True)
                try:
                    response = self.client.chat.completions.create(
                        model=model,
                        messages=[{
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt_text},
                                {"type": "image_url", "image_url": {"url": data_url}}
                            ]
                        }],
                        max_tokens=6000,
                        temperature=0.1,
                        timeout=90
                    )
                    
                    choice = response.choices[0]
                    content = choice.message.content
                    
                    # Si content est None mais qu'un reasoning existe, vérifier s'il contient le JSON
                    if not content and hasattr(choice.message, "reasoning"):
                        content = choice.message.reasoning
                        
                    if not content:
                        raise ValueError("Le modèle a renvoyé un contenu vide.")
                        
                    parsed_json = clean_and_extract_json(content)
                    print(f"  [OK] Extraction réussie avec le modèle '{model}' !", flush=True)
                    # Sauvegarde optionnelle du brut pour traçabilité
                    debug_stem = Path(image_path).stem
                    with open(f"data/processed/raw_{debug_stem}.txt", "w", encoding="utf-8") as f_raw:
                        f_raw.write(content)
                    return parsed_json
                    
                except Exception as e:
                    print(f"  [AVERTISSEMENT] Échec avec '{model}' : {type(e).__name__} - {e}", flush=True)
                    last_error = e
                    # Si erreur 429 (quota ou rate-limit), basculer immédiatement au modèle suivant sans retry
                    if "429" in str(e) or "RateLimit" in type(e).__name__:
                        print("  [INFO] 429 détecté, passage immédiat au modèle suivant...", flush=True)
                        break
                    time.sleep(2)
                    
            print(f"  [FALLBACK] Basculement vers le modèle suivant...", flush=True)
            
        raise RuntimeError(f"Tous les modèles ont échoué. Dernière erreur : {last_error}")


def run_pipeline_extraction(
    version: str,
    actif_img: str = "data/processed/bilan_group_4_actif.png",
    passif_img: str = "data/processed/bilan_group_4_passif.png",
    output_dir: Optional[str] = None
) -> Dict[str, Any]:
    """
    Exécute l'extraction complète (Actif + Passif) pour une version donnée ('v1' ou 'v2').
    Sauvegarde le JSON consolidé dans output/<version>/bilan_extracted.json.
    """
    version = version.lower()
    prompt_file = f"prompts/extract_bilan_{version}.txt"
    if not Path(prompt_file).exists():
        raise FileNotFoundError(f"Fichier de prompt introuvable : {prompt_file}")
        
    with open(prompt_file, "r", encoding="utf-8") as f:
        base_prompt = f.read()
        
    out_dir = Path(output_dir or f"output/{version}")
    out_dir.mkdir(parents=True, exist_ok=True)
    
    extractor = VLMExtractor()
    
    print(f"\n=======================================================")
    print(f" DÉBUT EXTRACTION - VERSION {version.upper()} ({prompt_file})")
    print(f"=======================================================")
    
    # 1. Extraction Page 1 : ACTIF
    print(f"\n[1/2] Extraction de l'ACTIF ({actif_img})...")
    actif_prompt = (
        f"{base_prompt}\n\nATTENTION : Cette image est la page BILAN - ACTIF. "
        f"Extrais tous les postes de l'Actif Immobilisé, Actif Circulant et Trésorerie Actif avec Brut, Amort/Prov, Net N, Net N-1."
    )
    actif_data = extractor.extract_from_image(actif_img, actif_prompt)
    
    # 2. Extraction Page 2 : PASSIF
    print(f"\n[2/2] Extraction du PASSIF ({passif_img})...")
    passif_prompt = (
        f"{base_prompt}\n\nATTENTION : Cette image est la page BILAN - PASSIF. "
        f"Extrais tous les postes du Financement Permanent, Passif Circulant et Trésorerie Passif avec Exercice N et Exercice N-1."
    )
    passif_data = extractor.extract_from_image(passif_img, passif_prompt)
    
    # Consolidation
    consolidated = {
        "version": version,
        "document": Path(actif_img).stem.replace("_actif", ""),
        "actif": actif_data.get("actif", actif_data),
        "passif": passif_data.get("passif", passif_data),
        "entreprise": actif_data.get("entreprise") or passif_data.get("entreprise"),
        "exercice_clos_le": actif_data.get("exercice_clos_le") or passif_data.get("exercice_clos_le")
    }
    
    # Validation Pydantic si v2
    if version == "v2":
        try:
            print("\n[VALIDATION PYDANTIC] Application du schéma BilanMarocain...")
            # Normalisation et validation
            bilan_obj = BilanMarocain(
                entreprise=consolidated.get("entreprise"),
                exercice_clos_le=consolidated.get("exercice_clos_le"),
                actif=consolidated.get("actif", {}),
                passif=consolidated.get("passif", {})
            )
            consolidated["pydantic_validated"] = True
            # Met à jour avec le dictionnaire propre validé
            consolidated["bilan_structure"] = json.loads(bilan_obj.model_dump_json())
            print("  -> Schéma validé avec succès par Pydantic !")
        except Exception as err:
            print(f"  [ATTENTION] Avertissement Pydantic : {err}")
            consolidated["pydantic_validated"] = False
            consolidated["pydantic_error"] = str(err)
            
    out_file = out_dir / "bilan_extracted.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(consolidated, f, ensure_ascii=False, indent=2)
        
    print(f"\n[SUCCÈS] Bilan consolidé sauvegardé dans : {out_file}")
    return consolidated


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Extraction de bilans marocains via VLM")
    parser.add_argument("--version", choices=["v1", "v2", "both"], default="both", help="Version à exécuter")
    args = parser.parse_args()
    
    if args.version in ("v1", "both"):
        run_pipeline_extraction("v1")
    if args.version in ("v2", "both"):
        run_pipeline_extraction("v2")
