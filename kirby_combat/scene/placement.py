"""Re-export (see `kirby_combat.scene`): moved to `kirby_combat.placement`."""
import kirby_combat.placement as _m

globals().update({k: v for k, v in vars(_m).items() if not k.startswith("__")})

