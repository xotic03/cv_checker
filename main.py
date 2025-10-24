import os
from io import BytesIO
from fastapi import FastAPI, File, UploadFile, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from openai import OpenAI
import pdfplumber, docx, stripe
import markdown
from dotenv import load_dotenv
import re

# ---------- ENV laden ----------
load_dotenv()  # liest .env im Projektordner

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# ---------- API Keys aus .env ----------
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
STRIPE_PUBLIC = os.getenv("STRIPE_PUBLIC_KEY")
STRIPE_SECRET = os.getenv("STRIPE_SECRET_KEY")
BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8000")

if not OPENAI_KEY:
    raise RuntimeError("❌ OPENAI_API_KEY fehlt in .env")
if not STRIPE_SECRET:
    raise RuntimeError("❌ STRIPE_SECRET_KEY fehlt in .env")

client = OpenAI(api_key=OPENAI_KEY)
stripe.api_key = STRIPE_SECRET

# ---------- Dateiformate ----------
ALLOWED_EXTENSIONS = [".pdf", ".docx", ".txt"]

def allowed_file(filename: str) -> bool:
    """Nur bestimmte Dateiformate akzeptieren"""
    return any(filename.lower().endswith(ext) for ext in ALLOWED_EXTENSIONS)

# ---------- Datei-Extraktion ----------
def extract_text(file: UploadFile) -> str:
    """Extrahiert Text aus PDF, DOCX oder TXT"""
    name = file.filename.lower()
    if name.endswith(".pdf"):
        with pdfplumber.open(file.file) as pdf:
            return "\n".join([(p.extract_text() or "") for p in pdf.pages])
    if name.endswith(".docx"):
        d = docx.Document(file.file)
        return "\n".join([p.text for p in d.paragraphs])
    return file.file.read().decode("utf-8", errors="ignore")

# ---------- Seiten ----------
@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse("index.html", {
        "request": request,
        "stripe_public": STRIPE_PUBLIC
    })

@app.get("/impressum", response_class=HTMLResponse)
def impressum(request: Request):
    return templates.TemplateResponse("impressum.html", {"request": request})

@app.get("/datenschutz", response_class=HTMLResponse)
def datenschutz(request: Request):
    return templates.TemplateResponse("datenschutz.html", {"request": request})

# ---------- Stripe Checkout ----------
@app.post("/create_checkout")
def create_checkout():
    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        mode="payment",
        line_items=[{
            "price_data": {
                "currency": "eur",
                "product_data": {"name": "AI Bewerbungs-Check"},
                "unit_amount": 500,  # 5 €
            },
            "quantity": 1,
        }],
        success_url=f"{BASE_URL}/?paid=true",
        cancel_url=f"{BASE_URL}/",
    )
    return RedirectResponse(session.url, status_code=303)

