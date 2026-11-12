"""追跡壁。

将来の分岐・変形・合流に備え、壁は複数の WallSegment の集合として管理する。
今回の試作では「画面全高を覆う右向きの垂直セグメント1枚」のみを使う。

即死判定は「セグメントの先端より後ろ側（飲み込まれた領域）」との交差で行う。
厚さ thickness は表示上の値で、判定は先端より後ろ全体に及ぶため、
高速移動で壁を飛び越える（通過する）ことはできない。
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import pygame

import config


@dataclass
class WallSegment:
    front_x: float
    top: float = -100000.0
    bottom: float = 100000.0
    direction: int = 1          # +1: 右へ進む（後方=左側が飲み込まれた領域）
    thickness: float = 32.0

    def advance(self, distance: float) -> None:
        self.front_x += self.direction * distance

    def intersects(self, rect) -> bool:
        if rect.bottom <= self.top or rect.top >= self.bottom:
            return False
        if self.direction > 0:
            return rect.left < self.front_x
        return rect.right > self.front_x

    def distance_to(self, rect) -> float:
        if self.direction > 0:
            return rect.left - self.front_x
        return self.front_x - rect.right


class ChasingWall:
    def __init__(self, start_x: float, speed: float, thickness: float):
        self.base_speed = speed
        self.speed_multiplier = 1.0   # 将来の一時加速用
        self.paused = False           # 将来のボス戦停止用
        self.thickness = thickness
        self.segments: list[WallSegment] = [WallSegment(front_x=start_x, thickness=thickness)]
        self._time = 0.0
        self._glow: pygame.Surface | None = None

    @property
    def speed(self) -> float:
        return self.base_speed * self.speed_multiplier

    @property
    def front_x(self) -> float:
        """先頭セグメントの先端X（試作では唯一のセグメント）。"""
        return self.segments[0].front_x

    def update(self, dt: float) -> None:
        self._time += dt
        if self.paused:
            return
        for seg in self.segments:
            seg.advance(self.speed * dt)

    # -- 判定 -------------------------------------------------------------
    def touches(self, rect) -> bool:
        return any(seg.intersects(rect) for seg in self.segments)

    def touches_swept(self, prev_rect, cur_rect) -> bool:
        """移動前後の矩形を包む領域で判定する（高速移動中の接触も拾う）。"""
        return self.touches(prev_rect.union(cur_rect))

    def distance_to(self, rect) -> float:
        return min(seg.distance_to(rect) for seg in self.segments)

    # -- 描画 -------------------------------------------------------------
    def _glow_surface(self, height: int) -> pygame.Surface:
        if self._glow is None or self._glow.get_height() != height:
            width = 80
            surf = pygame.Surface((width, height), pygame.SRCALPHA)
            r, g, b = config.COLORS["wall_glow"]
            for i in range(width):
                alpha = int(110 * (1 - i / width) ** 2)
                pygame.draw.line(surf, (r, g, b, alpha), (i, 0), (i, height))
            self._glow = surf
        return self._glow

    def draw(self, surface: pygame.Surface, camera) -> None:
        h = surface.get_height()
        t = self._time
        for seg in self.segments:
            fx = seg.front_x - camera.x
            if fx <= -seg.thickness - 40:
                continue
            core = config.COLORS["wall_core"]
            edge = config.COLORS["wall_edge"]
            # 光（先端の前方）
            surface.blit(self._glow_surface(h), (fx, 0))
            # 飲み込まれた領域
            if fx > 0:
                pygame.draw.rect(surface, core, (0, 0, int(fx) + 1, h))
            # うごめく先端
            pts_back = []
            pts_front = []
            for y in range(-16, h + 32, 16):
                wobble = (math.sin(t * 5.0 + y * 0.045) * 9
                          + math.sin(t * 11.0 + y * 0.13) * 5)
                pts_front.append((fx + wobble, y))
                pts_back.append((fx - seg.thickness + wobble * 0.5, y))
            poly = pts_back + list(reversed(pts_front))
            pygame.draw.polygon(surface, edge, poly)
            # 内側の暗い筋
            for i in range(0, h, 24):
                off = math.sin(t * 3 + i) * 6
                pygame.draw.line(surface, (60, 4, 8),
                                 (fx - seg.thickness - 30 + off, i),
                                 (fx - 6 + off, i + 18), 3)
            # 先端の赤い輪郭
            pygame.draw.lines(surface, (200, 40, 40), False, pts_front, 2)
