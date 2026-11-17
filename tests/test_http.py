import io
import unittest
from unittest import mock

from yojobs import http


class Trickle(io.BytesIO):
    """A response that delivers data slowly, one small chunk per read."""

    def __init__(self, clock, step, chunks):
        super().__init__()
        self.clock, self.step, self.chunks = clock, step, list(chunks)

    def read(self, n=-1):
        self.clock[0] += self.step
        return self.chunks.pop(0) if self.chunks else b""

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class TotalTimeout(unittest.TestCase):
    def run_with(self, step, chunks):
        clock = [0.0]
        with mock.patch.object(http.time, "monotonic", lambda: clock[0]), \
                mock.patch.object(http.urllib.request, "urlopen", lambda req, timeout: Trickle(clock, step, chunks)):
            return http.get_bytes("https://example.test/big")

    def test_normal_download(self):
        self.assertEqual(self.run_with(1, [b"ab", b"cd"]), b"abcd")

    def test_trickling_download_is_cut_off(self):
        with self.assertRaises(TimeoutError) as e:
            self.run_with(29, [b"x"] * 100)    # each read under the 30 s limit, total far above 120 s
        self.assertIn("longer than 120s", str(e.exception))


if __name__ == "__main__":
    unittest.main()