# ---------- Analyse ----------
@app.post("/analyze", response_class=HTMLResponse)
def analyze(request: Request, file: UploadFile = File(...)):
    text = extract_text(file)

    prompt = f"""
Du bist ein professioneller HR-Experte und Personalberater mit 20 Jahren Erfahrung in der Bewerbungsanalyse.
Deine Aufgabe ist es, den folgenden Lebenslauf inhaltlich, strukturell und sprachlich zu bewerten.
Dabei stammt der Text **aus einer automatischen PDF-Extraktion** — du musst also mit unvollständigen Zeilenumbrüchen,
Sonderzeichen oder nicht optimaler Formatierung rechnen. Das ist KEIN Fehler des Bewerbers und darf nicht negativ gewertet werden.

---

### 🎯 ZIEL DER ANALYSE:
Erstelle eine professionelle, strukturierte und verständliche Auswertung des Lebenslaufs, die einem Bewerber dabei hilft,
seine Chancen bei einer realen Bewerbung zu verbessern. Sei sachlich, präzise und hilfreich — kein Lehrer, kein Kritiker.

---

### 🧩 DEIN AUFBAU (halte dich exakt an diese Struktur):

#### 1️⃣ Gesamtbewertung
- Bewerte den Lebenslauf mit einer Punktzahl zwischen **0 und 100 Punkten**.
- Die Bewertung soll **nicht zu hart** ausfallen, sondern realistisch, nachvollziehbar und motivierend.
- 0 = unbrauchbar / 100 = perfekt aufbereitet.
- Berücksichtige dabei nur inhaltliche und fachliche Qualität — **nicht das Layout** der PDF oder technische Probleme.

#### 2️⃣ Positive Zusammenfassung (2–4 Sätze)
- Beschreibe, was am Lebenslauf **gut gelungen** ist.
- Gehe auf erkennbare Stärken ein, z. B. klare Berufserfahrung, relevante Praktika, Ausbildung, Motivation, Sprachkenntnisse oder Engagement.
- Verwende eine **wertschätzende, professionelle Sprache** (z. B. „zeigt Struktur und Zielorientierung“ statt „nicht schlecht gemacht“).

#### 3️⃣ Bewertungskategorien (jeweils kurz kommentieren, 1–2 Sätze):
Bewerte jede der folgenden Kategorien mit Schulnoten von 1 (sehr gut) bis 6 (ungenügend) UND mit einem kurzen Kommentar.

| Kategorie | Bedeutung | Bewertung (1–6) | Kommentar |
|------------|------------|----------------|------------|
| Struktur | Aufbau und logische Gliederung der Inhalte | | |
| Sprache & Ausdruck | Grammatik, Rechtschreibung, Stil, Wortwahl | | |
| Inhalt & Relevanz | Aussagekraft der Angaben, Vollständigkeit, rote Linie | | |
| Wirkung & Professionalität | Erster Eindruck, Seriosität, Gesamteindruck | | |

#### 4️⃣ Detaillierte Analyse (3–6 Absätze)
Erstelle eine tiefgehende, aber verständliche Analyse, die folgende Aspekte berücksichtigt:

- **Berufliche Erfahrungen & Praktika**  
  Bewerte, ob die beschriebenen Tätigkeiten, Zeiträume und Aufgaben schlüssig und aussagekräftig dargestellt sind.
  Wenn ein Bewerber etwa mehrere Praktika aufführt, erkläre, welche Wirkung diese auf Personaler haben könnten.
  Zeige Verbesserungspotenziale (z. B. Ergänzung konkreter Tätigkeiten, Technologien, Lernerfahrungen).

- **Ausbildung & schulischer Werdegang**  
  Prüfe, ob Ausbildung und Schulverlauf nachvollziehbar sind und ob Übergänge klar erkennbar sind.
  Gehe auf eventuelle Stärken (z. B. berufliche Schule mit Technikbezug) oder Lücken (z. B. fehlende Abschlussbezeichnung) ein.

- **Kenntnisse & Fähigkeiten**  
  Bewerte die Relevanz und Vollständigkeit der genannten Kenntnisse.  
  Falls der Bewerber z. B. Programmiersprachen, Sprachen oder Soft Skills erwähnt, beurteile, wie diese im Kontext des Berufsbilds wirken.

- **Gesamteindruck**  
  Fasse zusammen, wie der Lebenslauf auf dich als HR-Profi wirkt:
  Wirkt die Person engagiert, orientiert, unsicher, sehr jung oder zielstrebig?  
  Formuliere es wertschätzend, konstruktiv und ohne pauschale Urteile.

#### 5️⃣ Verbesserungsvorschläge (max. 5 Punkte)
Erstelle **maximal fünf konkrete, praxisnahe Vorschläge**, die den Lebenslauf inhaltlich und formal verbessern könnten:
- **Keine** allgemeinen Tipps wie „mach das schöner“ oder „bessere Formatierung“.  
- Nur **inhaltliche** und **sprachlich-relevante** Verbesserungen (z. B. „Füge kurze Beschreibung der Tätigkeiten hinzu“, „Formuliere Zielsetzung am Anfang“, „Ergänze besondere Projekte oder Zertifikate“).
- Verwende pro Vorschlag 1–2 Sätze.

#### 6️⃣ Abschließendes Fazit
Beende die Analyse mit einem freundlichen, professionellen Fazit in 2–3 Sätzen.  
Zeige, dass der Lebenslauf Potenzial hat, und ermutige zur weiteren Verbesserung — aber ohne übertriebenes Lob.

---

### ⚠️ WICHTIGE REGELN:
1. **Ignoriere** Zeilenumbrüche, Sonderzeichen, Bindestriche, fehlende Punkte oder Layout-Fehler — sie stammen aus der PDF-Konvertierung.
2. **Erkenne Eigennamen und Marken** (z. B. „fe:male Innovation Hub“, „Telekom Deutschland GmbH“) korrekt und **ändere sie nicht**.
3. **Beurteile fair nach Inhalt, nicht nach Design oder Format.**
4. **Kein unnötiges Werten** wie „wirkt unordentlich“, „nicht schön formatiert“, „optisch unübersichtlich“ — das ist irrelevant.
5. **Analysiere neutral**, ohne Ironie, Sarkasmus oder Belehrungen.
6. **Schreibe ausschließlich in deutscher Sprache.**
7. **Nutze Markdown** für Absätze, Listen und Hervorhebungen.

---

Hier ist der extrahierte Lebenslauftext:
---------------------------------------
{text}
---------------------------------------

Erstelle jetzt die Analyse im definierten Format.
"""

    result = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[{"role": "user", "content": prompt}]
    )

    output_raw = result.choices[0].message.content.strip()

    # 🧠 Markdown in echtes HTML umwandeln
    output_html = markdown.markdown(
        output_raw,
        extensions=["extra", "sane_lists", "nl2br", "smarty"]
    )

    score_match = re.search(r"(\d{1,3})\s*(?:/|von)?\s*100", output_raw)
    score = int(score_match.group(1)) if score_match else None
    if score and score > 100:
        score = 100  # Sicherheit: Kein Unsinnswert

    return templates.TemplateResponse(
        "result.html",
        {
            "request": request,
            "filename": file.filename,
            "output": output_html,
            "score": score if score else "-",
        }
    )