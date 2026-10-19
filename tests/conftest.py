"""Tests must never write to the real database file."""
import os, tempfile
os.environ["CIVILBOT_DB"] = os.path.join(tempfile.mkdtemp(prefix="civilbot_test_"), "test.sqlite3")
os.environ.setdefault("MPLBACKEND", "Agg")
