"""Prevent runtime files and workstation-specific paths entering releases."""

from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ReleaseContents(unittest.TestCase):
    def test_no_private_paths_or_runtime_payloads(self):
        forbidden = [
            re.compile(r"/home/(?!USER(?:/|\b)|example(?:/|\b))[A-Za-z0-9_.-]+/"),
            re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----"),
            re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"),
            re.compile(r"(?<![\w])(?:sk-proj-|sk-live-)[A-Za-z0-9_-]{20,}"),
        ]
        for path in ROOT.rglob("*"):
            if not path.is_file() or any(
                part in {".git", "__pycache__", ".ruff_cache", ".pytest_cache", ".venv"}
                for part in path.parts
            ):
                continue
            if path.suffix in {".sqlite", ".sqlite3", ".log", ".so", ".pem", ".key"}:
                self.fail(f"Runtime or secret material must not be published: {path.relative_to(ROOT)}")
            if path.suffix.lower() in {".png", ".jpg", ".gif"}:
                continue
            text = path.read_text(errors="replace")
            for pattern in forbidden:
                self.assertIsNone(pattern.search(text), str(path.relative_to(ROOT)))


if __name__ == "__main__":
    unittest.main()
