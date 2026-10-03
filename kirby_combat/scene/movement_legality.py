"""Re-export (see `kirby_combat.scene`): kirby_world.movement_legality, with the session-taking `movement_reach` from combat."""
import kirby_world.movement_legality as _m

globals().update({k: v for k, v in vars(_m).items() if not k.startswith("__")})
from kirby_combat.reach import movement_reach  # noqa: E402,F401
