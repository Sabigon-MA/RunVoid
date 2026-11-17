"""見た目だけの簡易パーティクル（ゲームロジックには影響しない）。"""
from __future__ import annotations

import math
import random

import pygame

import config


class Particle:
    __slots__ = ("x", "y", "vx", "vy", "life", "max_life", "color", "size", "gravity")

    def __init__(self, x, y, vx, vy, life, color, size, gravity):
        self.x, self.y, self.vx, self.vy = x, y, vx, vy
        self.life = self.max_life = life
        self.color = color
        self.size = size
        self.gravity = gravity


class HomingParticle:
    """対象（.rect を持つオブジェクト）へ吸い寄せられる粒子。"""
    __slots__ = ("x", "y", "vx", "vy", "life", "target", "color", "size")

    def __init__(self, x, y, vx, vy, life, target, color, size):
        self.x, self.y, self.vx, self.vy = x, y, vx, vy
        self.life = life
        self.target = target
        self.color = color
        self.size = size


class _OffsetCamera:
    """エンティティを一時サーフェスへ描くためのカメラ代わり。"""

    def __init__(self, x: float, y: float):
        self.x, self.y = x, y


def render_entity(entity, pad: int = 16):
    """エンティティの見た目を透明サーフェスに描き、(サーフェス, 左上のワールド座標) を返す。"""
    box = entity.hurtbox
    w, h = int(box.w) + pad * 2, int(box.h) + pad * 2
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    ox, oy = box.x - pad, box.y - pad
    cam = _OffsetCamera(ox, oy)
    draw_body = getattr(entity, "_draw_body", None)
    if draw_body is not None:      # プレイヤー（無敵点滅・残像を除いた本体だけ）
        draw_body(surf, cam)
    else:
        entity.draw(surf, cam)
    return surf, ox, oy


def silhouette(entity, color, pad: int = 16):
    surf, ox, oy = render_entity(entity, pad)
    mask = pygame.mask.from_surface(surf)
    return mask.to_surface(setcolor=(*color, 255), unsetcolor=(0, 0, 0, 0)), ox, oy


def draw_outline(surface, entity, camera, color, alpha: int = 255, width: int = 2) -> None:
    """テレポート対象の輪郭発光（描画済みの見た目から輪郭を抽出する）。"""
    surf, ox, oy = render_entity(entity, 8)
    mask = pygame.mask.from_surface(surf)
    pts = mask.outline()
    if len(pts) < 3:
        return
    layer = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
    glow = mask.to_surface(setcolor=(*color, alpha // 4), unsetcolor=(0, 0, 0, 0))
    for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2)):
        layer.blit(glow, (dx, dy))
    pygame.draw.lines(layer, (*color, alpha), True, pts, width)
    surface.blit(layer, (ox - camera.x, oy - camera.y))


