import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from yojobs import __main__ as cli
from yojobs import discovery
from yojobs.store import Store


class WeeklyWithoutDiscovery(unittest.TestCase):
    def test_discovery_failure_does_not_block_the_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "db.sqlite")
            def boom(*a, **k):
                raise ValueError("Unterminated string")
            with mock.patch.object(discovery, "run", boom), mock.patch.object(cli, "note") as note, \
                    mock.patch("builtins.print") as printed, \
                    mock.patch.object(cli, "_near_miss_scorer", lambda cfg, store: None):
                code = cli.send_weekly(SimpleNamespace(email=False), {"weekly": {}}, store)
            store.db.close()
        self.assertEqual(code, 0)
        self.assertTrue(printed.called)                                   # the summary was still built
        self.assertIn("Board discovery failed", note.call_args_list[0].args[0])


if __name__ == "__main__":
    unittest.main()
