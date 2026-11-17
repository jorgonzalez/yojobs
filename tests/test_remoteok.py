import unittest

from yojobs.sources.remoteok import fix_mojibake


class Mojibake(unittest.TestCase):
    def test_double_encoded_is_fixed(self):
        self.assertEqual(fix_mojibake("MÃ¼nchen"), "München")

    def test_clean_text_unchanged(self):
        self.assertEqual(fix_mojibake("München"), "München")
        self.assertEqual(fix_mojibake("Remote - US"), "Remote - US")
        self.assertEqual(fix_mojibake(""), "")


if __name__ == "__main__":
    unittest.main()