class Effects:
    MAX_PARTICLES = 400
    MAX_AFTERIMAGES = 12

    def __init__(self, seed: int | None = None):
        self.particles: list[Particle] = []
        self.homing: list[HomingParticle] = []
        self.rings: list[list] = []   # [x, y, 経過, 寿命, 最大半径, 色]
        self.afterimages: list[list] = []   # [サーフェス, x, y, 経過, 寿命]
        self.beams: list[list] = []         # [x1, y1, x2, y2, 経過, 寿命, 色]
        self.streaks: list[list] = []       # 画面座標 [x, y, 長さ, 速度, 経過, 寿命]（v2.3）
        self.locators: list[list] = []      # [対象, 経過, 寿命, 色]（v2.3）
        self._streak_cache: dict[int, pygame.Surface] = {}
        self.rng = random.Random(seed)

    # -- テレポート演出 ----------------------------------------------------
    def afterimage(self, entity, color, life: float) -> None:
        surf, ox, oy = silhouette(entity, color)
        self.afterimages.append([surf, ox, oy, 0.0, life])
        if len(self.afterimages) > self.MAX_AFTERIMAGES:
            del self.afterimages[0]

    def beam(self, x1, y1, x2, y2, color, life: float = 0.14) -> None:
        self.beams.append([x1, y1, x2, y2, 0.0, life, color])

    def teleport_depart(self, player, target, camera) -> None:
        """交換直前: 元の位置のシルエットを発光させ、そのまま残像として残す（描画のみ）。"""
        self.afterimage(player, (255, 170, 255), 0.28)
        self.afterimage(target, (200, 90, 255), 0.28)

    def teleport_arrive(self, before_player, before_target, player, target, color) -> None:
        """交換直後: 元の位置の粒子・到着地点の衝撃波・2点を結ぶ光（見た目のみ）。"""
        for r in (before_player, before_target):
            self.burst(r.centerx, r.centery, color, count=14, speed=170, life=0.35, size=2, gravity=0.0)
        for e in (player, target):
            box = e.hurtbox
            self.ring(box.centerx, box.centery, color, radius=34.0, life=0.22)
            self.burst(box.centerx, box.bottom - 2, (255, 210, 255), count=6, speed=90, life=0.2,
                       size=2, gravity=0.0)
        self.beam(before_player.centerx, before_player.centery,
                  before_target.centerx, before_target.centery, color)

    def teleport_camera_cue(self, camera_shift: float, view_w: int, view_h: int) -> None:
        """v2.3: テレポート直後のカメラの高速移動を「移動」として見せる流線（画面座標・見た目のみ）。

        camera_shift はこれからカメラが動く量（+ で右）。背景は逆向きに流れるので、線もその向きに流す。
        カメラ自体の動き（追従・照準・敵の更新範囲）は変えない。
        """
        p = config.TELEPORT_FX
        if not p["streaks"] or abs(camera_shift) < p["streak_min_shift"]:
            return
        rng = self.rng
        strength = min(1.0, abs(camera_shift) / 320.0)
        direction = -1.0 if camera_shift > 0 else 1.0
        for _ in range(int(6 + 10 * strength)):
            length = rng.uniform(50, 170) * (0.5 + 0.5 * strength)
            self.streaks.append([rng.uniform(-80, view_w + 80), rng.uniform(40, view_h - 60), length,
                                 direction * rng.uniform(900, 1700) * strength,
                                 0.0, p["streak_life"] * rng.uniform(0.7, 1.0)])

    def locator(self, entity, color, life: float | None = None) -> None:
        """v2.3: 到着した主人公の周りで外から縮むリング（移動先へ視線を誘導する。見た目のみ）。"""
        if config.TELEPORT_FX["locator"]:
            self.locators.append([entity, 0.0, config.TELEPORT_FX["locator_life"] if life is None else life,
                                  color])

    def _streak_image(self, length: int) -> pygame.Surface:
        key = max(8, int(length) // 8 * 8)
        img = self._streak_cache.get(key)
        if img is None:
            img = pygame.Surface((key, 2), pygame.SRCALPHA)
            for x in range(key):
                k = x / (key - 1)
                img.fill((255, 225, 245, int(150 * k * k)), (x, 0, 1, 2))
            self._streak_cache[key] = img
        return img

    def draw_screen_cues(self, surface: pygame.Surface) -> None:
        """背景・地形の後、キャラクターより前に描く画面座標の演出（流線）。"""
        for x, y, length, speed, age, life in self.streaks:
            img = self._streak_image(length)
            if speed < 0:   # 左へ流れる線は先端（明るい側）を左にする
                img = pygame.transform.flip(img, True, False)
            img.set_alpha(int(255 * (1.0 - age / life)))
            surface.blit(img, (x - img.get_width() / 2, y))

    def ring(self, x, y, color=(200, 130, 255), radius=18.0, life=0.15):
        """被弾時の小さな衝撃波。"""
        self.rings.append([x, y, 0.0, life, radius, color])

    def homing_burst(self, x, y, target, color=(205, 60, 170), count=8, speed=160.0, life=1.0, size=3):
        """撃破時にプレイヤーへ向かって飛ぶ粒子（見た目のみ。報酬は即時反映済み）。"""
        rng = self.rng
        for _ in range(count):
            a = rng.uniform(0, math.tau)
            s = rng.uniform(0.5, 1.0) * speed
            self.homing.append(HomingParticle(x, y, math.cos(a) * s, math.sin(a) * s,
                                              life, target, color, size))

    def burst(self, x, y, color, count=10, speed=180.0, life=0.4, size=3, gravity=400.0):
        rng = self.rng
        for _ in range(count):
            a = rng.uniform(0, math.tau)
            s = rng.uniform(0.3, 1.0) * speed
            self.particles.append(Particle(x, y, math.cos(a) * s, math.sin(a) * s,
                                           life * rng.uniform(0.6, 1.0), color, size, gravity))
        if len(self.particles) > self.MAX_PARTICLES:
            del self.particles[: len(self.particles) - self.MAX_PARTICLES]

    def update(self, dt: float) -> None:
        alive = []
        for p in self.particles:
            p.life -= dt
            if p.life <= 0:
                continue
            p.vy += p.gravity * dt
            p.x += p.vx * dt
            p.y += p.vy * dt
            alive.append(p)
        self.particles = alive

        homing = []
        for h in self.homing:
            h.life -= dt
            tx, ty = h.target.rect.center
            dx, dy = tx - h.x, ty - h.y
            dist = math.hypot(dx, dy)
            if h.life <= 0 or dist < 10:
                continue
            # 目標方向へ加速しつつ減衰（最初は散って、徐々に吸い込まれる）
            accel = 2600.0
            h.vx += dx / dist * accel * dt
            h.vy += dy / dist * accel * dt
            damp = max(0.0, 1.0 - 3.0 * dt)
            h.vx *= damp
            h.vy *= damp
            h.x += h.vx * dt
            h.y += h.vy * dt
            homing.append(h)
        self.homing = homing

        for r in self.rings:
            r[2] += dt
        self.rings = [r for r in self.rings if r[2] < r[3]]
        for a in self.afterimages:
            a[3] += dt
        self.afterimages = [a for a in self.afterimages if a[3] < a[4]]
        for b in self.beams:
            b[4] += dt
        self.beams = [b for b in self.beams if b[4] < b[5]]
        for s in self.streaks:
            s[0] += s[3] * dt
            s[4] += dt
        self.streaks = [s for s in self.streaks if s[4] < s[5]]
        for loc in self.locators:
            loc[1] += dt
        self.locators = [loc for loc in self.locators if loc[1] < loc[2] and getattr(loc[0], "alive", True)]

    def draw(self, surface: pygame.Surface, camera) -> None:
        w, h = surface.get_size()
        for img, x, y, age, life in self.afterimages:
            k = 1.0 - age / life
            img.set_alpha(int(220 * k))
            surface.blit(img, (x - camera.x, y - camera.y))
        for x1, y1, x2, y2, age, life, color in self.beams:
            k = 1.0 - age / life
            layer = pygame.Surface((w, h), pygame.SRCALPHA)
            a, b = (x1 - camera.x, y1 - camera.y), (x2 - camera.x, y2 - camera.y)
            pygame.draw.line(layer, (*color, int(90 * k)), a, b, max(1, int(10 * k)))
            pygame.draw.line(layer, (255, 230, 255, int(220 * k)), a, b, max(1, int(3 * k)))
            surface.blit(layer, (0, 0))
        for p in self.particles:
            sx, sy = p.x - camera.x, p.y - camera.y
            if -10 < sx < w + 10 and -10 < sy < h + 10:
                size = max(1, int(p.size * (p.life / p.max_life) + 0.5))
                pygame.draw.rect(surface, p.color, (sx, sy, size, size))
        for x, y, age, life, radius, color in self.rings:
            k = age / life
            rad = max(2, int(4 + (radius - 4) * k))
            width = max(1, int(3 * (1 - k)) + 1)
            pygame.draw.circle(surface, color, (x - camera.x, y - camera.y), rad, width)
        for hp in self.homing:
            sx, sy = hp.x - camera.x, hp.y - camera.y
            if -10 < sx < w + 10 and -10 < sy < h + 10:
                pygame.draw.rect(surface, hp.color, (sx - 1, sy - 1, hp.size, hp.size))
        for entity, age, life, color in self.locators:
            k = age / life
            cx, cy = entity.rect.centerx - camera.x, entity.rect.centery - camera.y
            rad = int(70 - 46 * (1 - (1 - k) ** 2))          # 70px → 24px（減速しながら縮む）
            width = 3 if k < 0.6 else 2
            pygame.draw.circle(surface, color, (cx, cy), rad, width)
            if k < 0.5:   # 内側の細い白線（到着直後だけ）
                pygame.draw.circle(surface, (255, 235, 255), (cx, cy), max(2, rad - 4), 1)
