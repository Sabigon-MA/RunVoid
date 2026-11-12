"""ワールド座標と画面座標を分離するカメラ。"""
from __future__ import annotations

import pygame

import config


class Camera:
    def __init__(self, view_w: int, view_h: int, world_w: float, world_h: float):
        self.view_w = view_w
        self.view_h = view_h
        self.world_w = world_w
        self.world_h = world_h
        self.x = 0.0
        self.y = 0.0
        self.follow_ratio = config.CAMERA["follow_x_ratio"]
        self.smoothing = config.CAMERA["smoothing"]
        self.keep_in_view_margin = config.CAMERA["keep_in_view_margin"]
        self.boost_timer = 0.0   # テレポート直後の高速追従

    @property
    def max_x(self) -> float:
        return max(0.0, self.world_w - self.view_w)

    def _clamp(self) -> None:
        self.x = min(max(self.x, 0.0), self.max_x)
        # 試作ではY方向は固定
        self.y = 0.0

    def target_for(self, rect) -> float:
        return rect.centerx - self.view_w * self.follow_ratio

    def follow(self, rect, dt: float) -> None:
        target = min(max(self.target_for(rect), 0.0), self.max_x)
        smoothing = self.smoothing
        if self.boost_timer > 0:
            smoothing *= config.CAMERA["teleport_boost"]
            self.boost_timer = max(0.0, self.boost_timer - dt)
        t = min(1.0, smoothing * dt)
        self.x += (target - self.x) * t
        self.keep_in_view(rect)
        self._clamp()

    def boost(self, duration: float | None = None) -> None:
        """テレポートなどで大きく移動した直後、しばらく追従を速める。"""
        self.boost_timer = config.CAMERA["teleport_boost_time"] if duration is None else duration

    def keep_in_view(self, rect) -> None:
        """プレイヤーが画面端から margin 以上外へ出ないようにカメラを即座に寄せる。"""
        m = self.keep_in_view_margin
        if rect.left - self.x < m:
            self.x = rect.left - m
        elif rect.right - self.x > self.view_w - m:
            self.x = rect.right - (self.view_w - m)

    def snap_to(self, rect) -> None:
        self.x = self.target_for(rect)
        self._clamp()

    # -- 変換 -------------------------------------------------------------
    def to_screen(self, wx: float, wy: float) -> tuple[float, float]:
        return wx - self.x, wy - self.y

    def to_world(self, sx: float, sy: float) -> tuple[float, float]:
        return sx + self.x, sy + self.y

    @property
    def view_rect(self) -> pygame.FRect:
        return pygame.FRect(self.x, self.y, self.view_w, self.view_h)

    def is_visible(self, rect, margin: float = 0.0) -> bool:
        return self.view_rect.inflate(margin * 2, margin * 2).colliderect(rect)
