# Stop-and-research rule

When the audit loop stalls — two consecutive fix rounds that don't move the
needle — stop grinding incremental patches. The rule is short on purpose: the
hard part is noticing you're stuck, not following the steps below.

## When it applies

You're running `ershov review` / `--execute` repeatedly, and each pass corrects
something only to break or re-find the same issue a step later. The artifact
diff stops converging.

It does **not** apply to a single failed command, a typo, or a one-off missing
flag. Those you just fix and move on. The threshold is *two rounds in a row
with no real progress*.

## What to do

1. **Re-read the root cause.** Not the symptom in the diff — the reason the
   engine keeps landing on the same correction. Re-open the source dialogue or
   the `MEMORY:` marker that produced the proposal. A correction that keeps
   re-firing is usually a sign the source itself is ambiguous or contradictory.

2. **Look at how other people solved this.** For anything upstream of your own
   config — a provider behaviour, a model quirk, a library version, someone
   else's Hermes plugin — search, dated to today, in roughly this order:
   GitHub issues / PRs and changelogs → Stack Overflow → Reddit / Discord →
   writeups. You're looking for a confirmed bug plus its fix, a known issue, a
   workaround, or an edge case somebody already hit. Read the date on the
   answer itself — a fix from two years ago may break on the version you run
   now.

3. **If it's your own logic** (your prompts, your memory layout, your cron
   schedule), the search is optional. Instead, compare against a similar setup
   you or someone else runs.

4. **Before you apply**, check the fix against your actual stack. Don't paste
   community advice in blind. Then run the staged workflow as usual — `review`,
   `diff`, `validate`, `apply` — and record what you changed.

## Why this is a rule at all

A stalled loop is cheap to keep spinning and feels productive, but it burns
provider calls and seeds memory with corrections that won't stick. Stepping
back for two minutes of research almost always costs less than round three.
