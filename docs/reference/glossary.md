---
tags: [reference, glossary]
---

# Glossary

## ABC

Abstract Base Class. A Python class used to define required methods for subclasses.

## ASGI

Asynchronous Server Gateway Interface. A Python standard for async web servers and applications.

## BDD

Behavior-Driven Development. Test style that describes behavior in scenario language (for example Gherkin).

## FSM

Finite-State Machine. A model where transitions are allowed only between specific states.

## JSONL

JSON Lines. One JSON object per line, useful for streamable logs and machine parsing.

## MCP

Model Context Protocol. A protocol used by coding agents to discover and call tools.

## PEP 621

Python Enhancement Proposal that standardizes project metadata in `pyproject.toml`.

## TDD

Test-Driven Development. Red → Green → Refactor workflow where tests are written before implementation.

## adopter

In pyarnes docs, you are an adopter when you use pyarnes to scaffold and build your own project.

## guardrail chain

Composable list of guardrails evaluated before tool execution to enforce safety constraints.

## lifecycle

The pyarnes session state machine (`INIT`, `RUNNING`, `PAUSED`, `COMPLETED`, `FAILED`) tracked by `Lifecycle`.

## tool handler

An implementation of the `ToolHandler` contract that executes one tool call from the model.
