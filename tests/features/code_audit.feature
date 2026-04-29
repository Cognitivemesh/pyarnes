Feature: Code audit subpackage
  The pyarnes_bench.audit subpackage parses a Python project, persists a graph,
  and runs detectors against it. The build artefact is the source of truth so
  later runs query the graph without re-parsing source.

  Scenario: Build a graph for a clean project
    Given a synthetic Python project with two modules
    When I build the audit graph
    Then the graph contains the modules
    And the graph file is persisted to disk

  Scenario: Detect a circular import
    Given a synthetic Python project with a circular import
    When I build the audit graph
    And I run audit_graph against it
    Then a high-severity circular_import finding is reported

  Scenario: Reload the graph without re-parsing source
    Given a synthetic Python project with two modules
    And the audit graph has been built
    When I reload the graph from disk
    Then the loaded graph has the same node count as the built graph
