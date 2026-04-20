"""Dispatch domain — LLM action routing to tool calls.

Atoms and ports used by ``AgentLoop`` to classify actions, compute
retry policy, and invoke tool handlers. No asyncio scheduling lives
here — that's the ``AgentLoop`` system in ``pyarnes_harness``.
"""
