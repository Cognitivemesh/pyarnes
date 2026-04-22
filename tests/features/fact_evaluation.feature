Feature: FACT citation trustworthiness of finished reports
  The FactEvaluator extracts cited claims from a report, deduplicates
  them, and verifies each one against an adopter-provided sources map,
  producing citation-accuracy and effective-citation metrics.

  Scenario: All claims supported yields accuracy 1.0
    Given a scripted FACT judge that supports every claim
    And a sources map covering every URL
    When the FACT evaluator runs
    Then the citation accuracy is 1.0
    And the effective citation count equals the supported count

  Scenario: Missing source is excluded from the accuracy denominator
    Given a scripted FACT judge that extracts two claims
    And a sources map missing one URL
    When the FACT evaluator runs
    Then the missing-source claim is marked unsupported by provided sources
    And the accuracy denominator excludes the missing claim

  Scenario: Empty report is rejected
    Given a scripted FACT judge
    When the FACT evaluator is called with an empty report
    Then a UserFixableError is raised
