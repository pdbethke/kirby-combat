"""Reactive defenses: Dodge, Block, Abort.

Reactive defenses are declared in response to an incoming attack or event.
They mark the combatant as 'aborting' — forfeiting their next phase's action
in exchange for an immediate defensive reaction this phase.
"""
from kirby_combat.actions.reactive.abort import (
    is_aborting, mark_aborting,
)
from kirby_combat.actions.reactive.dodge import Dodge
from kirby_combat.actions.reactive.block import Block, BlockResult

__all__ = ["is_aborting", "mark_aborting", "Dodge", "Block", "BlockResult"]
