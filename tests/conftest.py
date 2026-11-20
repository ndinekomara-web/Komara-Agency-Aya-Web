"""Chaque exécution des tests part d'une base neuve et sans attente."""
import os
import tempfile

os.environ.setdefault("RESPONSE_DELAY_MIN", "0")
os.environ.setdefault("RESPONSE_DELAY_MAX", "0")
os.environ["MEMORY_DIR"] = tempfile.mkdtemp(prefix="aya-tests-")
os.environ["ADMIN_ID"] = ""
