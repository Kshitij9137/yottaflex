# Schema Design Prompts

This file preserves selected schema-design prompt text. The implementation notes are clearly separated from the prompts.

## Prompt 1

I need to generate synthetic workforce retention data for an AI assignment.

The required entities are:

- Employee
- Role
- Team
- TenureSnapshot
- EngagementSurvey
- WorkloadSnapshot
- CompensationBand
- PromotionHistory
- AttritionOutcome
- Intervention

Can you suggest relationships between these entities and identify which should be master tables, transactional tables, and event-history tables?

### Implementation note (not part of the prompt)



Used the suggested categorization as a starting point.

Modified the design to:
- keep promotion history as events
- track team changes historically
- add EmployeeTeamAssignment as a bridge table
- preserve history rather than overwrite records


## Prompt 2

What is the best way to represent workforce changes over time?

I want to preserve promotions, transfers, workload changes and interventions without modifying old records.

Compare:
1. Snapshot-based model
2. Event-sourcing model
3. Hybrid approach

Explain tradeoffs.


## Record limitation

The original tool name and date for each prompt were not recorded in this file. They are intentionally not inferred. This file is a selected prompt record, not a complete conversation transcript.
