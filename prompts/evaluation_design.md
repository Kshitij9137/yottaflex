# Evaluation Design Prompts

This file preserves selected prompt text about evaluation design. Implementation notes are separated from the prompt records.

## Prompt 1 — Temporal evaluation

The assignment requires temporal evaluation.

Explain why a random train-test split would be misleading for workforce attrition prediction.

Suggest a temporal evaluation approach instead.

### Implementation note

The repository uses chronological cutoffs: earlier periods are used for training, and later periods are used for validation/testing to approximate prediction on future periods. This note describes the implementation; it is not part of the prompt text.

## Prompt 2 — Metrics for an imbalanced outcome

Which evaluation metrics are appropriate when voluntary attrition occurs in roughly 5–15% of the population?

Compare:
- Accuracy
- ROC-AUC
- Precision-Recall AUC
- Recall at top-k

### Implementation note

The project reports ranking and top-k metrics in addition to calibration-related measures. The model report should be consulted for the actual values and evaluation cutoffs. This note does not claim that any single metric establishes real-world validity.
