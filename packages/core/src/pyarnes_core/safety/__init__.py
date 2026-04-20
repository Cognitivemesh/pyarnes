"""Safety domain — guardrail primitives (pure, no I/O).

Atoms and molecules for preventing dangerous tool calls. Downstream
consumers (``pyarnes_guardrails``) import these and wrap them in the
``Guardrail`` protocol.
"""
