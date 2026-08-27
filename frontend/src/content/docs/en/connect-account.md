# Connecting an Amazon account

Connecting an Amazon account to Inthezon takes a few steps and **no code to copy**. You log in on Amazon, you approve, and you come back here.

## Seller Central or Vendor Central?

Before you start you need to know which type of account it is. This is the most important choice in the whole procedure: if you get it wrong, the connection succeeds but data syncing fails.

- **Seller Central**: the brand sells **directly to consumers** on Amazon. The brand manages prices, listings and shipping (on its own or through FBA). People working here talk about "orders", "buy box", "FBA inventory".
- **Vendor Central**: the brand **sells to Amazon**, and Amazon then resells to consumers. Purchase orders come in from Amazon. People working here talk about "POs", "purchase orders", "shipped COGS".

If you are not sure, ask the client which of the two portals they log into: the name they see when signing in is the answer.

## Connecting the account

1. Open **Accounts** from the left-hand menu.
2. Click the **Connect Amazon account** button.
3. Fill in the short form:
   - **Name**: what you want to call the account inside Inthezon. It is optional and only helps you recognise it in the list.
   - **Type**: Seller Central or Vendor Central (see above).
   - **Marketplace**: the country of the marketplace. It defaults to **Italy**; change it only if the account operates on another market.
4. Click **Continue on Amazon**.
5. Amazon opens. Log in and **approve** the requested access.
6. You are returned to Inthezon automatically. The connection is done and syncing starts on its own.

You are never asked for a code, a key or any value to paste by hand.

## The first historical load

Right after connecting, Inthezon starts downloading all the available history. It is not instant: it is a large amount of data and Amazon delivers it at a controlled pace, so the load can take a long time.

In the **Accounts** list, the **History** column shows the progress. You can close the page and come back later: the load keeps going on its own. In the meantime some screens may look empty or partial — that is normal, they fill up as data arrives.

## Use the right seller

When Amazon asks you to log in, sign in with **the correct seller account**. If your browser already has an Amazon session open with a different seller, you might approve with the wrong seller without noticing.

If you authorise with a seller different from the one already tied to that row, **Inthezon refuses the connection and changes nothing**. This is not a platform error: it is a deliberate safeguard that prevents the data of two different clients from being mixed together.

If it happens: sign out of Amazon (or open a private browsing window), sign back in with the right seller and repeat the procedure.

## Amazon Ads is a separate connection

Advertising data comes through a **separate** connection from the sales data one. They are two different authorisations, done one at a time.

While only one of the two is active, the account shows as **partially connected**. That is normal and not an error: it simply means the other connection is still missing. To get both sales and campaigns, complete both.

## The old manual method

You may come across guides or internal notes explaining how to generate a renewal code by hand and paste it into Inthezon. **That method is obsolete**: it was the previous way of working and should no longer be used for new connections. Use the **Connect Amazon account** button described above.
