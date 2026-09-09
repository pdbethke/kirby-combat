"""Side — which part of a fight a combatant is on. An object, not a string.

WHY THIS IS A CLASS. It began as `side: str | None`, and the string carried
the whole design badly:

* Two spellings silently became two things. `"Golden"` and `"golden"` in one
  roster made a fifth army in a four-army battle, changing who won, with
  nothing to look at. That needed a whole canonicalising validator to catch
  after the fact --- a defect a type could have prevented.
* Nothing could hang off it. "Is this side still standing", "what team is
  this side drawn from", "is this a real side or a lone brawler" all had to
  be re-derived by every caller from a bare value.
* The absent case had to be encoded IN the string. A combatant with no side
  is their own side, which as a string meant inventing a `"solo:<id>"`
  convention that every reader had to know and none could enforce.

A `Side` answers all three, once.

IDENTITY IS ``id``, AND ONLY ``id``. Equality and hashing ignore ``name`` and
``team_id`` deliberately: two references to the same side must compare equal
even if one was built with a display name and the other without. ``name`` is
what a result reports ("Iron Chorus wins"); ``id`` is what the engine
compares.

WHY THIS LIVES IN kirby-combat AND NOT IN kirby-campaign. A side is a fight
concept. A free-for-all in an alley has sides and no campaign, no teams and
no rosters --- so the class belongs in the lower package, and the higher one
builds instances of it. kirby-campaign imports this to turn a Team into a
Side; nothing here ever imports kirby-campaign. Putting `Side` upstairs
would have made resolving an attack depend on knowing what a campaign is.

``team_id`` is the opaque back-reference for when a side DID come from a
team. This module never dereferences it --- it is a string precisely because
following it is somebody else's job.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_WHITESPACE = re.compile(r"\s+")

#: Prefix for the side of a combatant who is on no named side.
SOLO_PREFIX = "solo:"


@dataclass(frozen=True)
class Side:
    """One side of a fight.

    Any number may exist: two teams, a three-way, the battle of four armies,
    or a brawl where every fighter is their own side. Nothing caps it.
    """

    id: str
    #: What a result calls this side. Defaults to ``id``.
    name: str = ""
    #: Opaque reference to the campaign Team this side was drawn from, if
    #: any. Never dereferenced here.
    team_id: str | None = field(default=None, compare=False)
    #: What this side is trying to achieve, in one sentence, for whatever
    #: is choosing actions to read.
    #:
    #: THE OTHER HALF OF A GOALS MODEL. Individual goals are Psychological
    #: Complications and the Brief renders them; a fighter could read his
    #: own code of honour and had no way to learn that the Earps were in
    #: that lot to DISARM the Cowboys rather than to kill them or to
    #: demolish Fly's Boarding House.
    #:
    #: A STRING, NOT A TEAM. kirby-combat must never import
    #: kirby-campaign: the bridge from a standing team to a fight's sides
    #: is deliberately a plain side, and `team_id` above is an opaque
    #: back-reference this module never dereferences. An objective is the
    #: same shape --- the campaign layer knows what the Earps want and
    #: writes it down when it builds the sides. Holding a real Team here
    #: would drag the entity layer behind every fight.
    #:
    #: `compare=False` for the same reason `team_id` is: two references to
    #: one side must compare equal, and a fight whose halves word the goal
    #: differently is still one fight.
    objective: str | None = field(default=None, compare=False)

    def __post_init__(self) -> None:
        if not (self.id or "").strip():
            raise ValueError("a Side needs an id")
        if not self.name:
            object.__setattr__(self, "name", self.id)

    # Identity is the id. `name` is display, `team_id` is a back-reference;
    # neither may split one side into two.
    def __eq__(self, other: object) -> bool:
        return isinstance(other, Side) and other.id == self.id

    def __hash__(self) -> int:
        return hash(self.id)

    def __str__(self) -> str:
        return self.name

    @classmethod
    def of(cls, combatant) -> "Side":
        """The side a combatant fights for.

        An explicit ``Side`` is returned as given; ``None`` resolves to
        ``Side.solo(combatant.id)``. A plain string RAISES rather than being
        coerced --- silently accepting one would restore exactly the class
        of bug this type exists to remove.
        """
        side = getattr(combatant, "side", None)
        if side is None:
            return cls.solo(combatant.id)
        if isinstance(side, str):
            raise TypeError(
                f"combatant {combatant.id!r} carries side={side!r} as a "
                f"string; sides are objects --- use Side.named({side!r}) so "
                f"that two spellings cannot become two armies"
            )
        return side

    @classmethod
    def solo(cls, combatant_id: str) -> "Side":
        """The side of a combatant who is on no named side --- themselves.

        This is the default, and it is load-bearing. The tempting reading ---
        that everyone unlabelled shares one "default" side --- ends an N-way
        free-for-all before the first punch, because "at most one side still
        standing" is true from the start. A side of one makes the team battle
        and the free-for-all the same rule.
        """
        return cls(id=f"{SOLO_PREFIX}{combatant_id}", name=combatant_id)

    @classmethod
    def named(cls, name: str, *, team_id: str | None = None,
              objective: str | None = None) -> "Side":
        """A named side, with its id derived from the name.

        The id is canonicalised (trimmed, internal whitespace collapsed,
        case-folded) so ``"Golden"``, ``"golden"`` and ``" Golden "`` are ONE
        side rather than three. That typo class is now impossible to create
        by accident rather than merely detectable afterwards --- which is
        most of why this stopped being a string.
        """
        canonical = _WHITESPACE.sub(" ", (name or "").strip())
        if not canonical:
            raise ValueError("a named Side needs a name")
        return cls(id=canonical.casefold(), name=canonical, team_id=team_id,
                   objective=objective)

    @property
    def is_solo(self) -> bool:
        """True when this side is one combatant standing alone."""
        return self.id.startswith(SOLO_PREFIX)
