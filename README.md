# ServiceApp (RO) – Final
Funcții: multi-atelier, login (demo/demo), PDF (pdfkit), branding (logo+culoare), dashboard (Chart.js), modul client (/client), PWA.

## Local
pip install -r requirements.txt
# (Windows) Instalează wkhtmltopdf și setează WKHTMLTOPDF_PATH dacă e nevoie
python app.py
# login: demo / demo

## Render (producție)
- Împinge proiectul pe GitHub, apoi în Render → New → Blueprint (folosește render.yaml).
- Variabile: DATABASE_URL (automat), SECRET_KEY (automat).
