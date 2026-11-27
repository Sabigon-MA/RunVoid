"""雑魚敵「影翔け」（v3.0）。空を飛ぶ。

行動サイクル:
    HOVER / CHASE → WINDUP(0.45秒) → SWOOP(最大0.75秒) → RECOVERY(0.5秒) → RETURN → COOLDOWN(0.6秒) → 再行動

- 重力を受けない。配置された高さ（foot_y）を基準の高さ home_y として、左右に巡回する。
- 主人公が「下方向の射程」（水平 140px 以内、上下は自分の中心から −24〜+220px）に入ると予備動作に入る。
  予備動作の開始時に主人公の中心へ向かう方向と距離を決め、以降は追尾しない（影這いの飛びかかりと同じ考え方）。
  急降下はその点を 24px 越えたところで止まるので、予備動作の間に動けばかわせる。
- 急降下は地形に当たった時点で終わる（地形を貫通しない）。すり抜け足場は無視して飛ぶ。
- 急降下の後は硬直し、元の高さ・巡回の範囲へ戻ってから次の行動に移る。
- 発見して追いかけるのは水平方向だけで、初期位置から chase_leash より離れない。
- テレポート: 交換後の位置を新しい基準（home_x, home_y）にする。落下はしない。
  予備動作・急降下中に交換された場合は攻撃を中断して硬直に入る。
  主人公は影翔けのいた空中に出るので、穴や城門の上の「空中の足場」として使える。
- 上下の揺れ（羽ばたき）は見た目だけで、当たり判定は動かさない（照準が揺れないように）。
"""
from __future__ import annotations

import math
from enum import Enum, auto

import pygame

import config
from enemies.base import Enemy
from enemies.shadow_crawler import _halo
from systems.combat import AttachedAttack

EPS = 1e-6


class FlierState(Enum):
    HOVER = auto()
    CHASE = auto()
    WINDUP = auto()
    SWOOP = auto()
    RECOVERY = auto()
    RETURN = auto()
    COOLDOWN = auto()
    STAGGER = auto()


