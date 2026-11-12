"""テレポート（主人公と敵の位置交換）。

処理の流れ（World.update の先頭、同一の物理更新内で完結する）:
    1. 左クリックの押下開始時のみ、カーソル下の敵を対象として試行する
    2. クールダウン中・対象不正なら失敗（クールダウンは消費しない）
    3. 足元中央を交換基準に、双方の交換先の仮位置を計算する
    4. それぞれ地形・マップ外・追跡壁と重なる場合は半径 safe_search_radius 内で安全位置を探す
       （壁の向こう側へ抜けないよう、元の占有者の中心から直線で到達できる位置に限る）
    5. 両方の位置が確定した場合のみ交換する。どちらかが見つからなければ双方とも動かさない
    6. 成功時: 速度・ダッシュのリセット、演出、クールダウン開始、ボス弾の自傷を有効化

テレポートは攻撃ではないため、交換自体ではどちらにもダメージを与えない。
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import config

SUCCESS = "success"
FAIL_COOLDOWN = "cooldown"
FAIL_INVALID = "invalid"
FAIL_BLOCKED = "blocked"


@dataclass
class TeleportResult:
    ok: bool
    reason: str
    player_foot: tuple[float, float] | None = None
    target_foot: tuple[float, float] | None = None


def _offsets(radius: float, step: float) -> list[tuple[float, float]]:
    """探索する補正量の一覧（近い順。同距離なら上方向→水平方向の小さい順）。"""
    n = int(radius // step)
    out = []
    for iy in range(-n, n + 1):
        for ix in range(-n, n + 1):
            dx, dy = ix * step, iy * step
            if dx * dx + dy * dy <= radius * radius + 1e-9:
                out.append((dx, dy))
    out.sort(key=lambda o: (round(math.hypot(*o), 6), o[1] > 0, abs(o[0]), o[1]))
    return out


class TeleportSystem:
    def __init__(self, params: dict | None = None):
        self.params = dict(config.TELEPORT)
        if params:
            self.params.update(params)
        self.cooldown_remaining = 0.0
        self.count = 0
        self.last_result: TeleportResult | None = None
        self.feedback_timer = 0.0     # 失敗表示用
        self._offsets = _offsets(self.params["safe_search_radius"], self.params["safe_search_step"])

    # ------------------------------------------------------------------
    @property
    def cooldown(self) -> float:
        return self.params["cooldown"]

    @property
    def ready(self) -> bool:
        return self.cooldown_remaining <= 0

    @property
    def ready_ratio(self) -> float:
        return 1.0 - min(1.0, self.cooldown_remaining / self.cooldown) if self.cooldown > 0 else 1.0

    def update(self, dt: float) -> None:
        # 浮動小数点誤差で1フレーム延びないよう、ごく小さい残りは0とみなす
        r = self.cooldown_remaining - dt
        self.cooldown_remaining = r if r > 1e-9 else 0.0
        self.feedback_timer = max(0.0, self.feedback_timer - dt)

    # -- 安全位置 ---------------------------------------------------------
    def is_safe(self, world, rect) -> bool:
        stage = world.stage
        if rect.left < 0 or rect.right > stage.world_width:
            return False
        if rect.bottom > stage.kill_y or rect.top < -stage.resolution[1]:
            return False
        if world.terrain.overlaps_solid(rect):
            return False
        if world.wall.touches(rect):
            return False
        return True

    @staticmethod
    def path_clear(terrain, a, b, step: float = 4.0) -> bool:
        """a から b への直線上に固体地形がないか（安全位置補正で壁を抜けない保証）。"""
        dist = math.hypot(b[0] - a[0], b[1] - a[1])
        n = max(1, math.ceil(dist / step))
        for i in range(n + 1):
            t = i / n
            if terrain.point_in_solid(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t):
                return False
        return True

    def find_safe_foot(self, world, entity, foot, anchor):
        """entity の足元中央を foot 付近に置ける位置を探す。見つからなければ None。

        anchor は交換先に元々いた者の中心（固体地形の外であることが保証された点）。
        """
        fx, fy = foot
        for dx, dy in self._offsets:
            rect = entity.rect_at_foot(fx + dx, fy + dy)
            if not self.is_safe(world, rect):
                continue
            if not self.path_clear(world.terrain, anchor, rect.center):
                continue
            return fx + dx, fy + dy
        return None

    # -- 実行 -------------------------------------------------------------
    def try_teleport(self, world, target) -> TeleportResult:
        result = self._try(world, target)
        self.last_result = result
        if not result.ok:
            self.feedback_timer = 0.6
        return result

    def _try(self, world, target) -> TeleportResult:
        player = world.player
        if not self.ready:
            return TeleportResult(False, FAIL_COOLDOWN)
        if (target is None or not player.alive or not target.can_be_teleported()
                or not world.camera.view_rect.colliderect(target.hurtbox)):
            return TeleportResult(False, FAIL_INVALID)

        player_from = player.foot_center
        target_from = target.foot_center
        player_anchor = player.rect.center
        target_anchor = target.hurtbox.center
        # 成功判定前には座標を一切変更しない
        new_player = self.find_safe_foot(world, player, target_from, target_anchor)
        if new_player is None:
            return TeleportResult(False, FAIL_BLOCKED)
        new_target = self.find_safe_foot(world, target, player_from, player_anchor)
        if new_target is None:
            return TeleportResult(False, FAIL_BLOCKED)

        before = (player.rect.copy(), target.hurtbox.copy())
        if world.with_graphics:
            world.effects.teleport_depart(player, target, world.camera)

        # 両者の位置を同時に確定する
        player.place_foot(*new_player)
        target.place_foot(*new_target)
        player.on_teleported(world)
        target.on_teleported(world)

        # 発射元が交換された飛び道具は自傷判定が有効になる
        for attack in world.combat.attacks:
            if attack.owner is target and hasattr(attack, "on_owner_teleported"):
                attack.on_owner_teleported()

        self.cooldown_remaining = self.cooldown
        self.count += 1
        world.on_teleported(target, before)
        return TeleportResult(True, SUCCESS, new_player, new_target)
