"""ワールド座標と画面座標を分離するカメラ。

縦方向（v3.0）:
    bounds=(top, bottom) を渡したときだけ縦に追従する。渡さなければ従来どおり y=0 に固定する。
    縦の基準は「最後に着地した足元の y」。ジャンプのたびに画面が上下しないよう、空中では基準を動かさず、
    画面の上 keep_in_view_margin_top・下 keep_in_view_margin_bottom の範囲を出たときだけ即座に寄せる。
    基準より下へ落ちているとき（穴・地下へ落下中）は基準を足元に合わせて追う。
"""
from __future__ import annotations

import pygame

import config


class Camera:
    def __init__(self, view_w: int, view_h: int, world_w: float, world_h: float,
                 bounds: tuple[float, float] | None = None):
        self.view_w = view_w
        self.view_h = view_h
        self.world_w = world_w
        self.world_h = world_h
        self.bounds = bounds
        self.x = 0.0
        self.y = 0.0
        self.follow_ratio = config.CAMERA["follow_x_ratio"]
        self.smoothing = config.CAMERA["smoothing"]
        self.keep_in_view_margin = config.CAMERA["keep_in_view_margin"]
        self.boost_timer = 0.0   # テレポート直後の高速追従
        self.anchor_y: float | None = None   # 縦の基準（最後に着地した足元の y）

    @property
    def max_x(self) -> float:
        return max(0.0, self.world_w - self.view_w)

    @property
    def vertical(self) -> bool:
        return self.bounds is not None

    @property
    def min_y(self) -> float:
        return self.bounds[0] if self.bounds else 0.0

    @property
    def max_y(self) -> float:
        if not self.bounds:
            return 0.0
        return max(self.bounds[0], self.bounds[1] - self.view_h)

    def _clamp(self) -> None:
        self.x = min(max(self.x, 0.0), self.max_x)
        # 縦の範囲の指定がなければ y は 0 に固定（v2.5 までと同じ）
        self.y = min(max(self.y, self.min_y), self.max_y) if self.bounds else 0.0

    def target_for(self, rect) -> float:
        return rect.centerx - self.view_w * self.follow_ratio

    def target_y_for(self, foot_y: float) -> float:
        return foot_y - self.view_h * config.CAMERA["follow_y_ratio"]

    def follow(self, rect, dt: float, grounded: bool = True) -> None:
        target = min(max(self.target_for(rect), 0.0), self.max_x)
        smoothing = self.smoothing
        boosted = self.boost_timer > 0
        if boosted:
            smoothing *= config.CAMERA["teleport_boost"]
            self.boost_timer = max(0.0, self.boost_timer - dt)
        t = min(1.0, smoothing * dt)
        self.x += (target - self.x) * t
        if self.bounds:
            if grounded or self.anchor_y is None or rect.bottom > self.anchor_y:
                self.anchor_y = rect.bottom
            ty = min(max(self.target_y_for(self.anchor_y), self.min_y), self.max_y)
            sy = config.CAMERA["smoothing_y"] * (config.CAMERA["teleport_boost"] if boosted else 1.0)
            self.y += (ty - self.y) * min(1.0, sy * dt)
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
        if self.bounds:
            top = config.CAMERA["keep_in_view_margin_top"]
            bottom = config.CAMERA["keep_in_view_margin_bottom"]
            if rect.top - self.y < top:
                self.y = rect.top - top
            elif rect.bottom - self.y > self.view_h - bottom:
                self.y = rect.bottom - (self.view_h - bottom)

    def snap_to(self, rect) -> None:
        self.x = self.target_for(rect)
        if self.bounds:
            self.anchor_y = rect.bottom
            self.y = self.target_y_for(rect.bottom)
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
