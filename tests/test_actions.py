"""End-to-end tests for the action pipeline (resolve_attack)."""
from kirby_combat.actions import resolve_attack
from kirby_combat.models import AttackInput, DiceValues


class TestEnergyBlastHitAndDamage:
    """Blaster fires 10d6 EB at Brick at 20 m — hit, normal damage."""

    def test_hit_and_damage(self, blaster, brick, superhero_template):
        attack = AttackInput(
            attacker=blaster,
            target=brick,
            power=blaster.attacks[0],  # Energy Blast 10d6 normal/ed
            distance_m=20,
            aim=None,
            dice=DiceValues(
                to_hit=[3, 3, 3],
                damage=[5, 4, 3, 6, 2, 4, 6, 3, 1, 2],
            ),
        )
        result = resolve_attack(attack, superhero_template)

        # To-hit: roll 9, OCV 8, range -4, target number = (8-4)+11-4 = 11. 9 <= 11 -> hit
        assert result.hit is True
        assert result.to_hit.range_penalty == -4

        # Damage: normal 10d6 -> STUN = sum = 36, BODY per die rules
        assert result.damage.stun == 36

        # Defense: Brick ED = 15, rED = 5, plus no defense items.
        # Normal attack: total ED = 15 applies to both STUN and BODY.
        assert result.defense.total_defense == 15

        # STUN dealt = 36 - 15 = 21
        assert result.stun_dealt == 21

        # BODY dealt: normal BODY = 0+1+1+2+1+1+2+1+0+1 = 10? Let me compute:
        # die values [5,4,3,6,2,4,6,3,1,2]
        # body: 1,1,1,2,1,1,2,1,0,1 = 10? Wait: 1=0, so:
        # 5->1, 4->1, 3->1, 6->2, 2->1, 4->1, 6->2, 3->1, 1->0, 2->1 = 10
        # BODY dealt = 10 - 15 = negative -> 0
        assert result.body_dealt == 0

        assert result.power_xmlid == "ENERGYBLAST"


class TestEnergyBlastMiss:
    """Blaster fires EB at Brick — roll 18, always miss."""

    def test_miss(self, blaster, brick, superhero_template):
        attack = AttackInput(
            attacker=blaster,
            target=brick,
            power=blaster.attacks[0],
            distance_m=20,
            aim=None,
            dice=DiceValues(
                to_hit=[6, 6, 6],
            ),
        )
        result = resolve_attack(attack, superhero_template)

        assert result.hit is False
        assert result.damage is None
        assert result.stun_dealt == 0


class TestKillingAttack:
    """Blaster fires 3d6+1 RKA at Brick at 10 m — hit, killing damage."""

    def test_killing_hit(self, blaster, brick, superhero_template):
        attack = AttackInput(
            attacker=blaster,
            target=brick,
            power=blaster.attacks[1],  # RKA 3d6+1 killing/ed
            distance_m=10,
            aim=None,
            dice=DiceValues(
                to_hit=[3, 4, 2],
                damage=[4, 5, 3],
                stun_multiplier=[4],
            ),
        )
        result = resolve_attack(attack, superhero_template)

        # To-hit: roll 9, OCV 8, range -2 (10m), target number = (8-2)+11-4 = 13. 9<=13 -> hit
        assert result.hit is True

        # Damage: killing 3d6+1 -> BODY = 4+5+3+1 = 13. Per 6E2 p100, STUN mult is ½d6:
        # raw d6=4 → half_die=2; multiplier = 1+(2-1) = 2. STUN = 13*2 = 26.
        assert result.damage.body == 13
        assert result.damage.stun == 26

        # Defense: Brick ED=15, rED=5.
        # Killing: STUN dealt = max(0, raw_stun - total_defense) = max(0, 26-15) = 11
        # BODY dealt = raw_body - resistant_defense = 13 - 5 = 8
        assert result.stun_dealt == 11
        assert result.body_dealt == 8
