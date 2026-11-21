# Variations

**Catalog > Variations** protects variation families (a parent and its children, for example the sizes and colours of the same product).

## How a family is recorded

Each family's original structure (parent, variation theme, list of children) is saved when you approve the current content as reference (see Content protection). Until you do, the page is empty. Every night the scan compares the live family with the recorded one.

## Family status

| Status | Meaning |
| --- | --- |
| Intact | All children are attached to the parent |
| Variations out of the family | Some children are detached, or there is an extra one |
| Family broken | The parent no longer holds the family together |

And for each child:

- **Attached**: fine.
- **Detached**: it was in the family, now it is not.
- **Unexpected**: it appeared in the family but was not in the approved version.
- **Not read yet**: the scan has not checked it yet.

A change of the variation theme is flagged too.

## Restoring a family

**Restore family** reattaches the detached variations to the parent. It changes nothing right away: it creates requests that go through **Approvals**; those sent to Amazon through the API are checked by Amazon first. If a restore is already queued, the page says so.

To reattach a variation you need the child's SKU and the parent's SKU. A request enters the Vendor Central file only if **both** are known. If either is missing (common on Vendor accounts), the request is left out of the file and has to be completed by hand. File-only requests are not checked by Amazon before approval: Vendor Central checks the file when you upload it.
