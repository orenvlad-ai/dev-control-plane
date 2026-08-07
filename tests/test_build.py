from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
import zipfile

from scripts.build_artifact import build


class BuildTests(unittest.TestCase):
    def test_artifact_is_executable_zipapp_with_attribution(self):
        with tempfile.TemporaryDirectory(prefix="dcp-build-test-") as directory:
            artifact = build(Path(directory) / "dcp-orchestrator.pyz")
            self.assertTrue(artifact.read_bytes().startswith(b"#!/usr/bin/env python3\nPK"))
            with zipfile.ZipFile(artifact) as archive:
                names = set(archive.namelist())
            self.assertIn("dcp_orchestrator/server.py", names)
            self.assertIn("NOTICE", names)
            self.assertIn("licenses/agent-orchestrator-APACHE-2.0.txt", names)


if __name__ == "__main__":
    unittest.main()
