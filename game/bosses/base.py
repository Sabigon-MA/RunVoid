"""ボスの共通基底クラス。

- Enemy を継承するため、雑魚敵と同じくテレポート対象になる（足元中央基準で位置交換）。
- 怯まない（stagger_immunity=True）。主人公は直接攻撃できないので、
  ダメージ源は自身の飛び道具（BossProjectile の自傷ルール）や環境のみ。
- 戦闘開始（engage）で追跡壁を停止し、撃破で再開する。
  最終ボス（壁発生源）は stops_wall_permanently=True にすると撃破で壁が完全停止する。

サブクラスは update_ai(dt, world) に行動を実装する。攻撃周期はテレポートの
クールダウン（config.TELEPORT["cooldown"]）より長い予備動作・間隔を基本にする。
"""
from __future__ import annotations

import pygame

import config
from bosses.projectile import BossProjectile
from enemies.base import Enemy


class Boss(Enemy):
    TYPE = "boss"
    is_boss = True
    display_name = "ボス"
    stops_wall_permanently = False

    def __init__(self, x: float, foot_y: float, enemy_id: str = "", params: dict | None = None):
        p = dict(config.BOSS_DEFAULTS)
        if params:
            p.update(params)
        super().__init__(x, foot_y, p["body_w"], p["body_h"], p["hp"], p["contact_damage"], enemy_id,
                         stagger_immunity=True, gravity=p["gravity"],
                         max_fall_speed=p["max_fall_speed"])
        self.params = p
        self.engaged = False

    # -- 戦闘開始・終了 ---------------------------------------------------
    def should_engage(self, world) -> bool:
        """既定: ボスが画面内に入ったら戦闘開始。"""
        return world.camera.is_visible(self.body_rect)

    def engage(self, world) -> None:
        self.engaged = True
        world.on_boss_engaged(self)

    # -- 攻撃 -------------------------------------------------------------
    def fire(self, world, x: float, y: float, dir_x: float, dir_y: float, **overrides) -> BossProjectile:
        """飛び道具を発射する（数値は params の projectile_* を既定値とする）。"""
        p = self.params
        proj = BossProjectile(
            self, overrides.get("damage", p["projectile_damage"]), x, y, dir_x, dir_y,
            overrides.get("speed", p["projectile_speed"]),
            overrides.get("max_range", p["projectile_range"]),
            overrides.get("width", p["projectile_width"]),
            self_harm=overrides.get("self_harm", p["projectile_self_harm"]),
            hitstop_frames=overrides.get("hitstop_frames", p["projectile_hitstop_frames"]))
        world.combat.spawn(proj)
        return proj

    def fire_at_player(self, world, **overrides) -> BossProjectile:
        cx, cy = self.center
        px, py = world.player.rect.center
        return self.fire(world, cx, cy, px - cx, py - cy, **overrides)

    # -- 更新 -------------------------------------------------------------
    def update(self, dt: float, world) -> None:
        super().update(dt, world)
        if not self.engaged:
            if self.should_engage(world):
                self.engage(world)
            return
        self.update_ai(dt, world)

    def update_ai(self, dt: float, world) -> None:
        """サブクラスで実装する。"""

    def draw(self, surface: pygame.Surface, camera) -> None:
        r = self.body_rect.move(-camera.x, -camera.y)
        col = (200, 170, 230) if self.hurt_flash > 0 else config.COLORS["silhouette"]
        pygame.draw.rect(surface, col, r, border_radius=6)
        pygame.draw.rect(surface, config.COLORS["enemy_eye"], (r.centerx - 6, r.top + 10, 12, 4))
