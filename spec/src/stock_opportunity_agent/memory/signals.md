# Memory Signals

## Status
Started

## Purpose

Persist the local signal library so cold-start outputs become reusable system
memory rather than one-off report artifacts.

## External Interface

Initial implementation exposes `FileSignalLibrary`, a JSON-backed store for:

- promoted `SignalDefinition` records,
- learned pre-surge signal logic,
- run id and creation timestamp.

## Invariants

- Signal definitions must preserve version, evidence, applicability, and
  false-positive patterns.
- Cold-start reports and signal memory are separate artifacts.
- Later signal edits should create new versions rather than silently mutating
  definitions.

## Limits

The first store writes full JSON snapshots. Append-only event logs, query
indexes, and performance histories should be added when review and
meta-learning consumers need them.
