import unittest

from yojobs.sources.companies import _mode


class WorkMode(unittest.TestCase):
    def test_mode(self):
        self.assertTrue(_mode("Remote"))
        self.assertTrue(_mode("remote"))
        self.assertFalse(_mode("Hybrid"))
        self.assertFalse(_mode("OnSite"))
        self.assertFalse(_mode("on-site"))
        self.assertIsNone(_mode(None))
        self.assertIsNone(_mode("unspecified"))


if __name__ == "__main__":
    unittest.main()
