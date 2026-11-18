import unittest
from unittest import mock

from yojobs import __main__ as m


class CvCheck(unittest.TestCase):
    def tearDown(self):
        m.progress.set_verbose(False)  # -v in a test must not leak into later tests

    def run_main(self, argv):
        calls = []
        with mock.patch.object(m, "load_config", return_value={}), mock.patch.object(m, "Store"), \
                mock.patch.object(m.matching, "check", lambda cfg, root: calls.append("check") or 0), \
                mock.patch.object(m, "run", lambda args, cfg, store, days: calls.append(("run", days, args.email)) or (0, True)), \
                mock.patch.object(m, "RunLock") as lock:
            lock.return_value.acquire.return_value = True
            m.main(argv)
        return calls

    def test_alone_only_checks(self):
        self.assertEqual(self.run_main(["--cv-check"]), ["check"])

    def test_with_run_options_checks_then_runs(self):
        self.assertEqual(self.run_main(["--cv-check", "--days", "90", "-v", "--email"]),
                         ["check", ("run", 90.0, True)])


if __name__ == "__main__":
    unittest.main()
