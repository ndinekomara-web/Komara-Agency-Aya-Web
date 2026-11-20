"""Les tests ne doivent pas attendre le temps de « réflexion » de production."""
import os

os.environ.setdefault("RESPONSE_DELAY_MIN", "0")
os.environ.setdefault("RESPONSE_DELAY_MAX", "0")
