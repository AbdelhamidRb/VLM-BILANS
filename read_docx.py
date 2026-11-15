import sys, io, docx
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
doc = docx.Document(r'C:\Users\pc\.gemini\antigravity\brain\5befc7bf-7b85-4a25-85ec-8b6120762bda\.user_uploaded\media_1794668725614_a025029c.docx')
for p in doc.paragraphs:
    print(p.text)
