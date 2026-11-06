# Welcome portal: IT security review

IT Security, reviewed after the discovery workshop. Synthetic example.

## Summary

The portal handles bank details, identity documents and, possibly, health and diversity information about people who are not yet employees. It is a likely target. The controls below are required before go-live.

## Required controls

1. **Bank and tax details.** The portal passes bank and tax details to payroll and does not store them.
2. **Identity documents.** Images of right to work documents are deleted from the portal 30 days after HR has checked the original. The portal records that the check was done, by whom and when.
3. **Sign-in.** Starters sign in with their personal email address and a one-time code. No passwords are stored.
4. **Sessions.** A session times out after 15 minutes without activity.
5. **Withdrawn offers.** Access ends on the day an offer is withdrawn.
6. **Location of data.** All personal data is stored in the United Kingdom or the European Economic Area.
7. **Accessibility.** Not a security control, but noted for completeness: the portal must meet WCAG 2.2 at level AA, in line with company policy.

## Open points

- HR has asked to keep copies of identity documents for audit. This conflicts with control 2 and needs a decision from the HR Director with legal advice.
