# Operator digest and action loop format

## Purpose

This note defines the local digest format for Self Ershov Memory artifacts and the action loop that follows it.
It is intentionally Telegram-friendly, but it does not send anything anywhere. It is just the render contract.

The digest must be generated entirely from local artifact data and run history:

- `manifest.json`
- `REPORT.md`
- `sources.jsonl`
- `proposals.jsonl`
- `audit.jsonl`
- `runs.jsonl`
- `ERSHOV.md`
- `state.json`

No remote state, no hidden cache, no second source of truth.

## Design goals

1. Make the current artifact obvious in one scan.
2. Put the highest-value decisions at the top.
3. Show what changed since the last memory run, not a wall of repeated history.
4. Make approve/reject commands copy-paste safe.
5. Keep weekly rollups useful, not ceremonial.
6. Stay readable on a phone.

## Digest shape

The digest is a single plain-text message with a fixed section order.
If it would exceed the transport limit, split at section boundaries, never mid-command.

### Section order

1. Header
2. Status snapshot
3. Priority-ranked proposals
4. What changed since last memory run
5. Action loop
6. Weekly rollup, only when requested or when the current artifact closes a week

### Header

Keep it short.

Example:

- `Self Ershov Memory digest`
- `Artifact: 20260527T221500Z-abc12345`
- `Status: staged | valid | 4 proposals | 2 approved | 1 rejected | 0 applied`
- `Priority: 87/100`

The header should expose only the facts an operator needs to decide whether to keep reading.

### Status snapshot

This section is the local equivalent of a report card summary.
Use the existing artifact model fields directly:

- artifact id
- created at
- provider
- status
- source count
- proposal count
- validation state
- apply state
- discard state
- target kind breakdown
- theme labels
- applied proposal ids
- backup file copies
- rollback evidence records
- created-file tombstones

Keep it to a few bullets, not a dump.

## Priority scoring

The digest needs a stable way to rank artifacts and proposals.
The score is not truth, it is a triage tool.
It should reward usefulness, urgency, and recurrence, while penalizing sludge.

### Artifact priority score

Score range: `0-100`

Recommended formula:

`artifact_priority = clamp(blocker + value + recurrence + freshness + readiness - noise, 0, 100)`

#### Components

`blocker` 0-40

- +40, validation errors or unsafe/conflicting proposals
- +25, unresolved approval state with at least one actionable proposal
- +20, artifact is ready to apply but not yet applied
- +0, already discarded or fully settled

`value` 0-30

- +30, at least one `user` proposal
- +22, at least one `skill` proposal
- +16, at least one `memory` proposal
- +10, at least one `fact` proposal
- +2, for each additional distinct target kind beyond the first, up to +6 total

`recurrence` 0-15

- +8, same theme appeared in the last memory run
- +7, same theme appears in 2+ source sessions or source snapshots

`freshness` 0-10

- +10, new proposal set or new evidence since the last memory run
- +5, mostly unchanged but with new audit state
- +0, pure repeat with no new signal

`readiness` 0-10

- +10, average confidence >= 0.90
- +7, average confidence >= 0.80
- +3, average confidence >= 0.70
- +0, below that

`noise` 0-20

- +10, missing provenance on a proposal
- +10, duplicate/conflicting proposal inside the artifact
- +5, rejected proposal with no reason
- +5, obvious slop theme with no operational value

### Proposal priority score

Inside an artifact, proposals are sorted by this score:

`proposal_score = target_kind_weight + confidence_weight + evidence_weight + recurrence_bonus - conflict_penalty`

#### Proposal weights

`target_kind_weight`

- `user`: 40
- `skill`: 30
- `memory`: 20
- `fact`: 10

`confidence_weight`

- `>= 0.90`: +20
- `0.80-0.89`: +15
- `0.70-0.79`: +8
- `< 0.70`: +0

`evidence_weight`

- +10, direct source quote or explicit marker
- +8, corroborated by 2+ source sessions or snapshots
- +5, supported by audit history or prior accepted memory run
- +0, weak or indirect evidence only

`recurrence_bonus`

- +10, recurring theme across multiple memory runs
- +5, recurring theme across multiple source sessions
- +0, one-off

`conflict_penalty`

- -25, duplicate target in the same artifact
- -20, contradicts a higher-confidence proposal
- -10, proposal is too broad or vague
- -5, low signal but still potentially useful

### Ranking rule

Order artifacts by `artifact_priority` descending.
Inside an artifact, order proposals by `proposal_score` descending.
If scores tie, prefer:

1. `user`
2. `skill`
3. `memory`
4. `fact`
5. higher confidence
6. newer evidence

## What changed since last memory run

This is the part that keeps the digest from becoming a rerun.
The section should compare the current artifact to the previous memory run, not to some abstract idea of progress.

