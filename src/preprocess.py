"""
Module de prétraitement documentaire pour bilans comptables scannés.
Convertit les pages PDF en images haute résolution (300 DPI) et applique
une normalisation de contraste OpenCV pour optimiser la lisibilité par le VLM.
"""

import os
from pathlib import Path
import pymupdf  # PyMuPDF
import cv2
import numpy as np


def preprocess_pdf_to_images(
    pdf_path: str,
    output_dir: str = "data/processed",
    dpi: int = 300,
    apply_enhancement: bool = True
) -> list[str]:
    """
    Convertit chaque page d'un PDF scanné en image PNG haute résolution (300 DPI),
    avec amélioration optionnelle du contraste via OpenCV (CLAHE / Normalisation).
    
    Retourne la liste des chemins des images générées.
    """
    pdf_file = Path(pdf_path)
    if not pdf_file.exists():
        raise FileNotFoundError(f"Fichier PDF introuvable : {pdf_path}")
        
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    
    doc = pymupdf.open(pdf_file)
    saved_images = []
    
    # Matrice de mise à l'échelle pour le DPI souhaité (DPI standard = 72)
    zoom = dpi / 72.0
    mat = pymupdf.Matrix(zoom, zoom)
    
    print(f"[PREPROCESS] Traitement de '{pdf_file.name}' ({len(doc)} pages, {dpi} DPI)...")
    
    for page_idx in range(len(doc)):
        page = doc[page_idx]
        pix = page.get_pixmap(matrix=mat, alpha=False)
        
        # Conversion du buffer PyMuPDF vers image OpenCV (RGB -> BGR)
        img_np = np.frombuffer(pix.samples, dtype=np.uint8).reshape((pix.height, pix.width, 3))
        img_bgr = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)
        
        if apply_enhancement:
            # Conversion en niveaux de gris pour améliorer le contraste
            gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
            
            # Normalisation du contraste avec CLAHE (Contrast Limited Adaptive Histogram Equalization)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            enhanced_gray = clahe.apply(gray)
            
            # Reconverting to 3 channels for VLM compatibility
            final_img = cv2.cvtColor(enhanced_gray, cv2.COLOR_GRAY2BGR)
        else:
            final_img = img_bgr
            
        page_name = "actif" if page_idx == 0 else ("passif" if page_idx == 1 else f"page_{page_idx+1}")
        out_filename = out_path / f"{pdf_file.stem}_{page_name}.png"
        
        # Enregistrement en PNG
        cv2.imwrite(str(out_filename), final_img)
        print(f"  -> Page {page_idx+1} sauvegardée : {out_filename} ({pix.width}x{pix.height} px)")
        saved_images.append(str(out_filename))
        
    doc.close()
    return saved_images


if __name__ == "__main__":
    import sys
    pdf_input = sys.argv[1] if len(sys.argv) > 1 else "data/raw/bilan_group_4.pdf"
    output_files = preprocess_pdf_to_images(pdf_input)
    print(f"[OK] Prétraitement terminé avec succès. {len(output_files)} images générées.")
