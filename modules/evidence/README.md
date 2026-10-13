# scopesteps-evidence

Claims, evidence links, authorized retrieval and citation validation.

Today it holds citation validation: a reference is usable only if it resolves to an exact
stored passage of the project. A valid citation does not mean the passage supports the claim;
people judge that.

## Public interface

Other modules import only `scopesteps.evidence.client`: `EvidenceRef` (the API shape of a
pointer to a passage), `Citation` and `check_citations`. Everything else is internal and
enforced by import-linter.

## What is where

| Path                       | Contains                                                            |
| -------------------------- | ------------------------------------------------------------------- |
| `client.py`                | `EvidenceRef`, `check_citations` (reads passages through `sources`) |
| `domain/citation.py`       | A citation and the three ways it can be invalid                     |
| `application/citations.py` | The check itself, on passages already loaded                        |
| `infrastructure/`, `http/` | Empty until evidence links are stored and served on their own       |

`check_citations` reports a citation as invalid when its source version is not in the project
(another project's version looks exactly like a missing one), when its block is not a paragraph
of that version, or when its quote is not in the paragraph. A citation without a quote cites
the whole paragraph.

Tables will be prefixed `evidence_` (ADR 0003); the module owns none yet.
