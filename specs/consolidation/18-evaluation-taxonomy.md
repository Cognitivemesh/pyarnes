# 18-evaluation-taxonomy

> See also `07-bench-integrated-axes.md` § Use-case reference: coding agents and deep agents — full taxonomy with worked examples.

## Evaluation Use-Case Taxonomy

To rigorously benchmark swarm capabilities, interactions are categorized into an integrated three-tier taxonomy that tracks both tool-selection capacity and ablation matrix components.

### Tier 1/2/3 Taxonomy
Inherited directly from the comprehensive Agents-eval standard, evaluation problems are segmented heavily into tiers based on context depth and cognitive load requirements.

### UC-C3 Tool-Selection
Under Use Case C3, the Agent must independently and correctly deduce tool hygiene parameters (e.g., streaming considerations from `CLAUDE.md`), showcasing complex reasoning distinct from simple schema parsing.

### 2³ Ablation Matrix
Experiments are conducted under a $2^3$ ablation matrix, intentionally restricting specific tools or reasoning pipelines (e.g., dropping the tool search node) to scientifically prove the necessity and performance bounds of the missing features.
