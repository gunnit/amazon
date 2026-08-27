# Gestire gli utenti

Ogni persona che usa Inthezon deve avere il **proprio** accesso. Non è una formalità: è l'unico modo per sapere chi ha fatto cosa e per togliere l'accesso a chi lascia l'agenzia senza costringere tutti gli altri a cambiare password.

Non ci si registra da soli. **Un amministratore crea l'utente dall'interno della piattaforma**, in *Impostazioni → Utenti*, e la persona entra nell'organizzazione già esistente — non in una nuova.

## Come si aggiunge una persona

1. Vai in **Impostazioni → Utenti** e aggiungi la persona indicando e-mail, nome e ruolo.
2. La piattaforma genera un **link**. Copialo.
3. **Mandaglielo tu**: WhatsApp, chat, e-mail dalla tua casella. Come preferisci.
4. La persona apre il link, sceglie la propria password ed entra.

Il link vale **7 giorni** e smette di funzionare nel momento in cui viene usato. Se scade o va perso, ne generi un altro dalla stessa schermata: non succede niente di male, il vecchio semplicemente muore.

Finché non apre quel link, l'utente esiste ma non può entrare: nessuna password è stata scelta per lui.

## Perché il link va mandato a mano

Perché la piattaforma **non riesce a spedire e-mail**: manca l'autenticazione del dominio di invio, un passaggio che spetta al cliente (lo trovi spiegato in *Report via e-mail*).

Quindi la piattaforma fa la parte che le compete — creare l'utente e produrre un link sicuro — e lascia a te la consegna. Quando l'invio delle e-mail verrà sbloccato, questa stessa schermata potrà spedire il link da sola, senza che cambi nulla di come funziona.

C'è comunque un vantaggio che resta anche dopo: **nessun amministratore conosce mai la password di nessuno**. Non c'è una password provvisoria da comunicare e poi da ricordarsi di cambiare. Ognuno sceglie la propria e nessun altro la vede.

## Chi ha dimenticato la password

Stessa schermata, stesso meccanismo. In *Impostazioni → Utenti*, sulla riga della persona, generi un nuovo link e glielo mandi. Lei sceglie una password nuova e rientra.

È il sostituto del "password dimenticata" via e-mail, che oggi non funziona. Significa che **nessuno resta chiuso fuori**, a patto che in agenzia ci siano almeno due amministratori.

## I due ruoli

**Amministratore** — usa la piattaforma e in più può gestire gli utenti e le credenziali delle API Amazon. È il ruolo di chi tiene in piedi lo strumento.

**Membro** — accesso completo a dati, analisi, report ed esportazioni. Non può aggiungere o rimuovere utenti, né toccare le credenziali Amazon.

Tieni **almeno due amministratori**. Con uno solo, se quella persona perde la password o è in ferie, non c'è nessuno che possa generarle un link nuovo, e si rientra soltanto intervenendo sul database.

Per la stessa ragione non puoi cambiare il ruolo o disattivare **te stesso**: è la garanzia che un'organizzazione non possa restare senza amministratori.

## Quando qualcuno lascia l'agenzia

**Disattivalo**, non cancellarlo. Un utente disattivato non può più entrare e nessun link generato in precedenza funziona più, ma resta traccia di lui nello storico. Se un domani rientra, lo riattivi.

Trovi il comando sulla sua riga in *Impostazioni → Utenti*.

## Una sola organizzazione

Tutti i dati — account Amazon, vendite, campagne, concorrenti — appartengono all'**organizzazione**, non alla singola persona. Chi entra tramite il link entra in quella organizzazione e vede quei dati.

Non esiste un modo, dall'interno della piattaforma, di creare una seconda organizzazione: sarebbe un contenitore vuoto e la persona che ci finisce dentro non vedrebbe più niente. Se un giorno servisse davvero — perché entra un cliente diverso, con i suoi account Amazon — è un intervento di configurazione da chiedere a chi mantiene la piattaforma.
