# Managing users

Everyone who uses Inthezon needs **their own** login. That is not a formality: it is the only way to know who did what, and to cut off access for someone who leaves the agency without making everyone else change their password.

Nobody signs themselves up. **An administrator creates the user from inside the platform**, in *Settings → Users*, and the person joins the organization that already exists — not a new one.

## Adding someone

1. Go to **Settings → Users** and add the person with their email, name and role.
2. The platform generates a **link**. Copy it.
3. **Send it yourself**: WhatsApp, chat, an email from your own inbox. Whatever you prefer.
4. They open the link, choose their own password, and they are in.

The link is valid for **7 days** and stops working the moment it is used. If it expires or gets lost, generate another one from the same screen — nothing bad happens, the old one simply dies.

Until they open that link the user exists but cannot log in: no password was ever chosen for them.

## Why the link is delivered by hand

Because the platform **cannot send email**: the sending domain has not been authenticated, and that step is the client's to take (it is explained in *Email reports*).

So the platform does its part — creating the user and producing a secure link — and leaves delivery to you. Once email sending is unblocked, this same screen will be able to send the link on its own, with nothing else about it changing.

There is an upside that survives either way: **no administrator ever learns anyone's password**. There is no temporary password to pass along and then remember to change. Everyone picks their own, and nobody else sees it.

## Someone forgot their password

Same screen, same mechanism. In *Settings → Users*, on that person's row, generate a new link and send it to them. They choose a new password and get back in.

It replaces the emailed "forgot password" flow, which does not work today. It means **nobody gets locked out**, as long as the agency keeps at least two administrators.

## The two roles

**Administrator** — uses the platform, and on top of that can manage users and the Amazon API credentials. This is the role for whoever keeps the tool running.

**Member** — full access to data, analysis, reports and exports. Cannot add or remove users, and cannot touch the Amazon credentials.

Keep **at least two administrators**. With only one, if that person loses their password or is on holiday, there is nobody left who can generate them a new link, and getting back in means going into the database.

For the same reason you cannot change the role of, or deactivate, **yourself**: that is what guarantees an organization can never end up with no administrators.

## When someone leaves the agency

**Deactivate them**, do not delete them. A deactivated user can no longer log in and any link issued to them earlier stops working, but their history stays intact. If they come back one day, reactivate them.

The control is on their row in *Settings → Users*.

## One organization

All the data — Amazon accounts, sales, campaigns, competitors — belongs to the **organization**, not to any one person. Someone who joins through the link joins that organization and sees that data.

There is no way, from inside the platform, to create a second organization: it would be an empty container, and whoever landed in it would see nothing at all. If one is ever genuinely needed — because a different client comes on board with their own Amazon accounts — that is a configuration change to request from whoever maintains the platform.
