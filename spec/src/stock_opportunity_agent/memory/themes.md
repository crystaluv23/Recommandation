# Memory Themes

## Status
Started

## Purpose

Persist cold-start theme maps so industry-chain hypotheses become reusable
system memory rather than one-off report artifacts.

## External Interface

Initial implementation exposes `FileThemeLibrary`, a JSON-backed store for:

- persisted `ThemeMap` records,
- run id and creation timestamp.

## Invariants

- Theme maps must preserve stage scale version, segment stages, candidate
  symbols, validation state, leading indicators, risks, and crowdedness flags.
- Cold-start reports and theme memory are separate artifacts.
- Later theme edits should create new versions or append review history rather
  than silently erasing prior maps.

## Limits

The first store writes full JSON snapshots. Append-only event logs, segment
history indexes, and query filters should be added when scanner and review
consumers need them.
