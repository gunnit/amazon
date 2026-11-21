# Limiti noti

Alcune cose non ci sono, o ci sono solo in parte. Non sono guasti: sono limiti di Amazon o scelte di perimetro. Leggere questa pagina prima di aprire una segnalazione ti risparmia tempo, e ti dà la risposta pronta quando è il cliente a chiedere.

## I dati pubblicitari partono dal 28/04/2026

Prima di quella data i dati delle campagne **non esistono** nella piattaforma, e non è recuperabile.

Il motivo è un limite di Amazon: mette a disposizione solo gli ultimi ~95 giorni di **Sponsored Products**. Quando è stato fatto il caricamento storico, indietro si arrivava fino al 28/04/2026 — e quel confine non si sposta più.

C'è un dettaglio che genera parecchi allarmi inutili: le altre due tipologie hanno finestre ancora più corte. **Sponsored Brands** conserva circa 60 giorni e **Sponsored Display** circa 65. Quindi questi due iniziano **più tardi** del 28/04.

Conseguenza pratica: qualsiasi "crollo" della spesa o delle vendite pubblicitarie che vedi **prima di giugno** è quasi sempre **dato assente**, non performance peggiore. Prima di scriverlo in un report, controlla che il periodo sia coperto.

## Recensioni e valutazioni dei concorrenti

Nelle schede dei prodotti concorrenti, **valutazione in stelle** e **numero di recensioni** compaiono nella maggior parte dei casi come **N/D**.

Non è un dato mancante per errore: Amazon non fornisce queste informazioni per i prodotti di terzi. Non c'è una configurazione che le sblocchi.

Restano invece normalmente disponibili **prezzo** e **posizione di vendita** dei concorrenti, che sono i due indicatori su cui puoi lavorare davvero.

## Cosa Amazon non ci lascia verificare

Il controllo di Qualità listing è grigio («non verificabile») quando Amazon non fornisce il dato tramite le API:

- **Video**: non è esposto, quindi non è mai verificabile.
- **Testo promozionale sull'immagine principale**: non viene controllato. Sfondo bianco e riempimento sì.
- **Item highlights**: verificabili solo quando Amazon li restituisce per quella scheda.
- **Keyword backend**: leggibili solo se l'account ha accesso alla scheda (codice vendor e SKU).

Il pulsante **Verifica accesso Amazon** in Catalogo mostra cosa è disponibile per ogni account.

## Modifiche e ripristini del catalogo

- **Contenuti A+**: confrontiamo solo il numero di moduli, quindi le modifiche all'interno di un modulo non vengono rilevate. Li rileviamo e li mostriamo, ma il ripristino è sempre a mano su Seller Central o Vendor Central.
- **Modelli NIS ufficiali di Amazon**: non ancora supportati. I nuovi articoli si validano sul tipo di prodotto Amazon (attributi obbligatori e verifica di Amazon).
- **Immagini**: si sostituiscono dall'aggiornamento massivo tramite URL, ma sugli account Vendor le rimozioni vanno fatte a mano su Vendor Central.
- **Account senza accesso in scrittura** (per esempio Vendor senza codice vendor o SKU): le modifiche approvate escono come file da caricare a mano su Vendor Central.
- **Notifiche di Amazon**: non le usiamo. Il catalogo si controlla con una scansione giornaliera, quindi una modifica può essere segnalata fino al giorno dopo.

## Le funzioni di intelligenza artificiale

Alcune parti della piattaforma sono generate da un servizio esterno di intelligenza artificiale, che funziona a **crediti**:

- le raccomandazioni strategiche;
- l'analisi di mercato;
- i testi discorsivi dell'analisi di marca.

Quando i crediti finiscono, **solo queste sezioni** smettono di produrre contenuti nuovi. Continui a vedere quelli già generati, ma non se ne aggiungono.

Tutto il resto — vendite, ordini, campagne, catalogo, esportazioni — continua a funzionare normalmente. Se noti che solo queste tre sezioni si sono fermate mentre i numeri si aggiornano, il sospetto giusto sono i crediti, non un guasto.

## Quanto storico è disponibile

Dipende dal tipo di account:

| Tipo di account | Storico vendite |
| --- | --- |
| Seller Central | fino a **24 mesi** |
| Vendor Central | oltre i 24 mesi |

Il tetto dei 24 mesi sugli account Seller è imposto da Amazon: più indietro di così i dati non vengono proprio consegnati. Gli account Vendor arrivano più lontano.

Tienilo presente quando prepari confronti anno su anno: su un account Seller collegato da poco, il periodo di confronto potrebbe non esistere.
