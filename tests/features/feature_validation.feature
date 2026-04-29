Feature: AgentLoop full runtime path — integration validation
  These scenarios complement unit tests by exercising the complete
  harness stack with retry semantics, observability, and guardrail integration.

  # Use this feature for contracts that produce visible artifacts or combine
  # multiple layers: JSONL logging, guarded execution, and live retry behavior.
  # Do not move pure helper tests here.

  Scenario: Flaky tool is retried the exact configured number of times
    Given a flaky tool that fails twice then succeeds
    And an integration loop with max_retries 2
    When I run the integration loop
    Then the tool execute method was called 3 times
    And the loop returns a successful tool message

  Scenario: ToolCallLogger records every invocation as valid JSONL
    Given an integration loop with a ToolCallLogger and a simple tool
    When I run the logged integration loop
    Then the log file contains 1 line
    And the log line has required JSONL keys

  Scenario: Guardrail enforced inside ToolHandler propagates as UserFixableError
    Given a tool that enforces a PathGuardrail on its input path
    When I run the guarded integration loop with a blocked path
    Then the guarded loop raises UserFixableError
