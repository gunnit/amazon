# Rinnovare il client secret Amazon

Ogni 180 giorni Amazon obbliga a rigenerare il **client secret** dell'applicazione collegata al tuo account. È una regola di Amazon, non una scelta di Inthezon, e non si può disattivare.

Quando la scadenza arriva, Amazon smette di accettare le richieste di Inthezon. La piattaforma resta accesa e continua a mostrare i dati già raccolti, ma non ne arrivano di nuovi: vendite, ordini e campagne restano fermi al giorno della scadenza.

In questa installazione è già successo: il secret è scaduto l'**11/08/2026** ed è rimasto scaduto per 16 giorni prima che qualcuno se ne accorgesse. Il grafico sembrava semplicemente piatto.

## Nessun account viene scollegato

Questa è la paura più comune, e la risposta è no.

- Gli account Amazon collegati **restano collegati**.
- Le autorizzazioni date ad Amazon **restano valide**.
- **Non** devi ricollegare nulla, **non** devi riautorizzare nulla, **non** devi rifare il login su Amazon.
- I dati storici già raccolti **non si perdono**.

L'unica cosa che cambia è una stringa da incollare in un campo. Nient'altro.

E c'è ancora più margine: quando generi il nuovo secret, **quello vecchio continua a funzionare per altri 7 giorni**. Quindi puoi generare il nuovo secret la mattina e incollarlo in Inthezon nel pomeriggio, o il giorno dopo, senza interrompere niente.

## Come rinnovarlo, passo per passo

Ti servono cinque minuti e l'accesso ad Amazon con l'utente che ha creato l'applicazione (di solito l'amministratore dell'account). Se accedi con un altro utente, la voce del menu potrebbe non comparire.

1. Entra in **Seller Central** o in **Vendor Central**, a seconda del tipo di account.
2. In alto, apri il menu **App e servizi** e scegli **Develop Apps**.
3. Nell'elenco che compare, individua l'applicazione usata per Inthezon.
4. Sulla riga dell'applicazione apri il menu delle azioni e scegli **Rotate secret** (rigenera il secret).
5. Amazon mostra il nuovo client secret. **Copialo subito**: viene mostrato **una volta sola** e non è più recuperabile. Se chiudi la finestra senza copiarlo, devi rigenerarlo da capo.
6. Torna in Inthezon e apri **Impostazioni** dal menu a sinistra.
7. Trova il campo **SP-API Client Secret**, incolla il valore appena copiato e salva.

Fatto. La sincronizzazione riparte da sola, senza bisogno di riavviare niente. Nel giro di poco vedrai tornare i dati aggiornati.

Se dopo il salvataggio l'errore resta, il sospetto numero uno è un copia-incolla imperfetto: uno spazio davanti o dietro, o una parte della stringa non selezionata. Rifai il copia-incolla prendendo l'intera stringa.

## Controllare quanti giorni sono passati

In **Impostazioni**, accanto al campo del client secret, trovi da **quanti giorni** il secret attuale è stato inserito. Superati i **120 giorni** compare un avviso: è il momento di programmare il rinnovo con calma, molto prima della scadenza.

Attenzione a come va letto quel numero: il conteggio parte da **quando il secret è stato salvato in Inthezon**, non da quando Amazon lo ha generato. Se il secret era già stato creato qualche settimana prima di essere incollato qui, l'età reale è maggiore di quella mostrata. In caso di dubbio, considera il numero come una stima ottimistica e rinnova prima.

Un consiglio pratico: metti un promemoria in calendario a **150 giorni** dalla data di inserimento. Il rinnovo dura cinque minuti se lo fai in anticipo, e ti costa giorni di dati mancanti se te ne accorgi dopo.
