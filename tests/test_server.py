from __future__ import annotations

import unittest
from unittest import mock

from dcp_orchestrator.config import ENV_PREFIX, TASK_ID, RuntimePaths
from dcp_orchestrator.server import Registry, _acquire_server_lease, _asset
import os
import tempfile


class ServerSurfaceTests(unittest.TestCase):
    def test_ui_has_one_card_container_and_machine_states(self):
        html = _asset("index.html").decode("utf-8")
        script = _asset("app.js").decode("utf-8")
        self.assertEqual(html.count('id="task-card"'), 1)
        self.assertIn('id="card-count"', html)
        self.assertIn('id="evidence-list"', html)
        for state in ("succeeded", "failed", "cleanup_failed", "safety_violation"):
            self.assertIn(state, script)
        self.assertNotIn("Задача принята", script)

    def test_ui_assets_have_no_external_fetch_or_script(self):
        for name in ("index.html", "app.js", "styles.css"):
            payload = _asset(name).decode("utf-8")
            self.assertNotIn("https://", payload)
            self.assertNotIn("http://", payload)

    def test_registry_exposes_one_preparing_card_before_worker_thread_runs(self):
        with tempfile.TemporaryDirectory(prefix="dcp-registry-test-") as directory:
            with mock.patch.dict(os.environ, {f"{ENV_PREFIX}ROOT": directory}, clear=False):
                registry = Registry(RuntimePaths.from_environment())
                with mock.patch("dcp_orchestrator.server.threading.Thread.start"):
                    registry.start()
                snapshot = registry.snapshot()
                self.assertEqual(snapshot["card_count"], 1)
                self.assertEqual(snapshot["task"]["task_id"], TASK_ID)
                self.assertEqual(snapshot["task"]["state"], "preparing")
                with self.assertRaisesRegex(Exception, "already consumed"):
                    registry.start()

    def test_server_namespace_has_one_exclusive_lease(self):
        with tempfile.TemporaryDirectory(prefix="dcp-server-lease-test-") as directory:
            with mock.patch.dict(os.environ, {f"{ENV_PREFIX}ROOT": directory}, clear=False):
                paths = RuntimePaths.from_environment()
                paths.create()
                first, lease_path = _acquire_server_lease(paths)
                try:
                    with self.assertRaisesRegex(RuntimeError, "another DCP Orchestrator"):
                        _acquire_server_lease(paths)
                finally:
                    first.close()
                    lease_path.unlink()


if __name__ == "__main__":
    unittest.main()
