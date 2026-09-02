# Cosa manca per la consegna

Stato verificato in produzione il **01/09/2026**. Ogni voce è stata controllata
sull'ambiente reale, non dedotta dal codice.

Il lavoro di sviluppo è chiuso: la suite gira verde (389 test) e la CI su GitHub
blocca `master`. Quello che resta dipende da credenziali, budget o accessi che
non sono nostri.

---

## 1. Il client secret SP-API è scaduto — BLOCCANTE

**I dati sono fermi dall'11 agosto.** Tutti e tre gli account (Bitron, Dialcos,
VIGNOLA) sono in errore con codice `LWA_SECRET_EXPIRED`. Le vendite si fermano
al 7–10 agosto; l'ultima sincronizzazione riuscita è dell'11–12 agosto.

Amazon obbliga a ruotare il client secret ogni 180 giorni e il fallimento è
silenzioso: il token viene emesso normalmente, è SP-API che risponde 403.

La rotazione richiede pochi minuti e la fa chi ha accesso a Seller/Vendor
Central: **App e servizi → Develop Apps → l'app → Rotate secret**, poi si
incolla il nuovo valore in Inthezon → Impostazioni. Il `client_id` non cambia e
i refresh token restano validi: **nessun account va ricollegato**. Il vecchio
secret resta attivo 7 giorni dopo la generazione del nuovo.

Finché non viene fatto, la piattaforma mostra dati di tre settimane fa. È la
prima cosa da chiudere prima di mostrare il tool a chiunque.

Dettagli e sintomi: pagina *Rotazione del client secret* nella documentazione
in-app.

## 2. Credito Anthropic esaurito

Verificato con una chiamata reale: la chiave è configurata in produzione ma il
saldo è a zero (`credit balance is too low`).

Conseguenza: le narrative AI, Market Research e le raccomandazioni strategiche
ricadono sui testi template. L'interfaccia lo dichiara, non si rompe nulla, ma
la parte "intelligente" del prodotto non è quella che il cliente ha visto in
demo.

Serve ricaricare il credito sul workspace Anthropic.

## 3. SendGrid: nessun mittente verificato

La chiave API è presente e valida, ma l'account ha **zero mittenti verificati e
zero domini autenticati** (verificato in diretta il 01/09/2026). Ogni invio
riceve 403.

Non parte quindi: reset password, report programmati, email di alert e digest
giornaliero. È anche il motivo per cui la scadenza del secret al punto 1 è
passata inosservata per settimane — l'unico canale di notifica era l'email.

Serve verificare un Single Sender oppure autenticare il dominio (DKIM/SPF)
nella dashboard SendGrid. È gratuito e richiede pochi minuti.

## 4. Il repository è pubblico

`github.com/gunnit/amazon` è pubblico e nella sua storia sono presenti due dump
del database. Va reso privato dal proprietario del repository.

## 5. Il ripristino del database non è mai stato provato

Il point-in-time recovery risulta attivo con una finestra di circa 7 giorni, ma
non è mai stata eseguita una prova completa di ripristino. La prova richiede di
creare un'istanza temporanea a pagamento e va concordata.

Procedura, limiti e comando per la copia esterna: pagina *Backup e ripristino
del database* nella documentazione in-app.

---

## Opzionali, non bloccanti

**Sentry** — `SENTRY_DSN` non è impostata in produzione. Il codice è già
collegato: basta incollare il DSN per avere gli errori del backend fuori
dall'applicazione. Oggi, senza email funzionante, non esiste nessun canale di
allerta esterno.

**Google Sheets** — le credenziali OAuth non sono configurate. La funzione
fallisce a runtime se qualcuno la usa, non compromette il resto.

**Amazon Advertising** — credenziali presenti e funzionanti dal 31/07/2026.
Nessuna azione richiesta.

---

## Cose che non servono, per scelta

**Redis e Celery.** La produzione non li usa. Il lavoro schedulato gira
in-process dentro il servizio API (`ENABLE_INPROCESS_SCHEDULER=true`), che è
quello che `render.yaml` provisiona. Per questo il servizio è fissato a una sola
istanza: una seconda eseguirebbe ogni job due volte.

> **Non avviare `celery beat`.** Schedula `manage_data_retention` e
> `manage_partitions`, che cancellano i dati più vecchi di
> `DATA_RETENTION_MONTHS` — compresi i circa 4 anni di storico vendor che Amazon
> non fornisce una seconda volta. Le due attività si rifiutano di partire senza
> `ALLOW_DESTRUCTIVE_RETENTION=true`: lascia quella variabile non impostata.

**AWS S3.** Fuori perimetro. Gli artefatti dei report sono colonne binarie nel
database e le immagini di catalogo non sono gestite dalla piattaforma.

L'elenco completo delle variabili d'ambiente, con cosa si rompe senza ciascuna,
è nella pagina *Configurazione* della documentazione in-app.
