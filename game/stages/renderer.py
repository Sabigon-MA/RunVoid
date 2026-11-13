"""ステージの仮グラフィック描画（背景・地形・ゴール）。

外部画像を使わず pygame の描画機能だけで生成する。
重い描画は初期化時にサーフェスへ焼き込み、毎フレームは blit のみ行う。
"""
from __future__ import annotations

import logging
import math
import random

import pygame

import config
from stages.background import BackgroundAssetError, BackgroundConfig, build_background


def _vertical_gradient(w: int, h: int, stops: list[tuple[float, tuple[int, int, int]]]) -> pygame.Surface:
    surf = pygame.Surface((w, h))
    for y in range(h):
        t = y / max(1, h - 1)
        for i in range(len(stops) - 1):
            t0, c0 = stops[i]
            t1, c1 = stops[i + 1]
            if t0 <= t <= t1:
                k = (t - t0) / max(1e-6, t1 - t0)
                color = tuple(int(c0[j] + (c1[j] - c0[j]) * k) for j in range(3))
                pygame.draw.line(surf, color, (0, y), (w, y))
                break
    return surf


class ParallaxLayer:
    def __init__(self, surface: pygame.Surface, factor: float, y: int = 0):
        self.surface = surface
        self.factor = factor
        self.y = y

    def draw(self, target: pygame.Surface, camera_x: float) -> None:
        w = self.surface.get_width()
        offset = -(camera_x * self.factor) % w
        x = offset - w
        tw = target.get_width()
        while x < tw:
            target.blit(self.surface, (x, self.y))
            x += w