### Definition of "last memory run"

Use the most recent successful run from `runs.jsonl`.
If the current artifact belongs to a chain of related runs, prefer the previous artifact with the same source bundle or source roots.
If no prior successful run exists, say so plainly and skip the delta block.

### Delta categories

Report only the deltas that matter:

- `new` — proposal or theme did not exist in the prior memory run
- `changed` — same proposal id, but summary, confidence, target, or proposed text changed
- `resolved` — proposal moved to approved, rejected, or applied
- `repeated` — same theme showed up again with new evidence
- `removed` — proposal existed before but is absent now
- `stalled` — nothing changed except audit churn

### Recommended format

Use a short bullet list like this:

- New: 2 user-facing proposals, 1 skill update
- Changed: proposal `p-04` confidence rose 0.78 -> 0.91
- Resolved: `p-02` rejected, reason recorded
- Repeated: review UX and live-root quoting showed up again
- Removed: none

### What not to do

Do not restate the whole artifact.
Do not repeat full proposal text in the delta section.
Do not hide the actual difference behind vague language like “some updates happened”.

## Action loop

This is the operational part.
The digest should end by telling the operator what to do next, with exact commands.

### Happy-path loop

1. Read the digest.
2. Approve or reject the proposals.
3. Re-run summarize to confirm the state counts changed.
4. Run diff.
5. Run validate.
6. Apply only after the artifact is approved and valid.
7. Finish with status.

### Command rules

Commands must be shell-safe and copy-pasteable.
Always quote artifact paths.
Always quote rejection reasons.

Examples:

- `ershov summarize '/tmp/self-ershov-memory/artifacts/20260527T221500Z-abc12345'`
- `ershov approve '/tmp/self-ershov-memory/artifacts/20260527T221500Z-abc12345' all`
- `ershov reject '/tmp/self-ershov-memory/artifacts/20260527T221500Z-abc12345' p-04 --reason "too broad"`
- `ershov diff '/tmp/self-ershov-memory/artifacts/20260527T221500Z-abc12345' --live-root '/tmp/live root'`
- `ershov validate '/tmp/self-ershov-memory/artifacts/20260527T221500Z-abc12345' --live-root '/tmp/live root'`
- `ershov apply '/tmp/self-ershov-memory/artifacts/20260527T221500Z-abc12345' --live-root '/tmp/live root' --backup-root '/tmp/backups'`

### Approval gate wording

When there are unreviewed proposals, the digest should say:

- `Next step: approve or reject proposals`

When everything is reviewed but not applied, it should say:

- `Next step: apply approved proposals`

When the artifact is already applied or discarded, it should say:

- `Next step: run status or compact`

## Weekly rollup

The weekly rollup is a separate summary, not part of every digest.
It should cover the last 7 days, or the current calendar week if the operator prefers that view.
Pick one definition and keep it consistent.

### Weekly rollup sections

1. Accepted themes
2. Rejected themes
3. Recurring themes
4. Decision patterns
5. Next-week watchlist

### Weekly rollup format

Example:

- Accepted themes:
  - review UX clarity, 4 wins, 1 apply-ready follow-up
  - live-root quoting safety, 2 wins
- Rejected themes:
  - broad refactors with weak provenance, 3 rejections
  - duplicate noise proposals, 2 rejections
- Recurring themes:
  - review ergonomics, 5 appearances
  - command safety, 4 appearances
- Decision patterns:
  - `user` and `skill` proposals are more likely to be approved than `fact` proposals
  - low-confidence duplicates get rejected fast
- Next-week watchlist:
  - proposal provenance
  - command quoting
  - state transition audit quality

### How to compute the rollup

Use run history and artifact audits:

- `runs.jsonl` for run outcomes and timestamps
- `ERSHOV.md` for the human-readable diary trail
- `audit.jsonl` for per-proposal state transitions
- `manifest.json` for proposal metadata

Count accepted/rejected/applied transitions by theme label.
Count recurring themes by repeated appearance across artifacts or source sessions.
Use examples, not a data dump.

## Suggested local implementation contract

A local renderer can build this digest without any network access.
It only needs to:

1. load the current artifact
2. load the previous successful run or artifact
3. score the artifact and proposals
4. compute deltas
5. render a flat text digest
6. optionally render a weekly rollup from the run ledger

That is the whole job.
If it needs more than that, the format is too clever.

## Non-goals

- No real Telegram API send in this task
- No external database
- No LLM-only scoring
- No hidden state outside the artifact/run ledger
- No giant wall of text that nobody will read

## Bottom line

The digest should act like a sharp operator brief, not a scrapbook.
It should tell Niko what matters, what changed, what to approve, what to reject, and what to do next.
If it doesn't help him decide in under a minute, it failed.
