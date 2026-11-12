"""攻撃判定とダメージ処理。

v2.0: 主人公の直接攻撃（剣・弓など）は廃止。ここに残る判定形状は
敵の攻撃（AttachedAttack）・ボスの飛び道具（Projectile 派生）・将来の環境攻撃で使う。

攻撃はすべて Attack のサブクラスとして表現し、以下を管理する。
    damage / 範囲 / startup(発生) / active(持続) / owner(攻撃者) / target_team(攻撃対象)
クールダウンは攻撃を出す側（キャラクター）が管理する。

同じ攻撃が同じ対象に複数回当たらないよう、攻撃ごとに命中済み uid を記録する。
"""
from __future__ import annotations

import math

import pygame

from systems.collision import circle_rect_intersect, sector_rect_intersect


class Attack:
    single_hit = False   # True なら最初の命中で消える（矢など）

    def __init__(self, owner, damage: float, startup: float = 0.0, active: float = 0.1,
                 target_team: str = "enemy", hitstop_frames: int = 0,
                 stagger_duration: float = 0.0):
        self.owner = owner
        self.damage = damage
        self.startup = startup
        self.active = active
        self.target_team = target_team
        self.hitstop_frames = hitstop_frames   # 命中時に物理更新を止めるフレーム数
        self.stagger_duration = stagger_duration   # 命中した敵を怯ませる時間（秒）
        self.timer = 0.0
        self.hit_ids: set[int] = set()
        self.done = False

    def push_direction(self, target) -> int:
        """ノックバック方向（+1: 右 / -1: 左）。攻撃者から見て対象のいる側。"""
        ox = self.owner.hurtbox.centerx
        tx = target.hurtbox.centerx
        if abs(tx - ox) > 1e-6:
            return 1 if tx > ox else -1
        return getattr(self.owner, "facing", 1) or 1

    @property
    def is_active(self) -> bool:
        return self.startup < self.timer <= self.startup + self.active + 1e-9

    def advance(self, dt: float, terrain) -> None:
        self.timer += dt
        if self.timer >= self.startup + self.active - 1e-9:
            self.done = True

    def overlaps(self, rect) -> bool:
        raise NotImplementedError

    def extra_targets(self):
        """target_team 以外に命中判定する対象（ボス弾の自傷など）。"""
        return ()

    def damage_for(self, target) -> float:
        """対象ごとのダメージ（既定は一律）。"""
        return self.damage

    def draw(self, surface: pygame.Surface, camera) -> None:
        pass


class RectAttack(Attack):
    """攻撃者の前方に出る矩形判定（剣・短剣）。攻撃者に追従する。"""

    def __init__(self, owner, damage, direction: int, reach: float, height: float,
                 startup=0.0, active=0.1, color=(235, 220, 220), **kw):
        super().__init__(owner, damage, startup, active, **kw)
        self.direction = 1 if direction >= 0 else -1
        self.reach = reach
        self.height = height
        self.color = color
        self.rect = pygame.FRect(0, 0, reach, height)
        self._sync()

    def _sync(self) -> None:
        o = self.owner.rect
        self.rect.size = (self.reach, self.height)
        self.rect.centery = o.centery
        if self.direction > 0:
            self.rect.left = o.right - 4
        else:
            self.rect.right = o.left + 4

    def advance(self, dt, terrain):
        self._sync()
        super().advance(dt, terrain)

    def overlaps(self, rect) -> bool:
        return self.rect.colliderect(rect)

    def draw(self, surface, camera):
        if self.timer < self.startup:
            return
        progress = min(1.0, (self.timer - self.startup) / max(self.active, 1e-6))
        r = self.rect.move(-camera.x, -camera.y)
        cx = r.left if self.direction > 0 else r.right
        cy = r.centery
        radius = self.reach
        # 三日月形の斬撃
        start = -70 + 120 * progress
        pts_outer, pts_inner = [], []
        for i in range(9):
            a = math.radians(start - 60 + i * 15)
            ox = math.cos(a) * radius * self.direction
            oy = math.sin(a) * radius * 0.6
            pts_outer.append((cx + ox, cy + oy))
            pts_inner.append((cx + ox * 0.7, cy + oy * 0.7))
        poly = pts_outer + list(reversed(pts_inner))
        surf = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        pygame.draw.polygon(surf, (*self.color, 170), poly)
        surface.blit(surf, (0, 0))


class SectorAttack(Attack):
    """攻撃者中心の扇形判定（戦士の大剣）。"""

    def __init__(self, owner, damage, direction: int, radius: float, angle_deg: float,
                 startup=0.0, active=0.15, **kw):
        super().__init__(owner, damage, startup, active, **kw)
        self.direction_angle = 0.0 if direction >= 0 else math.pi
        self.radius = radius
        self.half_angle = math.radians(angle_deg) / 2
        self.origin = owner.rect.center

    def advance(self, dt, terrain):
        self.origin = self.owner.rect.center
        super().advance(dt, terrain)

    def overlaps(self, rect) -> bool:
        ox, oy = self.origin
        return sector_rect_intersect(ox, oy, self.radius, self.direction_angle,
                                     self.half_angle, rect)

    def draw(self, surface, camera):
        ox, oy = self.origin[0] - camera.x, self.origin[1] - camera.y
        fade = 1.0 - min(1.0, self.timer / max(self.startup + self.active, 1e-6))
        pts = [(ox, oy)]
        n = 16
        for i in range(n + 1):
            a = self.direction_angle - self.half_angle + 2 * self.half_angle * i / n
            pts.append((ox + math.cos(a) * self.radius, oy + math.sin(a) * self.radius))
        surf = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        pygame.draw.polygon(surf, (230, 60, 50, int(110 * fade + 40)), pts)
        pygame.draw.lines(surf, (255, 200, 180, int(220 * fade + 30)), False, pts[1:], 3)
        surface.blit(surf, (0, 0))


