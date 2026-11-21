# Content protection

**Catalog > Content protection** compares each live product page with the **approved version** every day and flags anything that changed without authorisation.

## The approved version

This is the reference content to protect. You set it in two ways:

- **Approve current content as reference**: today's live content becomes the approved version, for all products. Variation families are saved too (see Variations).
- **Bulk update > Set as approved version**: upload an Excel file in the export format and it becomes the reference. Nothing changes on Amazon.

Both actions are for **administrators** only. Check that the live content really is the right one before approving: wherever it differs from the approved version so far, it replaces it.

## The daily comparison

With the nightly scan (05:00 UTC, or **Start scan**) the tool compares title, bullet points (text and order), description, images (replaced, missing, reordered), A+ content (missing or changed) and attributes. Prices, offers and stock are not compared.

Each difference becomes a change to review, with its type: **Modified**, **Removed**, **Added**, **Reordered**. The statuses are:

| Status | Meaning |
| --- | --- |
| To review | Detected, waiting for a decision |
| Acknowledged | Seen by an operator |
| Restore requested | A request already exists in Approvals |
| Resolved | The live content is the same as the approved version again |

A change closes on its own when the content matches again; a second one is not opened for the same difference.

## Side-by-side comparison

**Compare** opens the approved version on the left and the live one on the right. For texts the removed and new words are highlighted; for images the changed ones are marked.

## Accept or restore

- **Accept as new reference**: the change was intended, the live content becomes the approved version.
- **Restore**: puts the approved content back online. It does not change anything right away: it creates a request that goes through **Approvals** (see Bulk update and approvals). You can select several changes and restore them together.

**A+ content** cannot be restored through the APIs: restore it by hand on Seller Central or Vendor Central.

## History

**History** shows every version of a product's content, with the dates it was seen online and the differences from the previous version. A new version is recorded only when the content changes.
