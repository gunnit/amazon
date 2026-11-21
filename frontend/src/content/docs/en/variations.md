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

**Restore family** reattaches the detached variations to the parent. It changes nothing right away: it creates requests that go through **Approvals**, checked by Amazon first. If a restore is already queued, the page says so.

To reattach a variation you need the child's SKU and the parent's SKU. When they are missing (common on Vendor accounts), the request becomes **file only**: it goes into the file for Vendor Central, to upload by hand. If only the parent SKU is missing, the request has to be completed by hand and is left out of the file.
