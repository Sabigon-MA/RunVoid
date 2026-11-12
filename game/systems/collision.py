"""地形との衝突判定と幾何ユーティリティ。

- 静的地形は SpatialGrid に登録し、移動体の周辺だけを問い合わせる。
- 移動は collision_step 以下の距離に分割して軸ごとに解決するため、
  ダッシュやブリンクなどの高速移動でも地形をすり抜けない。
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import pygame

import config


class SpatialGrid:
    """固定サイズのセルで矩形を管理する簡易空間分割。"""

    def __init__(self, cell_size: int = 128):
        self.cell_size = cell_size
        self._cells: dict[tuple[int, int], list] = {}

    def _cell_range(self, rect):
        cs = self.cell_size
        x0 = int(math.floor(rect.left / cs))
        x1 = int(math.floor((rect.right - 1e-6) / cs))
        y0 = int(math.floor(rect.top / cs))
        y1 = int(math.floor((rect.bottom - 1e-6) / cs))
        for cx in range(x0, x1 + 1):
            for cy in range(y0, y1 + 1):
                yield cx, cy

    def insert(self, rect: pygame.FRect) -> None:
        for key in self._cell_range(rect):
            self._cells.setdefault(key, []).append(rect)

    def query(self, rect) -> list[pygame.FRect]:
        found: list[pygame.FRect] = []
        seen: set[int] = set()
        for key in self._cell_range(rect):
            for item in self._cells.get(key, ()):
                if id(item) not in seen:
                    seen.add(id(item))
                    found.append(item)
        return found


@dataclass
class MoveResult:
    hit_left: bool = False
    hit_right: bool = False
    hit_ceiling: bool = False
    landed: bool = False
    landed_on_one_way: bool = False

    @property
    def hit_x(self) -> bool:
        return self.hit_left or self.hit_right


class Terrain:
    """ステージの静的地形（通常地形 + 一方通行足場）。"""

    def __init__(self, solids, one_ways, cell_size: int = 128, step: float | None = None):
        self.solids: list[pygame.FRect] = [pygame.FRect(r) for r in solids]
        self.one_ways: list[pygame.FRect] = [pygame.FRect(r) for r in one_ways]
        self.step = step if step is not None else config.PHYSICS["collision_step"]
        self._solid_grid = SpatialGrid(cell_size)
        self._one_way_grid = SpatialGrid(cell_size)
        for r in self.solids:
            self._solid_grid.insert(r)
        for r in self.one_ways:
            self._one_way_grid.insert(r)

    # -- 問い合わせ -------------------------------------------------------
    def solids_near(self, rect) -> list[pygame.FRect]:
        return self._solid_grid.query(rect)

    def one_ways_near(self, rect) -> list[pygame.FRect]:
        return self._one_way_grid.query(rect)

    def overlaps_solid(self, rect) -> bool:
        return any(rect.colliderect(s) for s in self.solids_near(rect))

    def point_in_solid(self, x: float, y: float) -> bool:
        probe = pygame.FRect(x - 0.5, y - 0.5, 1.0, 1.0)
        return self.overlaps_solid(probe)

    def has_ground_at(self, x: float, foot_y: float, include_one_way: bool = True) -> bool:
        """足元 (x, foot_y) の直下に立てる面があるか（敵の崖判定用）。"""
        probe = pygame.FRect(x - 0.05, foot_y, 0.1, 4.0)
        if self.overlaps_solid(probe):
            return True
        if include_one_way:
            for p in self.one_ways_near(probe):
                if probe.colliderect(p) and abs(p.top - foot_y) <= 1.0:
                    return True
        return False

    def ground_state(self, rect, ignore_one_way: bool = False) -> tuple[bool, bool]:
        """(接地しているか, 一方通行足場だけに乗っているか) を返す。"""
        probe = pygame.FRect(rect.left, rect.bottom, rect.width, 1.0)
        for s in self.solids_near(probe):
            if probe.colliderect(s):
                return True, False
        if not ignore_one_way:
            for p in self.one_ways_near(probe):
                if probe.colliderect(p) and abs(p.top - rect.bottom) <= 0.5:
                    return True, True
        return False, False

    # -- 移動 -------------------------------------------------------------
    def move(self, rect: pygame.FRect, dx: float, dy: float,
             ignore_one_way: bool = False) -> MoveResult:
        """rect を (dx, dy) 動かし、地形に当たった軸の移動を止める（rect を直接書き換える）。"""
        res = MoveResult()
        dist = max(abs(dx), abs(dy))
        if dist == 0:
            return res
        steps = max(1, math.ceil(dist / self.step))
        sx, sy = dx / steps, dy / steps
        region = rect.union(rect.move(dx, dy)).inflate(4, 4)
        solids = self.solids_near(region)
        one_ways = [] if ignore_one_way else self.one_ways_near(region)

        for _ in range(steps):
            if sx:
                rect.x += sx
                for s in solids:
                    if rect.colliderect(s):
                        if sx > 0:
                            rect.right = s.left
                            res.hit_right = True
                        else:
                            rect.left = s.right
                            res.hit_left = True
                if res.hit_x:
                    sx = 0.0
            if sy:
                prev_bottom = rect.bottom
                rect.y += sy
                blocked = False
                for s in solids:
                    if rect.colliderect(s):
                        if sy > 0:
                            rect.bottom = s.top
                            res.landed = True
                        else:
                            rect.top = s.bottom
                            res.hit_ceiling = True
                        blocked = True
                if sy > 0 and not blocked:
                    for p in one_ways:
                        if (prev_bottom <= p.top + 0.01 and rect.bottom > p.top
                                and rect.right > p.left and rect.left < p.right):
                            rect.bottom = p.top
                            res.landed = True
                            res.landed_on_one_way = True
                            blocked = True
                            break
                if blocked:
                    sy = 0.0
            if not sx and not sy:
                break
        return res


# ---------------------------------------------------------------------------
# 幾何ユーティリティ
# ---------------------------------------------------------------------------
def circle_rect_intersect(cx: float, cy: float, radius: float, rect) -> bool:
    nx = min(max(cx, rect.left), rect.right)
    ny = min(max(cy, rect.top), rect.bottom)
    return (cx - nx) ** 2 + (cy - ny) ** 2 <= radius * radius


def _angle_diff(a: float, b: float) -> float:
    d = (a - b + math.pi) % (2 * math.pi) - math.pi
    return abs(d)


def sector_rect_intersect(ox: float, oy: float, radius: float, direction: float,
                          half_angle: float, rect, samples: int = 5) -> bool:
    """扇形（中心 o、半径、向き direction[rad]、半角 half_angle[rad]）と矩形の交差判定。

    矩形内のサンプル点 + 中心に最も近い点のいずれかが扇形内にあれば交差とみなす。
    """
    if rect.collidepoint(ox, oy):
        return True
    points = [(min(max(ox, rect.left), rect.right), min(max(oy, rect.top), rect.bottom))]
    for i in range(samples):
        for j in range(samples):
            px = rect.left + rect.width * i / (samples - 1)
            py = rect.top + rect.height * j / (samples - 1)
            points.append((px, py))
    r2 = radius * radius
    for px, py in points:
        dx, dy = px - ox, py - oy
        if dx * dx + dy * dy > r2:
            continue
        if _angle_diff(math.atan2(dy, dx), direction) <= half_angle:
            return True
    return False


def approach(value: float, target: float, delta: float) -> float:
    if value < target:
        return min(value + delta, target)
    return max(value - delta, target)