class Projectile(Attack):
    """直進する飛び道具（矢）。重力・距離減衰なし。地形に当たると消える。"""

    single_hit = True

    def __init__(self, owner, damage, x: float, y: float, dir_x: float, dir_y: float,
                 speed: float, max_range: float, width: float, color=(220, 210, 190), **kw):
        super().__init__(owner, damage, 0.0, 0.0, **kw)
        length = math.hypot(dir_x, dir_y) or 1.0
        self.dx, self.dy = dir_x / length, dir_y / length
        self.x, self.y = x, y
        self.prev = (x, y)
        self.speed = speed
        self.max_range = max_range
        self.width = width
        self.radius = width / 2
        self.traveled = 0.0
        self.color = color

    @property
    def is_active(self) -> bool:
        return True

    def push_direction(self, target) -> int:
        if abs(self.dx) > 1e-6:
            return 1 if self.dx > 0 else -1
        return super().push_direction(target)

    def advance(self, dt, terrain):
        self.timer += dt
        self.prev = (self.x, self.y)
        dist = min(self.speed * dt, self.max_range - self.traveled)
        step = 4.0
        n = max(1, math.ceil(dist / step))
        for i in range(1, n + 1):
            px = self.prev[0] + self.dx * dist * i / n
            py = self.prev[1] + self.dy * dist * i / n
            # 地形判定は矢の中心点で行う（太い矢が地面を擦って消えないように）
            if terrain is not None and terrain.point_in_solid(px, py):
                self.x, self.y = px, py
                self.done = True
                break
            self.x, self.y = px, py
        self.traveled += math.hypot(self.x - self.prev[0], self.y - self.prev[1])
        if self.traveled >= self.max_range - 1e-6:
            self.done = True

    def overlaps(self, rect) -> bool:
        px, py = self.prev
        seg = math.hypot(self.x - px, self.y - py)
        n = max(1, math.ceil(seg / max(2.0, min(self.radius, 6.0))))
        for i in range(n + 1):
            cx = px + (self.x - px) * i / n
            cy = py + (self.y - py) * i / n
            if circle_rect_intersect(cx, cy, self.radius, rect):
                return True
        return False

    def draw(self, surface, camera):
        x, y = self.x - camera.x, self.y - camera.y
        length = 26 + self.width * 0.5
        tail = (x - self.dx * length, y - self.dy * length)
        thickness = max(2, int(self.width / 4))
        if self.width > 12:
            glow = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
            pygame.draw.line(glow, (230, 80, 60, 90), tail, (x, y), int(self.width))
            surface.blit(glow, (0, 0))
        pygame.draw.line(surface, self.color, tail, (x, y), thickness)
        pygame.draw.circle(surface, (255, 240, 220), (x, y), max(2, thickness))


class AttachedAttack(Attack):
    """攻撃者に追従する任意形状の矩形判定（敵の飛びかかりなど）。

    get_rect() で毎フレーム判定矩形を取得し、keep_alive() が False になったら即座に消える。
    """

    def __init__(self, owner, damage, get_rect, active: float, keep_alive=None,
                 target_team: str = "player", **kw):
        super().__init__(owner, damage, 0.0, active, target_team=target_team, **kw)
        self.get_rect = get_rect
        self.keep_alive = keep_alive
        self.rect = get_rect()

    def _alive(self) -> bool:
        return self.owner.alive and (self.keep_alive is None or self.keep_alive())

    @property
    def is_active(self) -> bool:
        return self._alive() and super().is_active

    def advance(self, dt, terrain):
        self.rect = self.get_rect()
        super().advance(dt, terrain)
        if not self._alive():
            self.done = True

    def overlaps(self, rect) -> bool:
        return self.rect.colliderect(rect)


class CombatSystem:
    """アクティブな攻撃の更新と命中判定。"""

    def __init__(self):
        self.attacks: list[Attack] = []

    def spawn(self, attack: Attack) -> Attack:
        self.attacks.append(attack)
        return attack

    def clear(self) -> None:
        self.attacks.clear()

    def update(self, dt: float, terrain, targets_by_team: dict, on_hit=None) -> None:
        """targets_by_team: {"enemy": [...], "player": [...]}。

        対象は uid / hurtbox / alive / can_be_hit() / take_damage(amount, source) を持つこと。
        """
        for attack in self.attacks:
            attack.advance(dt, terrain)
            if not attack.is_active:
                continue
            targets = list(targets_by_team.get(attack.target_team, ()))
            targets.extend(attack.extra_targets())
            for target in targets:
                if not target.alive or target.uid in attack.hit_ids:
                    continue
                if not target.can_be_hit():
                    continue
                if attack.overlaps(target.hurtbox):
                    attack.hit_ids.add(target.uid)
                    killed = target.take_damage(attack.damage_for(target), attack)
                    if on_hit:
                        on_hit(attack, target, killed)
                    if attack.single_hit:
                        attack.done = True
                        break
        self.attacks = [a for a in self.attacks if not a.done]

    def draw(self, surface, camera) -> None:
        for a in self.attacks:
            a.draw(surface, camera)
