"""Print the shipped schema. `python -m kirby_combat.schema > events.json`."""
import sys

from kirby_combat.schema import SCHEMA_PATH

sys.stdout.write(SCHEMA_PATH.read_text())
