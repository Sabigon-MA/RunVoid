"""ボスが放つ飛び道具。

発射後は発射元から独立したオブジェクトとして CombatSystem が管理する。
    発射元 / 所有者 … owner（ボス）
    現在位置       … x, y
    移動速度・方向 … speed, (dx, dy)  ※位置交換が起きても方向は変えない
    ダメージ       … damage
    当たり判定     … 半径 radius の円を移動経路に沿って判定（Projectile と同じ）
    自傷判定の可否 … self_harm（False ならどんな場合も発射元に当たらない）

自傷ルール:
    通常、ボス自身の攻撃はボスに当たらない。
    ただし発射元がテレポートで位置交換された時点で飛行中だった弾は「自傷有効」になり、
    以後はボスにも命中する（主人公がボスと入れ替わり、ボスを自分の弾の軌道上に置く攻略）。
    交換された瞬間に既にボスの当たり判定と重なっていた弾は、その重なりが解消されるまで
    ボスに当たらない（発射直後の弾が交換と同時に誤爆しないようにするため）。
"""
from __future__ import annotations

from systems.combat import Projectile


class BossProjectile(Projectile):
    def __init__(self, owner, damage, x, y, dir_x, dir_y, speed, max_range, width,
                 self_harm: bool = True, color=(235, 90, 200), **kw):
        kw.setdefault("target_team", "player")
        super().__init__(owner, damage, x, y, dir_x, dir_y, speed, max_range, width, color=color, **kw)
        self.self_harm = self_harm
        self.self_harm_armed = False
        self._owner_overlap_grace = False

    def on_owner_teleported(self) -> None:
        """発射元が位置交換されたときに TeleportSystem から呼ばれる。"""
        if not self.self_harm or self.done:
            return
        self.self_harm_armed = True
        owner_box = getattr(self.owner, "hurtbox", None)
        self._owner_overlap_grace = owner_box is not None and self.overlaps(owner_box)

    def damage_for(self, target) -> float:
        if target is self.owner:
            return getattr(self.owner, "params", {}).get("projectile_self_damage", self.damage)
        return self.damage

    def extra_targets(self):
        if not self.self_harm_armed or not getattr(self.owner, "alive", False):
            return ()
        if self._owner_overlap_grace:
            if self.overlaps(self.owner.hurtbox):
                return ()
            self._owner_overlap_grace = False
        return (self.owner,)
