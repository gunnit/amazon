# Renewing your Amazon client secret

Every 180 days Amazon forces you to regenerate the **client secret** of the application connected to your account. This is an Amazon rule, not an Inthezon choice, and it cannot be turned off.

When the deadline passes, Amazon stops accepting requests from Inthezon. The platform stays up and keeps showing the data already collected, but no new data arrives: sales, orders and campaigns stay frozen on the expiry date.

It has already happened on this installation: the secret expired on **11/08/2026** and stayed expired for 16 days before anyone noticed. The chart simply looked flat.

## No account gets disconnected

This is the most common fear, and the answer is no.

- Connected Amazon accounts **stay connected**.
- The authorisations granted on Amazon **stay valid**.
- You do **not** need to reconnect anything, you do **not** need to re-authorise anything, you do **not** need to log in to Amazon again.
- The historical data already collected **is not lost**.

The only thing that changes is one string pasted into one field. Nothing else.

And there is even more room than that: once you generate the new secret, **the old one keeps working for another 7 days**. So you can generate the new secret in the morning and paste it into Inthezon in the afternoon, or the next day, without interrupting anything.

## How to renew it, step by step

You need five minutes and access to Amazon with the user who created the application (usually the account administrator). If you sign in with a different user, the menu entry may not appear.

1. Sign in to **Seller Central** or **Vendor Central**, depending on the account type.
2. At the top, open the **Apps and Services** menu and choose **Develop Apps**.
3. In the list that appears, find the application used for Inthezon.
4. On that application's row, open the actions menu and choose **Rotate secret**.
5. Amazon shows the new client secret. **Copy it right away**: it is shown **only once** and cannot be retrieved again. If you close the window without copying it, you have to regenerate it from scratch.
6. Go back to Inthezon and open **Settings** from the left-hand menu.
7. Find the **SP-API Client Secret** field, paste the value you just copied and save.

Done. Syncing restarts on its own, with nothing to restart manually. Updated data comes back shortly afterwards.

If the error is still there after saving, suspect number one is an imperfect copy-paste: a space before or after the value, or part of the string left unselected. Copy and paste it again, taking the whole string.

## Checking how many days have passed

In **Settings**, next to the client secret field, you can see how **many days** ago the current secret was entered. Past **120 days** a warning appears: that is the moment to plan the renewal calmly, well before the deadline.

Read that number carefully: the count starts from **when the secret was saved in Inthezon**, not from when Amazon issued it. If the secret had already been created a few weeks before it was pasted here, its real age is greater than the one shown. When in doubt, treat the number as an optimistic estimate and renew earlier.

A practical tip: put a calendar reminder at **150 days** from the entry date. The renewal takes five minutes when you do it early, and costs you days of missing data when you notice it late.
