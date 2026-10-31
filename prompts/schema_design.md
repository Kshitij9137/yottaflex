# Schema Design Prompts

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

### Outcome

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