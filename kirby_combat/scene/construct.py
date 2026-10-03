"""Re-export (see `kirby_combat.scene`): kirby_world.construct, with the session-taking `constructs_in` from combat."""
import kirby_world.construct as _m

globals().update({k: v for k, v in vars(_m).items() if not k.startswith("__")})
from kirby_combat.constructs import constructs_in, damage_by_object, damage_taken  # noqa: E402,F401
