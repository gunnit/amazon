# When an account shows an error

In the **Accounts** list every row shows its own status. When an error appears, below you will find what it means and what you should do. Find the message you are seeing and go to the matching section.

One important note: almost none of these errors delete data or disconnect the account. The data already collected stays where it is.

## Expired client secret

**What happened.** The Amazon application's client secret has passed its 180-day validity. Amazon refuses every request until it is renewed, so no new data arrives.

**What to do.** Regenerate the secret on Amazon and paste it into **Settings**. It is a five-minute procedure that disconnects nothing: it is explained step by step in [Renewing your Amazon client secret](secret-rotation).

## Missing application credentials

**What happened.** Inthezon does not have the Amazon application details it needs in order to connect. This usually happens on a new installation, or after a field has been emptied.

**What to do.** Open **Settings** from the left-hand menu and fill in the Amazon credential fields. Save and try again. If you do not know where those values come from, ask whoever created the application on Amazon.

## Invalid marketplace

**What happened.** The account type or the selected marketplace does not match what Amazon expects for that seller. The typical case: a **Vendor** account connected as a **Seller** (or the other way round), or a marketplace different from the one the seller actually operates in.

**What to do.** Check with the client which portal they log into (Seller Central or Vendor Central) and which marketplace they sell on. Then connect the account again, choosing the correct type and marketplace.

## Amazon refused access

**What happened.** The authorisation on Amazon did not go through: it was denied, it was interrupted halfway, or it was completed with an Amazon user who does not have the necessary permissions.

**What to do.** Redo the connection from the **Connect Amazon account** button and, on the Amazon screen, make sure you sign in with the right user and click all the way through the approval button.

## Amazon is throttling requests

**What happened.** Amazon caps how many requests can be made in a given time window. When the cap is reached — or when Amazon's systems are temporarily slow — some requests get rejected.

**What to do.** Nothing. This is a **temporary** condition: Inthezon retries on its own, automatically, spacing out the attempts. If the status is unchanged after a few hours, report it to support.

## Seller different from the expected one

**What happened.** The authorisation was completed with an Amazon seller different from the one already tied to that row. Inthezon **refused it on purpose** and changed nothing.

**What to do.** This is a safeguard, not a fault: it prevents two clients' data from getting mixed together. Sign out of Amazon or open a private browsing window, sign back in with the correct seller and repeat the connection.

## Missing advertising profile

**What happened.** The Amazon Ads connection is active, but no advertising profile has been chosen — or a profile from a different marketplace than the account's was chosen.

**What to do.** Go back into the Amazon Ads configuration and select the advertising profile **from the same marketplace** as the account (for example the Italy profile for an Italy account). Without that choice, campaign data cannot come through.

## The technical detail

Under many errors there is an expandable **Technical detail** entry, showing the original message received from Amazon.

That text is not meant for your daily work: it is there for whoever provides support. If you open a support request, expand it, copy it and paste it into your message along with the account name and the time you saw the error. It shortens diagnosis considerably.
