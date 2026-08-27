# Report via e-mail

Inthezon può inviare per e-mail report periodici, un riepilogo giornaliero e gli avvisi. Perché un'e-mail arrivi davvero devono essere **vere due condizioni insieme**. Se ne manca una, non parte niente — e non compare nessun errore evidente.

Oggi **non è soddisfatta nessuna delle due**. Ecco cosa manca e a chi tocca farlo.

## Le due condizioni

1. **Il dominio di invio deve essere autenticato** presso il servizio che spedisce le e-mail. Oggi non lo è, quindi nessuna e-mail esce dalla piattaforma.
2. **Deve esistere una programmazione** che dica quale report inviare, a chi e con quale frequenza. Oggi non ne è stata creata nessuna.

Sono indipendenti: sistemare solo la prima non fa partire nulla, perché non c'è niente da inviare. Creare solo la seconda non fa arrivare nulla, perché l'invio è bloccato.

## Condizione 1: autenticare il dominio di invio

Il servizio che spedisce le e-mail accetta di inviare per conto di un dominio solo dopo che qualcuno ha dimostrato di controllarlo. Finché questa verifica non c'è, ogni tentativo di invio viene respinto in partenza.

Cosa comporta, in pratica:

- Si fa **una volta sola**. Fatta quella, vale per sempre (finché il dominio non cambia).
- Si fa dal **pannello del servizio di posta**, non da Inthezon: dentro la piattaforma non c'è nessun pulsante che la sblocchi.
- Richiede l'accesso alla **configurazione DNS del dominio**, cioè a chi gestisce il dominio del cliente (di solito l'IT interno o il fornitore che ha registrato il dominio).
- È un'operazione lato cliente. L'agenzia da sola, senza quell'accesso, non può completarla.

I passaggi esatti li indica il pannello del servizio di posta al momento della verifica: genera dei valori da inserire nel DNS e poi controlla che siano stati pubblicati. Segui quelli, non una procedura scritta a memoria.

## Cosa non arriva finché l'invio è fermo

Tutto ciò che viaggia via e-mail è bloccato, non solo i report:

- i report programmati;
- il riepilogo giornaliero;
- gli avvisi (per esempio i cali di vendita o le variazioni di prezzo dei concorrenti);
- il **recupero password**.

Quest'ultimo merita attenzione ed è il motivo più urgente per sistemare l'invio: se un utente clicca "password dimenticata", l'e-mail non gli arriva, e **oggi non esiste un altro modo per rientrare**. Non c'è una funzione con cui un amministratore possa reimpostare la password di un altro utente: chi perde la password resta bloccato fuori finché l'invio non riparte. Finché la situazione è questa, conserva le credenziali in un gestore di password e non lasciare che l'accesso dipenda da una sola persona.

Gli avvisi, comunque, continuano a essere generati e restano visibili nella sezione **Avvisi**. Semplicemente non ti raggiungono via e-mail: devi entrare a guardarli.

## Condizione 2: creare una programmazione

Anche con l'invio funzionante, Inthezon non manda niente di propria iniziativa. Devi dirgli **cosa** inviare, **a chi** e **quando**: è quello che chiamiamo programmazione.

Oggi non ne esiste nessuna. Quindi, se domani il dominio venisse autenticato, la casella resterebbe comunque vuota finché non ne crei una.

Quando crei una programmazione, decidi tipicamente:

- il tipo di report e l'account (o gli account) a cui si riferisce;
- la frequenza, per esempio ogni lunedì o il primo del mese;
- i destinatari.

## Scaricare i report senza e-mail

L'e-mail è comoda, non obbligatoria. In qualsiasi momento puoi generare e scaricare i report dalla piattaforma, dalle schermate di esportazione:

- **Excel**, per lavorare i numeri o rigirarli al cliente in forma di tabella;
- **PowerPoint**, per la presentazione mensile già impaginata;
- **PDF**, per un documento da allegare o stampare.

Il file si scarica sul tuo computer e lo inoltri tu con la tua posta abituale. È il modo di lavorare consigliato finché le due condizioni qui sopra non sono entrambe soddisfatte.