class TwilightRuinsBackground:
    """ステージ1「黄昏の廃王国」: 荒れた平原、枯草、遠くの廃城。"""

    def __init__(self, view_w: int, view_h: int, seed: int = 7):
        self.view_w, self.view_h = view_w, view_h
        rng = random.Random(seed)
        self.sky = _vertical_gradient(view_w, view_h, [
            (0.0, (28, 16, 36)),
            (0.45, (92, 38, 48)),
            (0.72, (178, 82, 48)),
            (1.0, (70, 34, 34)),
        ])
        # 沈む太陽
        sun = pygame.Surface((view_w, view_h), pygame.SRCALPHA)
        for r in range(140, 0, -10):
            a = int(10 + (140 - r) * 0.35)
            pygame.draw.circle(sun, (255, 140, 70, a), (int(view_w * 0.72), int(view_h * 0.62)), r)
        self.sky.blit(sun, (0, 0))
        self.layers = [
            ParallaxLayer(self._castle_layer(1600, view_h, rng), 0.08),
            ParallaxLayer(self._hill_layer(1400, view_h, rng, (52, 26, 34), 330, 40), 0.2),
            ParallaxLayer(self._hill_layer(1200, view_h, rng, (36, 20, 26), 375, 28), 0.4),
            ParallaxLayer(self._grass_layer(1000, view_h, rng), 0.65),
        ]
        self.ash = [(rng.uniform(0, view_w), rng.uniform(0, view_h), rng.uniform(8, 25),
                     rng.uniform(0, math.tau)) for _ in range(40)]
        self.time = 0.0

    @staticmethod
    def _castle_layer(w, h, rng):
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        color = (58, 30, 42)
        base = 360
        x = 300
        # 廃城のシルエット（崩れた塔と城壁）
        pygame.draw.rect(surf, color, (x, base - 60, 360, 60))
        for i, (tx, th, tw) in enumerate([(x + 10, 150, 40), (x + 120, 210, 52),
                                          (x + 230, 120, 36), (x + 300, 175, 44)]):
            pygame.draw.rect(surf, color, (tx, base - th, tw, th))
            # 崩れた頂部
            pts = [(tx, base - th)]
            for k in range(5):
                pts.append((tx + tw * (k + 0.5) / 5, base - th - rng.randint(0, 22)))
            pts.append((tx + tw, base - th))
            pygame.draw.polygon(surf, color, pts)
            # 窓
            pygame.draw.rect(surf, (120, 50, 40), (tx + tw // 2 - 3, base - th + 30, 6, 12))
        for k in range(18):  # 城壁の狭間
            pygame.draw.rect(surf, color, (x + k * 20, base - 72, 10, 12))
        # 遠くの小さな廃墟
        for _ in range(4):
            rx = rng.randint(800, w - 100)
            rh = rng.randint(30, 80)
            pygame.draw.rect(surf, color, (rx, base - rh, rng.randint(14, 30), rh))
        pygame.draw.rect(surf, color, (0, base, w, h - base))
        return surf

    @staticmethod
    def _hill_layer(w, h, rng, color, base, amp):
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        pts = [(0, h)]
        phase1, phase2 = rng.uniform(0, 6), rng.uniform(0, 6)
        for x in range(0, w + 1, 20):
            t = x / w * math.tau
            y = base - amp * (0.6 * math.sin(t * 2 + phase1) + 0.4 * math.sin(t * 5 + phase2))
            pts.append((x, y))
        pts.append((w, h))
        pygame.draw.polygon(surf, color, pts)
        # 枯れ木
        for _ in range(3):
            tx = rng.randint(40, w - 40)
            ty = base + 10
            pygame.draw.line(surf, color, (tx, ty), (tx, ty - 50), 3)
            pygame.draw.line(surf, color, (tx, ty - 35), (tx - 16, ty - 55), 2)
            pygame.draw.line(surf, color, (tx, ty - 28), (tx + 14, ty - 46), 2)
        return surf

    @staticmethod
    def _grass_layer(w, h, rng):
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        base = 418
        # 地面より下は奈落として暗く落とし込む（穴が足場と見分けられるように）
        for y in range(base, h):
            k = min(1.0, (y - base) / 40)
            col = (int(46 * (1 - k) + 4 * k), int(28 * (1 - k) + 2 * k), int(26 * (1 - k) + 4 * k))
            pygame.draw.line(surf, col, (0, y), (w, y))
        for _ in range(260):
            x = rng.uniform(0, w)
            length = rng.uniform(8, 26)
            lean = rng.uniform(-6, 6)
            pygame.draw.line(surf, (86, 58, 40), (x, base + 2), (x + lean, base - length), 1)
        return surf

    def update(self, dt: float) -> None:
        self.time += dt

    def draw(self, surface: pygame.Surface, camera_x: float) -> None:
        surface.blit(self.sky, (0, 0))
        for layer in self.layers:
            layer.draw(surface, camera_x)
        # 舞い散る灰
        t = self.time
        for (x, y, spd, ph) in self.ash:
            ax = (x - camera_x * 0.3 + math.sin(t + ph) * 12) % self.view_w
            ay = (y + t * spd) % self.view_h
            pygame.draw.rect(surface, (190, 150, 130), (ax, ay, 2, 2))


BACKGROUNDS = {"twilight_ruins": TwilightRuinsBackground}


def make_background(theme: str, view_w: int, view_h: int, background: BackgroundConfig | None = None):
    """背景を作る。画像背景の設定があればそれを使い、画像の欠落・破損時だけ手続き背景へ戻す。"""
    if background is not None:
        try:
            return build_background(background, view_w, view_h)
        except BackgroundAssetError as exc:
            logging.getLogger("runvoid.background").warning(
                "%s -> 手続き背景 '%s' で続行します", exc, theme)
    cls = BACKGROUNDS.get(theme, TwilightRuinsBackground)
    return cls(view_w, view_h)


def find_pits(rects, world_width: float, view_h: int) -> list[tuple[int, int, int]]:
    """画面下端まで届く固体地形の切れ目（= 穴）を (左x, 右x, 上端y) で返す。描画専用。

    上端は両隣の地面の上面のうち高い方（小さい y）。ステージ両端の外側は穴として扱わない。
    """
    floor = sorted((r for r in rects if r.bottom >= view_h), key=lambda r: r.left)
    pits = []
    covered = 0
    prev = None
    for r in floor:
        if r.left > covered and prev is not None:
            pits.append((int(covered), int(r.left), int(min(prev.top, r.top))))
        if r.right > covered:
            covered, prev = r.right, r
    return [p for p in pits if 0 < p[0] < p[1] < world_width]


class TerrainRenderer:
    """地形・一方通行足場・ゴールの描画。各地形は初期化時にサーフェス化する。"""

    def __init__(self, stage, seed: int = 3):
        rng = random.Random(seed)
        rects = [r.to_rect() for r in stage.platforms]
        self.pits = find_pits(rects, stage.world_width, stage.resolution[1])
        lefts = {x1 for _, x1, _ in self.pits}     # 穴の右端 = 右側の地面の左面
        rights = {x0 for x0, _, _ in self.pits}    # 穴の左端 = 左側の地面の右面
        self.solids = [(rect, self._bake_ground(r, rng, rect.left in lefts, rect.right in rights))
                       for r, rect in zip(stage.platforms, rects)]
        self.one_ways = [(r.to_rect(), self._bake_one_way(r, rng)) for r in stage.one_way_platforms]
        self.pit_images = [(x0, top, self._bake_pit(x1 - x0, stage.resolution[1] - top))
                           for x0, x1, top in self.pits]
        self.goal_x = stage.goal_x
        self.time = 0.0

    @staticmethod
    def _bake_pit(w: int, h: int) -> pygame.Surface:
        """v2.3: 穴の内部。上は黒く、底に向かって赤く光る（地面の暗灰色と色相で区別する）。描画のみ。"""
        surf = pygame.Surface((max(1, int(w)), max(1, int(h))))
        base = (5, 2, 5)
        glow = config.COLORS["pit_glow"]
        a_max = config.VISIBILITY["pit_glow_alpha"] / 255
        for y in range(surf.get_height()):
            k = y / max(1, surf.get_height() - 1)
            g = a_max * max(0.0, (k - 0.25) / 0.75) ** 1.6
            surf.fill(tuple(int(base[i] + (glow[i] - base[i]) * g) for i in range(3)), (0, y, w, 1))
        # 両側の壁面の影（奥行き）
        for i in range(6):
            shade = (0, 0, 0, int(150 * (1 - i / 6)))
            layer = pygame.Surface((1, surf.get_height()), pygame.SRCALPHA)
            layer.fill(shade)
            surf.blit(layer, (i, 0))
            surf.blit(layer, (surf.get_width() - 1 - i, 0))
        return surf

    @staticmethod
    def _bake_ground(r, rng, left_edge: bool = False, right_edge: bool = False) -> pygame.Surface:
        w, h = int(r.w), int(r.h)
        surf = pygame.Surface((w, h + 24), pygame.SRCALPHA)
        top = 24
        pygame.draw.rect(surf, config.COLORS["ground"], (0, top, w, h))
        pygame.draw.rect(surf, config.COLORS["ground_top"], (0, top, w, 6))
        # 石と亀裂
        for _ in range(w // 40):
            x = rng.randint(0, max(1, w - 20))
            y = rng.randint(top + 14, top + h - 10)
            pygame.draw.rect(surf, (44, 34, 36), (x, y, rng.randint(8, 22), rng.randint(4, 9)))
        # 枯草
        for _ in range(w // 6):
            x = rng.uniform(0, w)
            length = rng.uniform(5, 18)
            lean = rng.uniform(-5, 5)
            col = config.COLORS["grass"] if rng.random() < 0.6 else (90, 74, 50)
            pygame.draw.line(surf, col, (x, top + 2), (x + lean, top - length), 1)
        # 側面の縁取り
        pygame.draw.line(surf, (20, 14, 16), (0, top), (0, top + h), 2)
        pygame.draw.line(surf, (20, 14, 16), (w - 1, top), (w - 1, top + h), 2)
        # v2.3: 穴に面した側面は明るい石の縁にする（上ほど明るく、下へ地面の色に溶ける）。描画のみ
        ew = config.VISIBILITY["ground_edge_width"]
        if ew > 0:
            edge, ground = config.COLORS["ground_edge"], config.COLORS["ground"]
            for side, on in ((0, left_edge), (1, right_edge)):
                if not on:
                    continue
                for y in range(h):
                    k = max(0.0, 1.0 - y / 70) if y > 6 else 1.0
                    col = tuple(int(ground[i] + (edge[i] - ground[i]) * k) for i in range(3))
                    x0 = 0 if side == 0 else w - ew
                    pygame.draw.line(surf, col, (x0, top + y), (x0 + ew - 1, top + y))
                # 角の欠けた石（縁の位置を上面でも示す）
                cx = 0 if side == 0 else w - 10
                pygame.draw.rect(surf, edge, (cx, top - 2, 10, 4))
        return surf

    @staticmethod
    def _bake_one_way(r, rng) -> pygame.Surface:
        w, h = int(r.w), int(r.h)
        surf = pygame.Surface((w, h + 60), pygame.SRCALPHA)
        # 崩れかけた石橋
        pygame.draw.rect(surf, config.COLORS["platform"], (0, 0, w, h))
        pygame.draw.rect(surf, config.COLORS["platform_top"], (0, 0, w, 3))
        for x in range(0, w, 32):
            pygame.draw.line(surf, (40, 32, 30), (x, 0), (x, h), 1)
        # 下に垂れる朽ちた布と鎖
        for _ in range(max(1, w // 64)):
            x = rng.randint(8, max(9, w - 16))
            ln = rng.randint(18, 50)
            pygame.draw.polygon(surf, (70, 20, 24),
                                [(x, h), (x + 10, h), (x + 7, h + ln), (x + 2, h + ln - 8)])
        return surf

    def update(self, dt: float) -> None:
        self.time += dt

    def draw(self, surface: pygame.Surface, camera) -> None:
        view = camera.view_rect.inflate(64, 64)
        for x0, top, img in self.pit_images:
            if view.colliderect(pygame.Rect(x0, top, img.get_width(), img.get_height())):
                surface.blit(img, (x0 - camera.x, top - camera.y))
        for rect, img in self.solids:
            if view.colliderect(rect):
                surface.blit(img, (rect.x - camera.x, rect.y - 24 - camera.y))
        for rect, img in self.one_ways:
            if view.colliderect(rect.inflate(0, 120)):
                surface.blit(img, (rect.x - camera.x, rect.y - camera.y))
        # ゴール地点: 光る石碑
        gx = self.goal_x - camera.x
        if -60 < gx < surface.get_width() + 60:
            pulse = 0.5 + 0.5 * math.sin(self.time * 3)
            glow = pygame.Surface((80, 300), pygame.SRCALPHA)
            for i in range(40):
                a = int((40 - i) * 2.2 * (0.6 + 0.4 * pulse))
                pygame.draw.line(glow, (255, 210, 140, a), (40 - i, 0), (40 - i, 300))
                pygame.draw.line(glow, (255, 210, 140, a), (40 + i, 0), (40 + i, 300))
            surface.blit(glow, (gx - 40 - 12, 122))
            pygame.draw.rect(surface, (30, 24, 28), (gx - 22, 330, 20, 92))
            pygame.draw.polygon(surface, (30, 24, 28), [(gx - 26, 330), (gx - 12, 312), (gx + 2, 330)])
            pygame.draw.rect(surface, (255, 200, 120), (gx - 15, 350, 6, 20))
