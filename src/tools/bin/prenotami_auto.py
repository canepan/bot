import os
import re
import time
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

# Modifica questi valori con le tue credenziali e dati di prenotazione
BOOKING_URL = "https://prenotami.esteri.it/Services/Booking/5770"

def run_automation():
    # Carica le variabili contenute nel file .env
    load_dotenv()

    # Recupera i dati dalle variabili d'ambiente
    EMAIL = os.getenv("PRENOTAMI_EMAIL")
    PASSWORD = os.getenv("PRENOTAMI_PASSWORD")
    PASSPORT_NUMBER = os.getenv("PRENOTAMI_PASSPORT")
    PDF_PATH = os.getenv("PDF_PATH")
    pdf_path = os.path.abspath(PDF_PATH or "Carta_identita_Canepa_Nicola-20230124.pdf")
    with sync_playwright() as p:
        # Avviamo il browser in modalità visibile per gestire eventuali verifiche/OTP
        browser = p.chromium.launch(
            headless=False,
            # channel="chrome", # Utilizza Google Chrome installato nel sistema
            # args=["--disable-blink-features=AutomationControlled"]
        )
        context = browser.new_context()
        page = context.new_page()

        # Configura 5 minuti di timeout globale
        page.set_default_timeout(300000)
        page.set_default_navigation_timeout(300000)

        print("[1/4] Navigazione verso la Home di Prenot@mi...")
        page.goto("https://prenotami.esteri.it/Home")

        # 1. Clic sul pulsante d'accesso per generare la sessione OAuth2 dinamica
        print("[2/4] Avvio della procedura di Login...")
        # Adatta il selettore del pulsante d'accesso se necessario
        page.click("a[href*='login'], button:has-text('Accedi')")

        # Attesa del reindirizzamento su iam.esteri.it
        page.wait_for_url("**/iam.esteri.it/**")

        # Compilazione del modulo di login su IAM
        #page.fill("input[name='Username'], input[type='email']", EMAIL)
        page.fill("input[name='callback_1'], input[type='email']", EMAIL)
        #page.fill("input[name='Password'], input[type='password']", PASSWORD)
        page.fill("input[name='callback_2'], input[type='password']", PASSWORD)
        page.click("button[type='submit'], input[type='submit']")

        # Attesa del ritorno su Prenot@mi
        page.wait_for_url("**/prenotami.esteri.it/**")
        print("[✓] Login completato con successo.")

        # 2. Navigazione alla pagina del servizio specifico
        print(f"[3/4] Navigazione verso il servizio {BOOKING_URL}...")
        page.goto(BOOKING_URL)

        # Attesa del caricamento del modulo
        page.wait_for_selector("form")

        # 3. Compilazione dei campi del modulo
        print("[4/4] Compilazione dei campi...")
        
        # Esempi di selettori per la compilazione (da adattare in base al form specifico):
        # page.fill("#Field1", "Valore Campo 1")
        # page.select_option("select#TipoDocumento", value="Passaporto")
        # page.check("input[type='checkbox']#privacy")
        page.fill("#Nome", "Nicola")
        page.fill("#Cognome", "Canepa")
        page.select_option("select#TipoDocumento", value="Passaporto")

        # 1. Attendi che il campo o il pulsante di caricamento sia visibile nel DOM
        # page.wait_for_selector("input[type='file']", timeout=300000)
        page.wait_for_selector("input[type='file']")
        # 2. Esegui l'upload
        page.set_input_files("input[type='file']", pdf_path)
        print("[✓] File PDF caricato con successo!")
        page.get_by_label(re.compile(r"numero", re.I)).fill(PASSPORT_NUMBER)

        # NOTA: Se il servizio richiede codice OTP via email o CAPTCHA manuale,
        # lo script si mette in pausa consentendoti di inserirlo a schermo.
        input("Controlla i dati a schermo. Premi INVIO nel terminale per procedere con l'invio del modulo...")

        # 4. Invia il modulo
        # page.click("button[type='submit']#btnSubmit")
        print("[✓] Modulo inviato.")

        time.sleep(5)
        browser.close()

if __name__ == "__main__":
    run_automation()
