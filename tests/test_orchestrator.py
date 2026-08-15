"""AENIMUS orchestration role-boundary tests v0.1.1."""

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.orchestrator import run


class FakeStore:
    def __init__(self):
        self.saved = []

    def messages(self, _session_id):
        return [{"role": "user", "content": "Build the requested feature."}]

    def message(self, session_id, role, content, agent_id, channel):
        item = {
            "session_id": session_id,
            "role": role,
            "content": content,
            "agent_id": agent_id,
            "channel": channel,
        }
        self.saved.append(item)
        return item

    def audit(self, *_args, **_kwargs):
        return None


class OrchestratorTests(unittest.IsolatedAsyncioTestCase):
    async def test_targeted_executor_is_not_promoted_to_evaluator(self):
        store = FakeStore()
        session = {
            "id": "session",
            "agent_ids": ["builder", "reviewer"],
            "orchestration": "pipeline",
        }
        agents = [
            {"id": "builder", "role": "executor"},
            {"id": "reviewer", "role": "reviewer"},
        ]
        request = SimpleNamespace(
            content="Implement it.",
            agent_id="builder",
            max_rounds=8,
            success_criteria="Complete implementation.",
        )

        async def fake_complete(_agent, messages):
            instruction = messages[-1]["content"]
            self.assertIn("as the executor", instruction)
            self.assertNotIn("final/head evaluator", instruction)
            self.assertNotIn("[OUTCOME:", instruction)
            return "Concrete implementation response."

        with (
            patch("app.orchestrator.complete", side_effect=fake_complete) as completed,
            patch("app.orchestrator.recall", new=AsyncMock(return_value=[])),
            patch("app.orchestrator.remember", new=AsyncMock(return_value=True)),
        ):
            output = await run(store, session, request, agents)

        self.assertEqual(completed.call_count, 1)
        self.assertEqual(len(output), 1)
        self.assertEqual(output[0]["agent_id"], "builder")


if __name__ == "__main__":
    unittest.main()
