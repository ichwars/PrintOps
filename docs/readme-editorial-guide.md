# README Editorial Guide

## Purpose

The root README must explain what PrintOps provides today, how it relates to
BambuBuddy, and where the project is heading. It should help hobbyists,
print-farm operators, business users, and developers decide whether the project
fits their needs without requiring them to inspect the source tree first.

## Positioning

PrintOps is an independent fork of
[BambuBuddy](https://github.com/maziggy/bambuddy). It retains BambuBuddy's
printer-management foundation while evolving toward an operations platform that
connects printers with materials, procurement, costing, customers, orders, and
business documents.

The README must not present PrintOps as an official successor to BambuBuddy, a
Bambu Lab product, or a project endorsed by either party. It must also avoid
framing BambuBuddy as obsolete or inferior.

## Attribution

The opening section should thank [maziggy](https://github.com/maziggy) for the
idea, creativity, and sustained work behind BambuBuddy. The acknowledgement must
be warm and specific without becoming promotional or overly sentimental.

Approved wording:

> **PrintOps stands on the foundation created by
> [maziggy](https://github.com/maziggy). His idea, creativity, and sustained work
> turned Bambu printer management into a capable self-hosted platform with
> [BambuBuddy](https://github.com/maziggy/bambuddy). We are sincerely grateful
> for that foundation.**
>
> **PrintOps is an independent fork. It preserves BambuBuddy's proven
> printer-management core while pursuing a broader goal: connecting printing
> with materials, costing, customers, orders, and business documents in one
> coherent operations platform.**

## Audience and voice

The README addresses four audiences equally:

- Hobbyists who want local control and room to grow.
- Print-farm operators who need reliable printer and production workflows.
- Small businesses that need inventory and commercial processes around their
  printers.
- Developers and contributors who value an open, self-hosted codebase.

Use direct, plain English. Prefer verifiable statements over marketing claims.
Keep headings and lists easy to scan. Avoid exhaustive feature inventories that
will become stale quickly.

## Content structure

The root README should use this order:

1. Project logo, title, and the tagline "From printer control to complete
   3D-print operations."
2. Concise product summary.
3. BambuBuddy acknowledgement and project lineage.
4. A factual BambuBuddy versus PrintOps comparison.
5. Capabilities available today, grouped by workflow rather than page.
6. A separately labelled product direction and roadmap.
7. Docker-first quick start and a compact local-development section.
8. Project status and expectation setting.
9. Documentation, contribution, license, and independence statements.

## Comparison rules

The comparison should cover product purpose, code lineage, printer workflows,
business workflows, interface identity, best-fit users, and project direction.
It must distinguish focus rather than declare a winner.

Key distinction:

- BambuBuddy is a self-hosted command center focused on deep Bambu printer and
  farm management.
- PrintOps uses that foundation as the production core of a broader system for
  inventory, purchasing, costing, customer, order, and document workflows.

The README should explicitly say that PrintOps is more than a visual rebrand,
while recognizing BambuBuddy as a strong choice for users whose primary need is
printer control and automation.

## Product truthfulness

The README must separate current capability from future direction:

- "Available today" contains only shipped behavior present in the repository.
- "Where PrintOps is going" contains planned product outcomes.
- Planned electronic invoicing, complete document lifecycles, deeper production
  planning, and expanded reporting must not be described as finished features.
- Version-sensitive claims should link to maintained documentation where
  possible.

## Validation

Before merging a README update:

- Verify every repository-relative link and image target.
- Confirm that current-versus-planned wording matches the product state.
- Check that BambuBuddy and maziggy links resolve to the intended GitHub pages.
- Confirm that no wording implies affiliation with or endorsement by Bambu Lab.
- Review the rendered table and headings for GitHub readability.
