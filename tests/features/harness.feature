Feature: Agent harness error handling
  The harness routes tool failures through a four-error taxonomy
  so the agent loop stays running whenever possible.

  Scenario: Transient error triggers retry
    Given a tool that raises a transient error
    When the harness executes the tool
    Then the tool is retried up to the configured limit
    And the error is returned as a tool message

  Scenario: LLM-recoverable error feeds back to the model
    Given a tool that raises an LLM-recoverable error
    When the harness executes the tool
    Then the error is returned as a tool message with is_error true

  Scenario: User-fixable error interrupts the loop
    Given a tool that raises a user-fixable error
    When the harness executes the tool
    Then the loop raises a UserFixableError

  Scenario: Unexpected error bubbles up
    Given a tool that raises an unexpected exception
    When the harness executes the tool
    Then the loop raises an UnexpectedError
