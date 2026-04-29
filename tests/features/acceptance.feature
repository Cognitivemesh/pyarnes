Feature: User acceptance — core workflows
  As a developer using pyarnes, I want to verify the key user-facing
  workflows work end-to-end so that I can trust the harness in production.

  # This feature owns behavior that reads naturally as a session story:
  # runtime wiring, lifecycle progression, and end-to-end tool execution.
  # Keep leaf helpers in unit tests; keep adopter-visible flows here.

  Scenario: Agent loop executes a tool and returns a final answer
    Given a registered echo tool and a model that calls it once
    When I run the agent loop
    Then the result contains the tool output and a final answer

  Scenario: Guardrails block a dangerous path
    Given a path guardrail with allowed root "/workspace"
    When I check a tool call with path "/etc/shadow"
    Then the guardrail raises a UserFixableError

  Scenario: Lifecycle tracks a full session
    Given a new lifecycle session
    When I start, pause, resume, and complete the session
    Then the lifecycle phase is "completed"
    And the history has 4 transitions

  Scenario: Evaluation suite scores scenarios correctly
    Given an eval suite with one correct and one incorrect scenario
    When I score the suite with exact match
    Then the pass rate is 0.5
    And the average score is 0.5

