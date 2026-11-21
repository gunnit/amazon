# Aggiornamento massivo e approvazioni

Su Amazon non si scrive mai senza una persona che approva. Ogni modifica (da Excel, un ripristino, una variante, un nuovo articolo) diventa una **richiesta**, viene controllata da Amazon e aspetta in **Approvazioni**.

## Esporta, modifica, carica

In **Catalogo > Aggiornamento massivo**:

1. **Esporta catalogo**: il file Excel contiene i contenuti attuali (ASIN, SKU, tipo di prodotto, titolo, bullet 1-5, descrizione, keyword backend, item highlights, keyword principale, immagine principale, immagini 1-8, parent, SKU parent, tema, più colonne `attr:nome` per gli attributi semplici). È anche il modello da ricaricare.
2. Modifica **solo le celle da cambiare**. Una cella **vuota lascia il valore com'è**: non esiste un modo per cancellare un campo con il file. Così un file che compila solo `bullet_2` non tocca gli altri bullet.
3. **Carica file** (.xlsx o .csv, massimo 10 MB) e scegli come usarlo.

Limiti per riga: titolo 200 caratteri, bullet 500, descrizione 2000, item highlights 125, keyword backend 250 byte; gli URL delle immagini devono iniziare con `https://`. Le righe fuori limite non vengono usate e sono elencate con il problema. Le immagini si sostituiscono posizione per posizione e non se ne cancella nessuna.

## Due modi d'uso

- **Aggiorna le schede prodotto**: le celle cambiate diventano richieste. Amazon le verifica subito, nulla viene pubblicato.
- **Imposta come versione approvata**: il file diventa il riferimento di Protezione contenuti. Su Amazon non cambia nulla. Solo amministratori.

La colonna `main_keyword` aggiorna la keyword principale nel tool, non su Amazon.

## Nuovi articoli

In **Nuovi articoli** scrivi il tipo di prodotto Amazon e scarica il **modello**: contiene SKU, tipo di prodotto e gli attributi obbligatori, poi i consigliati. Compilalo e caricalo. Ogni riga è controllata sugli attributi obbligatori del tipo di prodotto e poi verificata da Amazon, come tutto il resto. I modelli ufficiali NIS di Amazon per ora non sono supportati.

## Il flusso di approvazione

**Approvazioni** raccoglie le richieste, per lotto. Per ognuna vedi prima e dopo, e l'esito della verifica di Amazon. Gli stati:

| Stato | Significato |
| --- | --- |
| In verifica | Appena creata, Amazon non l'ha ancora controllata |
| Validata da Amazon | Controllo superato, pronta per l'approvazione |
| Rifiutata da Amazon | Il controllo ha trovato errori: correggi e ricarica |
| Approvata | Un amministratore ha dato il via |
| Rifiutata | Scartata da un operatore |
| Inviata | Spedita in un feed, in elaborazione |
| Accettata da Amazon | Applicata |
| Non riuscita | Amazon l'ha rifiutata in fase di invio: apri la richiesta per il dettaglio |
| Solo file | Non può passare dalle API (vedi sotto) |
| Caricata a mano | Segnata come caricata su Vendor Central |

La **verifica** usa la modalità di prova di Amazon (VALIDATION_PREVIEW): non pubblica nulla. Una richiesta non validata non si può inviare.

Chi può fare cosa: tutti gli operatori caricano file, creano ripristini e **rifiutano**. **Approvare**, **inviare ad Amazon**, **aggiornare lo stato del feed** e **segnare come caricato a mano** è riservato agli **amministratori**. Prima dell'invio il tool chiede conferma e mostra quante schede verranno modificate.

Sotto le 50 richieste ogni scheda parte con una chiamata diretta; da 50 in su parte un unico feed, il cui esito si legge con **Aggiorna stato feed**.

## Vendor Central: file e caricamento a mano

Se un account non ha accesso in scrittura alle schede (nessun codice vendor, o manca lo SKU), le richieste sono **solo file**. Dopo l'approvazione usa **Scarica file per Vendor Central** (un file JSON_LISTINGS_FEED con le richieste approvate di quel lotto), caricalo a mano su Vendor Central, poi premi **Segna come caricato a mano**: le richieste passano a «Caricata a mano» e non risultano più da gestire. Le richieste a cui manca lo SKU o il tipo di prodotto restano fuori dal file.

## Immagini da togliere

Sugli account Vendor Amazon non permette di cancellare un valore dalla scheda. Se una modifica richiede di rimuovere immagini (per esempio ne carichi meno di quante ce ne sono online), la richiesta lo segnala con **Rimuovi a mano queste immagini su Vendor Central**: le sostituzioni partono, le rimozioni vanno fatte a mano.
