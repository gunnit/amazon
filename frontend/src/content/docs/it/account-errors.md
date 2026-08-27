# Quando un account mostra un errore

Nell'elenco **Account** ogni riga mostra il proprio stato. Quando compare un errore, qui sotto trovi che cosa significa e che cosa devi fare. Trova il messaggio che vedi e vai alla sezione corrispondente.

Nota importante: quasi tutti questi errori **non** cancellano dati e **non** scollegano l'account. I dati già raccolti restano dove sono.

## Client secret scaduto

**Cosa è successo.** Il client secret dell'applicazione Amazon ha superato i 180 giorni di validità. Amazon rifiuta ogni richiesta finché non viene rinnovato, quindi non arrivano più dati nuovi.

**Cosa fare.** Rigenera il secret su Amazon e incollalo in **Impostazioni**. È una procedura di cinque minuti che non scollega niente: la trovi spiegata passo per passo nella pagina [Rinnovare il client secret Amazon](secret-rotation).

## Mancano le credenziali dell'applicazione

**Cosa è successo.** Inthezon non ha i dati dell'applicazione Amazon da usare per collegarsi. Di solito succede su un'installazione nuova, o dopo che un campo è stato svuotato.

**Cosa fare.** Apri **Impostazioni** dal menu a sinistra e compila i campi delle credenziali Amazon. Salva e riprova. Se non sai da dove prendere quei valori, chiedi a chi ha creato l'applicazione su Amazon.

## Mercato non valido

**Cosa è successo.** Il tipo di account o il mercato selezionato non corrisponde a ciò che Amazon si aspetta per quel venditore. Il caso tipico: un account **Vendor** collegato come **Seller** (o viceversa), oppure un mercato diverso da quello in cui il venditore opera davvero.

**Cosa fare.** Verifica con il cliente su quale portale accede (Seller Central o Vendor Central) e su quale marketplace vende. Poi rifai il collegamento dell'account scegliendo il tipo e il mercato corretti.

## Amazon ha rifiutato l'accesso

**Cosa è successo.** L'autorizzazione su Amazon non è andata a buon fine: è stata negata, è stata interrotta a metà, oppure è stata completata con un utente Amazon che non ha i permessi necessari.

**Cosa fare.** Rifai il collegamento dal pulsante **Collega account Amazon** e, nella schermata Amazon, assicurati di accedere con l'utente giusto e di cliccare fino in fondo sul pulsante di approvazione.

## Amazon sta limitando le chiamate

**Cosa è successo.** Amazon impone un tetto al numero di richieste per intervallo di tempo. Quando il tetto viene raggiunto — o quando i sistemi Amazon hanno un rallentamento temporaneo — alcune richieste vengono respinte.

**Cosa fare.** Nulla. È una condizione **passeggera**: Inthezon riprova da solo, in automatico, distanziando i tentativi. Se lo stato resta identico dopo qualche ora, segnalalo al supporto.

## Venditore diverso da quello atteso

**Cosa è successo.** L'autorizzazione è stata completata con un venditore Amazon diverso da quello già associato a quella riga. Inthezon l'ha **rifiutata di proposito** e non ha modificato nulla.

**Cosa fare.** È una protezione, non un guasto: serve a impedire che i dati di due clienti finiscano mescolati. Esci da Amazon o apri una finestra di navigazione privata, rientra con il venditore corretto e ripeti il collegamento.

## Manca il profilo pubblicitario

**Cosa è successo.** Il collegamento ad Amazon Ads è attivo, ma non è stato scelto quale profilo pubblicitario usare — oppure è stato scelto un profilo di un mercato diverso da quello dell'account.

**Cosa fare.** Rientra nella configurazione di Amazon Ads e seleziona il profilo pubblicitario **dello stesso mercato** dell'account (per esempio il profilo Italia per un account Italia). Senza questa scelta i dati delle campagne non possono arrivare.

## Il dettaglio tecnico

Sotto molti errori trovi una voce espandibile **Dettaglio tecnico**, che mostra il messaggio originale ricevuto da Amazon.

Quel testo non serve a te per lavorare: è pensato per chi fornisce assistenza. Se apri una segnalazione al supporto, aprilo, copialo e incollalo nel messaggio insieme al nome dell'account e all'ora in cui hai visto l'errore. Accorcia di molto i tempi di diagnosi.
