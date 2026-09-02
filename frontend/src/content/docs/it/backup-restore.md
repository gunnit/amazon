# Backup e ripristino del database

Tutto quello che la piattaforma sa vive in un solo database Postgres su Render. Se lo perdi, la parte ricostruibile da Amazon è poca: le finestre delle API sono corte e alcune serie storiche non tornano più. Questa pagina dice cosa ti protegge oggi, fin dove arriva, e cosa fare quando serve davvero.

I dati qui sotto sono stati verificati sull'istanza di produzione il **01/09/2026**.

## Cosa c'è oggi

Il database è `inthezon-db`: Postgres 18, piano **Basic 256 MB**, disco **1 GB**, regione **Frankfurt**. Nessuna alta disponibilità e nessuna replica di lettura — c'è una sola copia in esecuzione.

La rete è chiusa: la lista di IP autorizzati è **vuota**, quindi il database non accetta connessioni da fuori Render. Ci si arriva solo dall'interno (un job una tantum sul servizio API) o dalla dashboard Render. È una buona impostazione: non allargarla per comodità.

La protezione vera è il **ripristino a un istante preciso** (point-in-time recovery). Render lo tiene attivo su questo piano e la finestra è di circa **7 giorni scorrevoli**. Al momento della verifica risultava disponibile a partire dal 25/08/2026.

**Sette giorni è tutta la rete di sicurezza.** Una cancellazione o una corruzione che nessuno nota entro una settimana non è più recuperabile. È il motivo per cui esiste il paragrafo sulle copie esterne.

## Ripristinare a un istante preciso

Si fa dalla dashboard Render, sul database → **Recovery**, scegliendo data e ora.

Due cose da sapere prima di premere il pulsante:

Il ripristino **non sovrascrive** il database esistente: Render ne crea uno nuovo. Quello vecchio resta lì finché non lo elimini, il che è una salvaguardia, ma significa anche che il lavoro non finisce con il ripristino.

Perché l'applicazione usi il database ripristinato devi aggiornare `DATABASE_URL` sul servizio `inthezon-api` con la nuova stringa di connessione e fare un nuovo deploy. Finché non lo fai, l'app continua a leggere e scrivere sul database vecchio.

Dopo il deploy, verifica in quest'ordine: `/health` risponde `ok`; la versione Alembic è quella attesa; il numero di tabelle e le righe delle tabelle grandi (`sales_data`, `orders`) sono coerenti con l'istante scelto.

Un avvertimento specifico di questa piattaforma: su un database ripristinato la variabile `ALLOW_DESTRUCTIVE_RETENTION` deve restare **non impostata**. I job di retention cancellano i dati più vecchi della finestra configurata, e su uno storico appena recuperato è esattamente il modo di perderlo una seconda volta.

## Copia esterna su richiesta

La finestra di 7 giorni non copre il caso "ce ne accorgiamo tardi", e non copre affatto il caso in cui si perda l'accesso al workspace Render. Per quello serve una copia che vive altrove.

L'esportazione dalla API di Render è risultata inaffidabile in prova: la richiesta viene accettata ma non produce alcun file. Il modo che funziona è `pg_dump` da un job una tantum sul servizio API, che gira dentro la rete di Render e quindi raggiunge il database senza aprire nulla verso l'esterno:

```python
import os, subprocess
url = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")
subprocess.run(["pg_dump", "-Fc", "-f", "/tmp/db.dump", url], check=True)
```

Misurato il 01/09/2026: **6,9 MB** in formato compresso, 140 tabelle, circa 40 secondi. Un file di queste dimensioni si conserva ovunque senza problemi.

Il ripristino di questo file si fa con `pg_restore` su un database vuoto. Vale la pena provarlo una volta in locale, quando non serve: una copia mai ripristinata è un'ipotesi, non un backup.

## Quello che non è ancora stato provato

Il ripristino a un istante preciso non è **mai stato eseguito** su questa istanza. La funzione risulta attiva e la finestra è presente, ma la prova completa — ripristinare, ripuntare l'API, verificare i dati — richiede di creare un'istanza temporanea a pagamento e va concordata.

Finché quella prova non è stata fatta, considera il ripristino una procedura documentata, non una procedura collaudata.
