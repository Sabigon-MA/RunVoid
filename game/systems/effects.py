"""見た目だけの簡易パーティクル（ゲームロジックには影響しない）。"""
from __future__ import annotations

import math
import random

import pygame


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
