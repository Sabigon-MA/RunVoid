"""主人公。異星文明から奪ったテレポート装置を持つ（直接攻撃の手段はない）。

テレポートの判定・位置交換は systems/teleport.py が行い、主人公側は
交換直後の状態リセットと装置の見た目だけを担当する。
"""
from __future__ import annotations

import math

import pygame

import config
from player.base import Player


class Protagonist(Player):
    def __init__(self, x: float, y: float, cfg: dict | None = None):
        super().__init__(cfg or config.protagonist_config(), x, y)
        # 装置の発光（テレポート準備完了で明るくなる）。World が毎フレーム設定する
        self.device_ready = True
        self.device_flash = 0.0

    def update(self, dt, inp, world) -> None:
        self.device_flash = max(0.0, self.device_flash - dt)
        super().update(dt, inp, world)

    def on_teleported(self, world) -> None:
        if config.TELEPORT["reset_velocity"]:
            self.cancel_motion()
        else:
            self.dash_timer = 0.0
        self.coyote = 0.0
        self.jump_buffer = 0.0
        self.trail.clear()
        self.device_flash = 0.3
        # 交換先での接地状態を即座に反映（次フレームの移動を待たない）
        grounded, one_way = world.terrain.ground_state(self.rect)
        self.on_ground = grounded
        self.on_one_way = one_way

    def draw_extra(self, surface, camera) -> None:
        # 左腕のテレポート装置
        f = self.facing
        cx = self.rect.centerx - camera.x - f * 7
        cy = self.rect.top + 22 - camera.y
        if self.device_flash > 0:
            col = (255, 220, 255)
        elif self.device_ready:
            pulse = 0.5 + 0.5 * math.sin(self.anim_time * 6)
            r, g, b = config.COLORS["teleport"]
            col = (int(r * (0.7 + 0.3 * pulse)), int(g * (0.7 + 0.3 * pulse)), int(b * (0.7 + 0.3 * pulse)))
        else:
            col = config.COLORS["teleport_dim"]
        pygame.draw.rect(surface, (30, 24, 34), (cx - 4, cy - 3, 8, 6), border_radius=2)
        pygame.draw.rect(surface, col, (cx - 2, cy - 1, 4, 2))


def create_protagonist(x: float, y: float) -> Protagonist:
    return Protagonist(x, y)
