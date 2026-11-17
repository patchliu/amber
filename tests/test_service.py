import copy
import select
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from amber_house.client import AmberClient
from test_spec import QUERY, candidate


TARGET = {"backend": "cuda", "architecture": "sm90"}


class ServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.process = None

    def start(self) -> AmberClient:
        self.process = subprocess.Popen(
            [sys.executable, "-m", "amber_house", "--root", str(self.root / "registry"), "--port", "0"],
            cwd=Path(__file__).resolve().parents[1],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        ready, _, _ = select.select([self.process.stdout], [], [], 5)
        self.assertTrue(ready, "server did not start")
        url = self.process.stdout.readline().strip()
        self.assertTrue(url.startswith("http://127.0.0.1:"), url)
        return AmberClient(url, self.root / "client-cache")

    def stop(self) -> None:
        if self.process is not None:
            self.process.terminate()
            self.process.wait(timeout=5)
            self.process.stdout.close()
            self.process.stderr.close()
            self.process = None

    def tearDown(self) -> None:
        self.stop()

    def test_upload_search_restart_and_cached_download(self) -> None:
        client = self.start()
        source = "def kernel(a, b):\n    return a + b\n"
        implementation = candidate()
        compiled = client.compile(QUERY)
        self.assertTrue(compiled["spec_digest"].startswith("sha256:"))
        upload = client.upload(implementation, TARGET, source)
        first = client.search(QUERY, TARGET)
        self.assertEqual(first["cache"], "miss")
        self.assertEqual(first["matches"][0]["decision"], "candidate")
        self.assertEqual(first["matches"][0]["evidence"], "unverified_source_declaration")
        self.assertEqual(client.search(QUERY, TARGET)["cache"], "hit")
        path, hit = client.download(upload["source_digest"])
        self.assertFalse(hit)
        self.assertEqual(path.read_text(), source)
        self.stop()

        # A fresh service process reuses the registry's durable query cache.
        client = self.start()
        self.assertEqual(client.search(QUERY, TARGET)["cache"], "hit")
        self.stop()
        path, hit = client.download(upload["source_digest"])
        self.assertTrue(hit)
        self.assertEqual(path.read_text(), source)

    def test_new_upload_invalidates_query_cache_and_explains_mismatch(self) -> None:
        client = self.start()
        client.upload(candidate(), TARGET, "first source")
        self.assertEqual(client.search(QUERY, TARGET)["cache"], "miss")
        self.assertEqual(client.search(QUERY, TARGET)["cache"], "hit")
        incompatible = copy.deepcopy(candidate())
        incompatible["computation"]["nodes"][0]["attributes"]["accumulate"] = "fp16"
        client.upload(incompatible, TARGET, "second source")
        report = client.search(QUERY, TARGET)
        self.assertEqual(report["cache"], "miss")
        rejected = [entry for entry in report["matches"] if entry["decision"] == "rejected"]
        self.assertEqual(len(rejected), 1)
        self.assertIn("accumulate", rejected[0]["reasons"][0])


if __name__ == "__main__":
    unittest.main()
