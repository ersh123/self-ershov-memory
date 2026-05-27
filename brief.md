# Hermes Dreaming — Project Brief

## Goal
Build a safe, reviewable self-improvement engine for Hermes-style memory,
user, skill, and fact updates. The MVP must support writeback, but only
through an explicit apply step after a staged proposal is reviewed.

## Approved contract
- Read recent sessions and durable context
- Produce a staged dream artifact with proposed changes and provenance
- Allow explicit apply/discard
- Apply approved changes to live memory, user, skills, and fact-store targets
- Verify the resulting state after writeback

## Non-goals for v1
- Silent live mutation during analysis
- Hidden background writes without artifacts
- One-off environment failures becoming durable knowledge
- Repo secrets, tokens, or private operational data

## Overlap research
The upstream Hermes repo already has overlapping open work in flight. Keep this repo scoped as a standalone implementation of the contract, not a duplicate of upstream PR text. See `research/upstream-overlap.md` for the issue/PR list and notes.

## Success criteria
- Repo is buildable and testable locally
- Dream artifacts are deterministic enough to review
- The apply step is explicit and safe
- Tests prove discard/apply behavior and catch bad proposals
- No embarrassing leaked or incorrect repo content
