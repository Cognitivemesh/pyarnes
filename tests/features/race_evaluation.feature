Feature: RACE evaluation of finished research reports
  The RaceEvaluator scores a target report against a reference report
  using a post-hoc LLM-as-judge, returning a normalized final score
  in [0, 1] and integrating with EvalSuite.

  # This feature owns the top-level RACE semantics that adopters care about:
  # the normalization anchor, the better-than-reference outcome, and input
  # rejection. Fine-grained weighting and criterion mechanics stay unit-level.

  Scenario: Identical target and reference yield a final score of 0.5
    Given a scripted judge with uniform weights and a constant score
    When the RACE evaluator scores an identical target and reference
    Then the final score is approximately 0.5
    And the criteria weights per dimension sum to 1.0

  Scenario: Better target beats the reference
    Given a scripted judge that rates the target higher than the reference
    When the RACE evaluator runs
    Then the final score is greater than 0.5
    And the EvalSuite records the result as passed

  Scenario: Empty target is rejected
    Given a scripted judge
    When the RACE evaluator is called with an empty target report
    Then a UserFixableError is raised
