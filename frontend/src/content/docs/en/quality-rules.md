# Listing quality and rules

In **Catalog > Listing quality** each product has a traffic light for each of the 11 listing elements, plus an overall one. The worst cases are at the top: click a row to see the detail and the reason for each colour.

## The 11 elements

Title, Item highlights, Bullet points, Description, Images, Main image, Video, A+ Content, Backend keywords, Attributes, Category. The default thresholds are the ones agreed with the client (title at most 75 characters, 5 bullets, 8 images, backend keywords under 250 bytes, and so on) and can be changed from the **Rules** tab.

## What the colours mean

| Colour | Meaning |
| --- | --- |
| Green | Compliant and optimised |
| Yellow | Compliant but improvable |
| Red | Non-compliant or missing |
| Grey | Cannot be verified |

**Grey** is not a problem: it means Amazon does not let us check that element, and the tool prefers to say so rather than show a false green. It happens like this:

- **Video**: always grey, Amazon does not expose it.
- **Item highlights**: grey when Amazon does not return them for that listing.
- **Backend keywords**: grey when the account has no access to the listing (for example no vendor code or SKU).
- **A+ Content**, **Attributes**: grey if access to that API is not available.
- **Main image**: grey if the image cannot be downloaded or analysed. Promotional text on the image is never verified.

## Mandatory or best practice

Each rule is either **mandatory** or **best practice**. A single red on a mandatory rule makes the whole product red. A red or yellow on a best practice makes it yellow at most. The product is grey only when every element is grey. The 0-100 score counts mandatory rules double and ignores grey ones.

By default these are mandatory: title, bullet points, main image, attributes and category.

## Main keyword

Many checks (title, bullets, description) look for the product's **main keyword**. Set it from the product detail, or in Excel with the `main_keyword` column. If you do not set it, the tool uses the term that ASIN wins in Brand Analytics, when there is one. With no keyword at all, the keyword check is skipped and the detail says so. Traffic lights update at the next scan.

## Editing the rules

**Rules** tab. For each rule you can switch it on or off, make it mandatory or best practice, and change the thresholds. Choose the scope first:

- the whole organisation (defaults);
- one marketplace;
- one product type;
- marketplace and product type together.

The most specific rule always wins. «Restore the default value» goes back to the base values. **Only administrators can save the rules**; everyone else sees them read-only. Changes show in the traffic lights after the next scan.

## When traffic lights update

The tool scans on its own every night at 05:00 UTC, for all active accounts (Seller and Vendor). To do it right away on one account use **Start scan**; products never scanned do not appear until a scan has run. We do not use Amazon notifications: the nightly scan replaces them.

## Check Amazon access

The **Check Amazon access** button tries, for the account, each API the catalogue uses (Catalog, Listings read, Product types, A+ Content, Feeds) and shows what is available. Use it when you see many greys or an account that does not update.
