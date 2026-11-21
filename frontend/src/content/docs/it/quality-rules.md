# Qualità listing e regole

In **Catalogo > Qualità listing** ogni prodotto ha un semaforo per ognuno degli 11 elementi della scheda e un semaforo complessivo. I casi peggiori sono in alto: clicca una riga per vedere il dettaglio e il motivo di ogni colore.

## Gli 11 elementi

Titolo, Item highlights, Bullet point, Descrizione, Immagini, Immagine principale, Video, Contenuti A+, Keyword backend, Attributi, Categoria. Le soglie predefinite sono quelle concordate con il cliente (titolo al massimo 75 caratteri, 5 bullet, 8 immagini, keyword backend sotto i 250 byte, e così via) e si cambiano dalla scheda **Regole**.

## Cosa significano i colori

| Colore | Significato |
| --- | --- |
| Verde | Conforme e ottimizzato |
| Giallo | Conforme ma migliorabile |
| Rosso | Non conforme o mancante |
| Grigio | Non verificabile |

Il **grigio** non è un problema: vuol dire che Amazon non ci permette di controllare quell'elemento, e il tool preferisce dirlo piuttosto che mostrare un falso verde. Succede così:

- **Video**: sempre grigio, Amazon non lo espone.
- **Item highlights**: grigio quando Amazon non li restituisce per quella scheda.
- **Keyword backend**: grigie quando l'account non ha accesso alla scheda (per esempio manca il codice vendor o lo SKU).
- **Contenuti A+**, **Attributi**: grigi se l'accesso a quella API non è disponibile.
- **Immagine principale**: grigia se l'immagine non si riesce a scaricare o analizzare. Il testo promozionale sull'immagine non viene mai verificato.

## Obbligatorio o best practice

Ogni regola è **obbligatoria** oppure **best practice**. Un solo rosso su una regola obbligatoria rende rosso l'intero prodotto. Un rosso o un giallo su una best practice lo rende al massimo giallo. Il prodotto è grigio solo se tutti gli elementi sono grigi. Il punteggio da 0 a 100 conta le regole obbligatorie il doppio e ignora quelle grigie.

Di base sono obbligatorie: titolo, bullet point, immagine principale, attributi e categoria.

## Keyword principale

Molti controlli (titolo, bullet, descrizione) cercano la **keyword principale** del prodotto. La imposti dal dettaglio del prodotto, oppure in Excel con la colonna `main_keyword`. Se non la imposti, il tool usa il termine che quell'ASIN vince in Brand Analytics, se c'è. Se non c'è nessuna keyword, il controllo sulla keyword viene saltato e il dettaglio lo dice. I semafori si aggiornano alla scansione successiva.

## Modificare le regole

Scheda **Regole**. Per ogni regola puoi attivarla o disattivarla, renderla obbligatoria o best practice e cambiare le soglie. Scegli prima l'ambito:

- tutta l'organizzazione (valori predefiniti);
- un marketplace;
- un tipo di prodotto;
- marketplace e tipo di prodotto insieme.

Vince sempre la regola più specifica. Con «Ripristina il valore predefinito» torni ai valori di base. **Solo gli amministratori possono salvare le regole**; gli altri le vedono in sola lettura. Le modifiche si vedono nei semafori dopo la prossima scansione.

## Quando si aggiornano i semafori

Il tool scansiona da solo ogni notte, alle 05:00 UTC, tutti gli account attivi (Seller e Vendor). Per farlo subito su un account usa **Avvia scansione**; i prodotti mai scansionati non compaiono finché non è stata fatta una scansione. Non usiamo le notifiche di Amazon: la scansione notturna le sostituisce.

## Verifica accesso Amazon

Il pulsante **Verifica accesso Amazon** prova, per l'account, ogni API usata dal catalogo (Catalogo, Schede in lettura, Tipi di prodotto, Contenuti A+, Feed) e mostra cosa è disponibile. Usalo quando vedi molti grigi o un account che non si aggiorna.
