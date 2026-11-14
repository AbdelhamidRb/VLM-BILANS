from pathlib import Path
import cv2
import fitz  # PyMuPDF
import numpy as np

INPUT_DIR = Path("data/pdf")
OUTPUT_DIR = Path("data/processed")


def deskew_image(gray: np.ndarray) -> np.ndarray:
    """Redresse légèrement une image inclinée (angle entre -15° et +15°)."""
    thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    coords = np.column_stack(np.where(thresh > 0))
    if len(coords) < 100:
        return gray

    angle = cv2.minAreaRect(coords)[-1]
    if angle < -45:
        angle = -(90 + angle)
    else:
        angle = -angle

    # Ignorer les rotations aberrantes ou négligeables
    if abs(angle) < 0.3 or abs(angle) > 15:
        return gray

    h, w = gray.shape
    center = (w // 2, h // 2)
    matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    return cv2.warpAffine(
        gray, matrix, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE
    )


def enhance_scan(img_bgr: np.ndarray) -> np.ndarray:
    """Convertit en niveaux de gris, redresse et améliore le contraste (CLAHE)."""
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    deskewed = deskew_image(gray)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    return clahe.apply(deskewed)


def process_all(dpi: int = 300) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    supported_ext = {".pdf", ".png", ".jpg", ".jpeg"}
    files = [f for f in INPUT_DIR.iterdir() if f.is_file() and f.suffix.lower() in supported_ext]

    if not files:
        print("Aucun fichier PDF ou image trouvé dans 'data/'.")
        return

    for file_path in sorted(files):
        if file_path.suffix.lower() == ".pdf":
            doc = fitz.open(file_path)
            for page_idx, page in enumerate(doc, start=1):
                pix = page.get_pixmap(dpi=dpi)
                img_array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
                    pix.height, pix.width, pix.n
                )
                img_bgr = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
                cleaned = enhance_scan(img_bgr)
                out_path = OUTPUT_DIR / f"{file_path.stem}_p{page_idx}.png"
                cv2.imwrite(str(out_path), cleaned)
                print(f"[OK] {out_path}")
        else:
            img_bgr = cv2.imread(str(file_path))
            if img_bgr is not None:
                cleaned = enhance_scan(img_bgr)
                out_path = OUTPUT_DIR / f"{file_path.stem}.png"
                cv2.imwrite(str(out_path), cleaned)
                print(f"[OK] {out_path}")


if __name__ == "__main__":
    process_all()