# Bulk update and approvals

Nothing is ever written to Amazon without a person approving it. Every change (from Excel, a restore, a variation, a new item) becomes a **request** and waits in **Approvals**. Those sent to Amazon through the API are checked by Amazon first; file-only ones are not (see below).

## Export, edit, upload

In **Catalog > Bulk update**:

1. **Export catalogue**: the Excel file holds the current content (ASIN, SKU, product type, title, bullets 1-5, description, backend keywords, item highlights, main keyword, main image, images 1-8, parent, parent SKU, theme, plus `attr:name` columns for simple attributes). It is also the template to upload again.
2. Edit **only the cells to change**. An **empty cell keeps the current value**: there is no way to clear a field with the file. So a file that fills only `bullet_2` leaves the other bullets alone.
3. **Upload file** (.xlsx or .csv, 10 MB maximum) and choose how to use it.

Limits per row: title 200 characters, bullets 500, description 2000, item highlights 125, backend keywords 250 bytes; image URLs must start with `https://`. Rows over the limits are not used and are listed with the problem. Images are replaced position by position and none is deleted.

## Two ways to use a file

- **Update the product pages**: changed cells become requests. Amazon checks them right away, nothing is published.
- **Set as approved version**: the file becomes the reference for Content protection. Nothing changes on Amazon. Administrators only.

The `main_keyword` column updates the main keyword in the tool, not on Amazon.

## New items

In **New items** type the Amazon product type and download the **template**: it holds SKU, product type and the required attributes, then the recommended ones. Fill it in and upload it. Each row is checked against the product type's required attributes and then verified by Amazon, like everything else. Amazon's official NIS templates are not supported for now.

## The approval flow

**Approvals** collects the requests, by batch. For each one you see before and after, and the result of Amazon's check. The statuses:

| Status | Meaning |
| --- | --- |
| Being checked | Just created, Amazon has not checked it yet |
| Validated by Amazon | Check passed, ready for approval |
| Rejected by Amazon | The check found errors: fix and upload again |
| Approved | An administrator gave the go-ahead |
| Rejected | Discarded by an operator |
| Sent | Sent in a feed, being processed |
| Accepted by Amazon | Applied |
| Failed | Amazon refused it at sending: open the request for the detail |
| File only | Cannot go through the APIs (see below) |
| Uploaded by hand | Marked as uploaded to Vendor Central |

The **check** uses Amazon's trial mode (VALIDATION_PREVIEW): it publishes nothing. A request that has not been validated cannot be sent. File-only requests do not go through this check.

Who can do what: all operators upload files, create restores and **reject**. **Approving**, **sending to Amazon**, **refreshing the feed status**, **marking as uploaded by hand** and, in Content protection, **accepting a change as the new reference** are for **administrators** only. Before sending, the tool asks for confirmation and shows how many pages will change.

Under 50 requests each page goes out with a direct call; from 50 up, a single feed is sent, and its outcome is read with **Refresh feed status**.

## Vendor Central: file and manual upload

If an account has no write access to listings (no vendor code, or the SKU is missing), the requests are **file only**. After approval use **Download file for Vendor Central** (a JSON_LISTINGS_FEED file with only that batch's approved file-only requests: requests that go through the API never end up in the file), upload it by hand on Vendor Central, then press **Mark as uploaded by hand**: the requests move to "Uploaded by hand" and no longer count as to-do. Requests missing the SKU, the product type or the parent SKU stay out of the file and cannot be marked as uploaded. Amazon does not check them before approval: Vendor Central checks the file when you upload it.

## Images to remove

Uploading from Excel never removes images: positions are replaced one by one. Removals only come from **restoring** an approved version that has fewer images than the one online. On Vendor accounts Amazon does not allow deleting a value from a listing: the request lists them with **Remove these images by hand on Vendor Central**, the replacements go through and the removals have to be done by hand.
