# pyarnes-bench

Evaluation and benchmarking toolkit for the pyarnes agentic harness.

## What's included

- **EvalResult** — immutable record of a single evaluation run
- **EvalSuite** — collect, run, and summarise evaluation scenarios
- **Scorers** — pluggable scoring functions (exact match, fuzzy, LLM-as-judge)
- **RaceEvaluator** — post-hoc RACE evaluator for Deep-Research Agents (LLM-as-judge, reference-normalized, 4 dimensions)
- **FactEvaluator** — post-hoc FACT evaluator for citation trustworthiness (accuracy + effective citations; adopter-supplied sources)
