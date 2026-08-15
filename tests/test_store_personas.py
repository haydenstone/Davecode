"""AENIMUS persistence and persona tests v0.1.0."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from app.db import Store
from app.personas import load_directory


class StorePersonaTests(unittest.TestCase):
    def test_seed_personas_are_versioned(self):
        rows = load_directory(Path("personas"))
        self.assertGreaterEqual(len(rows), 4)
        self.assertTrue(all(x["version"] == "0.1.0" for x in rows))
        names = {x["id"]: x["name"] for x in rows}
        self.assertEqual(names["architect"], "Elliot Stone")
        self.assertEqual(names["narrator"], "Ava Stone")
        self.assertEqual(names["reviewer"], "Vee Thorne")

    def test_online_backup_and_restore(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = Store(root / "live.db")
            store.put_agent({"id": "agent-one"})
            store.backup(root / "backup.db")
            store.put_agent({"id": "agent-two"})
            store.restore(root / "backup.db")
            self.assertEqual([x["id"] for x in store.agents()], ["agent-one"])

    def test_approval_is_payload_bound_and_single_use(self):
        with TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "live.db")
            approval = store.approval("terminal.exec", {"argv": ["ls"], "cwd": "."})
            store.decide(approval["id"], "approved")
            self.assertFalse(
                store.consume_approval(
                    approval["id"], "terminal.exec", {"argv": ["id"], "cwd": "."}
                )
            )
            self.assertTrue(
                store.consume_approval(
                    approval["id"], "terminal.exec", {"argv": ["ls"], "cwd": "."}
                )
            )
            self.assertFalse(
                store.consume_approval(
                    approval["id"], "terminal.exec", {"argv": ["ls"], "cwd": "."}
                )
            )

    def test_layered_persona_resolves_independent_of_file_order(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a-child.md").write_text(
                "---\nid: child\nextends: base\n---\nChild"
            )
            (root / "z-base.md").write_text("---\nid: base\n---\nBase")
            child = next(x for x in load_directory(root) if x["id"] == "child")
            self.assertEqual(child["persona"], "Base\n\nChild")


if __name__ == "__main__":
    unittest.main()
