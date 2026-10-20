# 0016. License the code under the GNU AGPL v3

- Status: Accepted
- Date: 2026-10-19

## Context

The repository is moving from private to public. Without a license, public code stays "all rights
reserved": people can read it but not use, change or share it. ScopeSteps is a hosted web app, so
the license that matters is the one that applies when someone runs a modified copy as a service.

## Decision

- **The code is licensed under the GNU Affero General Public License v3.0 only**, with the full
  text in `LICENSE`.
- **Network use counts as distribution.** Anyone who offers a modified ScopeSteps to users over a
  network must offer those users the modified source, so a closed hosted fork is not allowed.
- **Contributions come in under the same license**, as `CONTRIBUTING.md` states.

## Consequences

- Others can study, run and improve ScopeSteps, and improvements to hosted copies stay open.
- Some companies do not use AGPL code at all, which limits adoption by them.
- Offering a commercial license on other terms would need every copyright holder to agree. If that
  becomes likely, add a contributor license agreement before accepting outside contributions.
- Revisit if the project needs a permissive license (Apache-2.0) for adoption, or a
  source-available license to protect a commercial offering.
