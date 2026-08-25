# Changelog

## 0.1.4 - 2026-08-25
- Classify operations by vertical name when scopes carry the numeric API code, so
  `200.invoices.r` no longer creates a `200` command group. Write commands move back
  under their vertical: `chift accounting invoices create`, not `chift 200 invoices create`.
- Give the datalab endpoints their own group instead of filing them under whichever
  vertical sorted first.
- Name every vertical after its spelled-out form, the way `pos` already became
  `point-of-sale`. `chift pms …` is now `chift property-management-system …` and
  `chift commerce …` is now `chift e-commerce …`.

## 0.1.3 - 2026-06-01
- Add support for datalayer

## 0.1.2 - 2026-05-29
- General fixes
- Support windows as well

## 0.1.1 - 2026-05-28
- Initial release