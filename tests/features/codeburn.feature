Feature: Codeburn waste-detection scan
  The codeburn:optimize task scans local Claude Code sessions for
  cost-wasting patterns and assigns an A–F health grade.

  Scenario: Optimize emits findings, a grade, and a structured event
    Given a local Claude Code session that triggers a detector
    When I run the codeburn optimize scan
    Then I see at least one finding
    And the report carries a health grade between A and F
    And a "codeburn.optimize.report" event is emitted
    And a 48h snapshot is written under the cache directory

  Scenario: Optimize against a clean workspace returns grade A
    Given a clean Claude Code workspace
    When I run the codeburn optimize scan
    Then the report carries grade A
