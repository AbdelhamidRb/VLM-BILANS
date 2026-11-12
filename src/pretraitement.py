import fitz  # pymupdf

doc = fitz.open("data/pdf/bilan_group_4.pdf")
for i, page in enumerate(doc, start=1):
    pix = page.get_pixmap(dpi=200)
    pix.save(f"data/images/bilan_group_4_p{i}.png")
    print(f"Page {i} sauvegardée")