# Email reports

Inthezon can email you periodic reports, a daily summary and alerts. For an email to actually arrive, **two conditions must both be true**. If one is missing, nothing goes out — and no obvious error appears.

Today **neither of the two is satisfied**. Here is what is missing and who has to do it.

## The two conditions

1. **The sending domain must be authenticated** with the service that delivers the emails. Today it is not, so no email leaves the platform.
2. **A schedule must exist**, saying which report to send, to whom and how often. Today none has been created.

They are independent: fixing only the first sends nothing, because there is nothing to send. Creating only the second delivers nothing, because sending is blocked.

## Condition 1: authenticating the sending domain

The service that delivers the emails only agrees to send on behalf of a domain once someone has proven they control it. Until that verification exists, every send attempt is rejected up front.

What this means in practice:

- It is done **once**. Once done, it holds for good (until the domain changes).
- It is done from the **email service's own dashboard**, not from Inthezon: there is no button inside the platform that unlocks it.
- It requires access to the **domain's DNS configuration**, meaning whoever manages the client's domain (usually internal IT or the provider that registered it).
- It is a client-side task. The agency alone, without that access, cannot complete it.

The exact steps are given by the email service's dashboard at verification time: it generates values to add to the DNS and then checks that they have been published. Follow those, not a procedure written from memory.

## What does not arrive while sending is blocked

Everything that travels by email is blocked, not just reports:

- scheduled reports;
- the daily summary;
- alerts (for example sales drops or competitor price changes);
- **password recovery**.

That last one deserves attention, and it is the most urgent reason to fix email delivery: if a user clicks "forgot password", the email never reaches them, and **there is currently no other way back in**. There is no feature that lets an administrator reset another user's password: whoever loses their password stays locked out until sending works again. While this is the case, keep credentials in a password manager and do not let access depend on a single person.

Alerts, in any case, keep being generated and stay visible in the **Alerts** section. They just do not reach you by email: you have to go in and look at them.

## Condition 2: creating a schedule

Even with sending working, Inthezon does not send anything on its own initiative. You have to tell it **what** to send, **to whom** and **when**: that is what we call a schedule.

Today none exists. So if the domain were authenticated tomorrow, the inbox would still stay empty until you create one.

When you create a schedule, you typically decide:

- the report type and the account (or accounts) it covers;
- the frequency, for example every Monday or the first of the month;
- the recipients.

## Downloading reports without email

Email is convenient, not mandatory. At any time you can generate and download reports from the platform, from the export screens:

- **Excel**, to work on the numbers or hand the client a table;
- **PowerPoint**, for the monthly presentation, already laid out;
- **PDF**, for a document to attach or print.

The file downloads to your computer and you forward it yourself with your usual mail client. This is the recommended way of working until both conditions above are satisfied.