class ShadowFlier(Enemy):
    TYPE = "shadow_flier"

    def __init__(self, x: float, foot_y: float, enemy_id: str = "", params: dict | None = None):
        p = dict(config.ENEMIES[self.TYPE])
        if params:
            p.update(params)
        super().__init__(x, foot_y, p["body_w"], p["body_h"], p["hp"], p["contact_damage"], enemy_id,
                         knockback_speed=p["knockback_speed"], knockback_time=p["knockback_time"],
                         stagger_resistance=p["stagger_resistance"],
                         stagger_immunity=p["stagger_immunity"],
                         gravity=0.0, max_fall_speed=0.0)
        self.params = p
        self.home_y = float(foot_y)
        self.speed = p["speed"]
        self.detect_range = p["detect_range"]
        self.patrol_range = p["patrol_range"]
        self.state = FlierState.HOVER
        self.state_time = 0.0
        self.swoop_dir = (0.0, 1.0)
        self.swoop_duration = p["swoop_time"]
        self.attack_lock = 0.0
        self.facing = -1

    # ------------------------------------------------------------------
    @property
    def flying(self) -> bool:
        return True

    def _enter(self, state: FlierState) -> None:
        self.state = state
        self.state_time = 0.0

    def _apply_gravity(self, dt: float, terrain) -> None:
        """飛行するので落下しない（基底クラスの落下処理を無効にする）。"""
        self.vy = 0.0
        self.airborne = False

    def _sees_player(self, player) -> bool:
        if player is None or not player.alive:
            return False
        cx, cy = self.center
        px, py = player.rect.center
        return math.hypot(px - cx, py - cy) <= self.detect_range

    def _in_attack_range(self, player) -> bool:
        p = self.params
        cx, cy = self.center
        px, py = player.rect.center
        dy = py - cy
        return abs(px - cx) <= p["attack_range_x"] and p["attack_below_min"] <= dy <= p["attack_below_max"]

    def on_stagger(self) -> None:
        self._enter(FlierState.STAGGER)

    def on_teleported(self, world) -> None:
        super().on_teleported(world)
        self.home_y = self.foot_y
        self.airborne = False
        if self.state in (FlierState.WINDUP, FlierState.SWOOP):
            self._enter(FlierState.RECOVERY)
            self.attack_lock = self.params["recovery_time"] + self.params["cooldown_time"]
        elif self.state == FlierState.RETURN:
            self._enter(FlierState.HOVER)

    def swoop_hitbox(self) -> pygame.FRect:
        return self.body_rect.inflate(6, 6)

    # -- 移動（地形は貫通しない。すり抜け足場は無視する） ---------------------
    def _fly(self, dx: float, dy: float, terrain):
        body = self.body_rect
        res = terrain.move(body, dx, dy, ignore_one_way=True)
        self.x = body.centerx
        self.foot_y = body.bottom
        return res

    # ------------------------------------------------------------------
    def update(self, dt: float, world) -> None:
        super().update(dt, world)   # 点滅・怯みタイマー・ノックバック（落下はしない）
        self.state_time += dt
        self.attack_lock = max(0.0, self.attack_lock - dt)
        terrain = world.terrain
        player = world.player
        p = self.params
        st = self.state

        if st == FlierState.STAGGER:
            if not self.is_staggered:
                self._enter(FlierState.RETURN)
            return

        if st in (FlierState.HOVER, FlierState.CHASE):
            sees = self._sees_player(player)
            if sees and self.attack_lock <= EPS and self._in_attack_range(player):
                cx, cy = self.center
                px, py = player.rect.center
                d = math.hypot(px - cx, py - cy) or 1.0
                self.swoop_dir = ((px - cx) / d, (py - cy) / d)
                # 狙った点を少し越えるまで（最大 swoop_time）。主人公が動けば外れる
                self.swoop_duration = min(p["swoop_time"], (d + p["swoop_overshoot"]) / p["swoop_speed"])
                if abs(px - cx) > EPS:
                    self.facing = 1 if px > cx else -1
                self._enter(FlierState.WINDUP)
                return
            wanted = FlierState.CHASE if sees else FlierState.HOVER
            if wanted != st:
                self._enter(wanted)
            self._move(dt, player, terrain)

        elif st == FlierState.WINDUP:
            if self.state_time >= p["windup_time"] - EPS:
                self._enter(FlierState.SWOOP)
                world.combat.spawn(AttachedAttack(
                    self, p["swoop_damage"], self.swoop_hitbox, p["swoop_time"],
                    keep_alive=lambda: self.alive and self.state == FlierState.SWOOP))

        elif st == FlierState.SWOOP:
            sp = p["swoop_speed"] * dt
            res = self._fly(self.swoop_dir[0] * sp, self.swoop_dir[1] * sp, terrain)
            if res.hit_x or res.landed or res.hit_ceiling or self.state_time >= self.swoop_duration - EPS:
                self._enter(FlierState.RECOVERY)
                self.attack_lock = p["recovery_time"] + p["cooldown_time"]

        elif st == FlierState.RECOVERY:
            if self.state_time >= p["recovery_time"] - EPS:
                self._enter(FlierState.RETURN)

        elif st == FlierState.RETURN:
            self._return(dt, terrain)

        elif st == FlierState.COOLDOWN:
            if self.state_time >= p["cooldown_time"] - EPS:
                self._enter(FlierState.CHASE if self._sees_player(player) else FlierState.HOVER)

    def _return(self, dt: float, terrain) -> None:
        """元の高さへ戻る。先に高さを戻し、巡回の範囲の外にいれば水平にも戻る。"""
        step = self.params["return_speed"] * dt
        dy = self.home_y - self.foot_y
        lo, hi = self.home_x - self.patrol_range, self.home_x + self.patrol_range
        tx = min(max(self.x, lo), hi)
        dx = tx - self.x
        mvy = max(-step, min(step, dy))
        mvx = max(-step, min(step, dx)) if abs(dy) < 1.0 else 0.0
        res = self._fly(mvx, mvy, terrain)
        blocked = (mvy and (res.hit_ceiling or res.landed)) or (mvx and res.hit_x)
        if (abs(self.home_y - self.foot_y) < 0.5 and abs(tx - self.x) < 0.5) or blocked:
            if abs(self.home_y - self.foot_y) < 0.5:
                self.foot_y = self.home_y
            self._enter(FlierState.COOLDOWN)

    def _move(self, dt, player, terrain) -> None:
        if self.state == FlierState.CHASE:
            dx = player.rect.centerx - self.x
            direction = 0 if abs(dx) < 4 else (1 if dx > 0 else -1)
            leash = self.params["chase_leash"]
            if direction and abs(self.x + direction * self.speed * dt - self.home_x) > leash:
                direction = 0
        else:
            if self.x >= self.home_x + self.patrol_range:
                self.facing = -1
            elif self.x <= self.home_x - self.patrol_range:
                self.facing = 1
            direction = self.facing
        if direction == 0:
            return
        self.facing = direction
        res = self._fly(direction * self.speed * dt, 0.0, terrain)
        if res.hit_x and self.state == FlierState.HOVER:
            self.facing = -direction

    # ------------------------------------------------------------------
    def draw(self, surface: pygame.Surface, camera) -> None:
        t = self.anim_time
        st = self.state
        f = self.facing
        p = self.params
        # 羽ばたきによる上下の揺れ（見た目のみ）
        flap_speed = 16.0 if st in (FlierState.CHASE, FlierState.RETURN) else 11.0
        bob = 0.0 if st in (FlierState.SWOOP, FlierState.STAGGER) else math.sin(t * flap_speed * 0.5) * 2.5
        cx = self.x - camera.x
        cy = self.foot_y - self.height / 2 - camera.y + bob
        shake = 0.0
        wing_up = math.sin(t * flap_speed)            # -1（下）〜 1（上）
        fold = 0.0
        if st == FlierState.WINDUP:
            k = min(1.0, self.state_time / p["windup_time"])
            shake = math.sin(t * 70) * 1.5 * k
            wing_up = 1.0                              # 翼を高く掲げて溜める
        elif st == FlierState.SWOOP:
            fold = 1.0                                 # 翼をたたんで突っ込む
        elif st == FlierState.RECOVERY:
            wing_up = -0.6
        cx += shake

        if self.hurt_flash > 0:
            body_col = (200, 170, 230) if int(self.hurt_flash * 40) % 2 == 0 else (90, 50, 120)
        else:
            body_col = config.COLORS["silhouette"]
        bw, bh = 20, 14
        body = pygame.Rect(0, 0, bw, bh)
        body.center = (int(cx), int(cy + 2))
        head = pygame.Rect(0, 0, 12, 10)
        head.center = (int(cx + f * 9), int(cy - 1))

        # 翼（左右）。たたむと体に沿う
        span = 16 * (1 - 0.7 * fold)
        tip_y = cy - 2 - wing_up * 9 * (1 - fold)
        wings = []
        for side in (-1, 1):
            root = (cx + side * 4, cy)
            tip = (cx + side * (6 + span), tip_y)
            back = (cx + side * (4 + span * 0.55), cy + 6 - wing_up * 2)
            wings.append([root, tip, back])

        vis = config.VISIBILITY
        if vis["enemy_halo_alpha"] > 0:
            halo = _halo(bw + 36, bh + 26, vis["enemy_halo_alpha"])
            surface.blit(halo, (cx - halo.get_width() / 2, cy - halo.get_height() / 2))
        rim = vis["enemy_rim_width"]
        if rim > 0:
            rim_col = config.COLORS["enemy_rim"]
            for w in wings:
                pygame.draw.polygon(surface, rim_col, w, 0)
                pygame.draw.polygon(surface, rim_col, w, rim * 2)
            pygame.draw.ellipse(surface, rim_col, body.inflate(rim * 2, rim * 2))
            pygame.draw.ellipse(surface, rim_col, head.inflate(rim * 2, rim * 2))
        for w in wings:
            pygame.draw.polygon(surface, config.COLORS["flier_wing"], w)
            mid = [(w[0][0] * 0.5 + w[1][0] * 0.5, w[0][1] * 0.5 + w[1][1] * 0.5), w[1], w[2]]
            pygame.draw.polygon(surface, config.COLORS["flier_membrane"], mid)
        pygame.draw.ellipse(surface, body_col, body)
        pygame.draw.ellipse(surface, body_col, head)
        # 垂れた尾（朽ちた布）
        tail_x = cx - f * 9
        pygame.draw.polygon(surface, (52, 36, 34), [
            (tail_x - 3, cy + 3), (tail_x + 3, cy + 3),
            (tail_x - f * 6 + math.sin(t * 6) * 2, cy + 11)])
        # 紫に光る目
        ex, ey = head.centerx + f * 2, head.centery - 1
        strong = st in (FlierState.WINDUP, FlierState.SWOOP)
        for off in (-2, 2):
            if strong:
                pygame.draw.circle(surface, (*config.COLORS["enemy_eye"],), (int(ex + off), int(ey)), 3)
                pygame.draw.rect(surface, (255, 230, 255), (ex + off - 1, ey - 1, 2, 2))
            elif st == FlierState.RECOVERY:
                pygame.draw.rect(surface, (120, 70, 150), (ex + off - 1, ey - 1, 2, 2))
            else:
                pygame.draw.rect(surface, (230, 180, 255), (ex + off - 1, ey - 1, 2, 2))
        # 予備動作の警告（急降下する方向に短い光の線）
        if st == FlierState.WINDUP:
            k = min(1.0, self.state_time / p["windup_time"])
            dx, dy = self.swoop_dir
            pygame.draw.line(surface, (*config.COLORS["enemy_eye"],),
                             (cx + dx * 12, cy + dy * 12), (cx + dx * (12 + 22 * k), cy + dy * (12 + 22 * k)), 2)
        if self.hp < self.max_hp:
            hb = 30
            top = self.foot_y - self.height - 12 - camera.y
            pygame.draw.rect(surface, (30, 10, 30), (cx - hb / 2, top, hb, 4))
            pygame.draw.rect(surface, (180, 90, 230), (cx - hb / 2, top, hb * max(0, self.hp) / self.max_hp, 4))
