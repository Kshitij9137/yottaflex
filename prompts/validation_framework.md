# Validation Framework Prompt

## Retained prompt

Create a validation checklist for a synthetic relational dataset.

The checks should cover:

- primary-key uniqueness
- foreign-key integrity
- date ordering
- lifecycle transitions
- duplicate records
- allowed values
- reconciliation of derived values

## Repository implementation note

The project implements a schema-driven validation layer and documents its rules in the validation source and validation report. The full rule set includes key, relationship, domain, temporal, lifecycle, duplicate, and reconciliation checks, as well as detectors for the deliberately injected anomaly cases.

This section is an implementation note added for documentation clarity. It is not an original AI response and does not replace the validation report or test results.
