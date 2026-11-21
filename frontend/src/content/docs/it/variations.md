# Variazioni

**Catalogo > Variazioni** protegge le famiglie di varianti (parent e figli, per esempio le taglie e i colori di uno stesso prodotto).

## Come si registra una famiglia

La struttura originale di ogni famiglia (parent, tema di variazione, elenco dei figli) si salva quando approvi i contenuti attuali come riferimento (vedi Protezione contenuti). Finché non lo fai, la pagina è vuota. Ogni notte la scansione confronta la famiglia online con quella registrata.

## Stato di una famiglia

| Stato | Significato |
| --- | --- |
| Integra | Tutti i figli sono collegati al parent |
| Varianti fuori famiglia | Alcuni figli sono staccati, o ce n'è qualcuno in più |
| Famiglia spezzata | Il parent non tiene più insieme la famiglia |

E per ogni figlio:

- **Collegata**: a posto.
- **Staccata**: era nella famiglia, ora non lo è più.
- **Non prevista**: è comparsa nella famiglia ma non era nella versione approvata.
- **Non ancora letta**: la scansione non l'ha ancora controllata.

Anche un cambio del tema di variazione viene segnalato.

## Ripristinare una famiglia

**Ripristina famiglia** ricollega al parent le varianti staccate. Non cambia nulla subito: crea richieste che passano da **Approvazioni**; quelle che vanno ad Amazon tramite API sono controllate prima da Amazon. Se un ripristino è già in coda, la pagina lo indica.

Per ricollegare una variante servono lo SKU del figlio e quello del parent. Entra nel file per Vendor Central solo se si conoscono **entrambi**. Se ne manca uno (succede spesso sugli account Vendor), la richiesta resta fuori dal file e va completata a mano. Le richieste solo file non sono controllate da Amazon prima dell'approvazione: il file lo controlla Vendor Central al caricamento.
