"""雑魚敵「影這い」。

行動サイクル:
    PATROL / CHASE → WINDUP(0.4秒) → LUNGE(0.2秒) → RECOVERY(0.6秒) → COOLDOWN(0.3秒) → 再行動

- 状態遷移は1回の update で最大1回。時間は固定タイムステップの dt で積算する。
- WINDUP 開始時に飛びかかる方向を決定し、以降はプレイヤーを追尾しない。
- LUNGE 中だけ専用の攻撃判定（AttachedAttack）を出す。本体接触ダメージとは別系統。
- v1.2: どの状態からでも被弾で STAGGER（怯み）へ移行し、行動を中断する。
  怯み明けは CHASE / PATROL に戻り、中断された飛びかかりは再開しない。
  ただし硬直・待機の途中で怯んだ場合でも、その残り時間が過ぎるまでは次の攻撃を始めない
  （怯ませることで攻撃後硬直を短縮できてしまうのを防ぐ）。
- v2.0: テレポートの対象になる。交換後は新しい位置を巡回の基準にする。
  足場のない位置へ交換された場合は落下し、着地するまで行動しない
  （予備動作・飛びかかり中に空中へ出された場合は攻撃を中断して硬直に入る）。
"""
from __future__ import annotations

import math
from enum import Enum, auto

import pygame

import config
from enemies.base import Enemy
from systems.combat import AttachedAttack

EPS = 1e-6

_HALO_CACHE: dict[tuple[int, int, int], pygame.Surface] = {}


def _halo(w: int, h: int, alpha: int) -> pygame.Surface:
    """敵の背後に置く楕円の淡い光（中心ほど濃い）。サイズごとに一度だけ作る。"""
    key = (w, h, alpha)
    surf = _HALO_CACHE.get(key)
    if surf is None:
        surf = pygame.Surface((max(2, w), max(2, h)), pygame.SRCALPHA)
        r, g, b = config.COLORS["enemy_halo"]
        steps = 8
        for i in range(steps):
            k = i / steps
            rect = pygame.Rect(0, 0, int(w * (1 - k)), int(h * (1 - k)))
            rect.center = (w // 2, h // 2)
            pygame.draw.ellipse(surf, (r, g, b, int(alpha * (k + 1 / steps) ** 1.5)), rect)
        if len(_HALO_CACHE) > 256:   # 姿勢でサイズが変わるため上限を設ける
            _HALO_CACHE.clear()
        _HALO_CACHE[key] = surf
    return surf


class CrawlerState(Enum):
    PATROL = auto()
    CHASE = auto()
    WINDUP = auto()
    LUNGE = auto()
    RECOVERY = auto()
    COOLDOWN = auto()
    STAGGER = auto()


class ShadowCrawler(Enemy):
    TYPE = "shadow_crawler"

    def __init__(self, x: float, foot_y: float, enemy_id: str = "", params: dict | None = None):
        p = dict(config.ENEMIES[self.TYPE])
        if params:
            p.update(params)
        super().__init__(x, foot_y, p["body_w"], p["body_h"], p["hp"], p["contact_damage"], enemy_id,
                         knockback_speed=p["knockback_speed"], knockback_time=p["knockback_time"],
                         stagger_resistance=p["stagger_resistance"],
                         stagger_immunity=p["stagger_immunity"],
                         gravity=p["gravity"], max_fall_speed=p["max_fall_speed"])
        self.params = p
        self.speed = p["speed"]
        self.detect_range = p["detect_range"]
        self.patrol_range = p["patrol_range"]
        self.attack_range = p["attack_range"]
        self.attack_vertical_range = p["attack_vertical_range"]
        self.state = CrawlerState.PATROL
        self.state_time = 0.0
        self.lunge_dir = -1
        self.attack_lock = 0.0   # 次の攻撃を始められるまでの残り時間（硬直＋待機）
        self._glow = self._make_glow(16)
        self._glow_strong = self._make_glow(28)

    @staticmethod
    def _make_glow(size: int) -> pygame.Surface:
        surf = pygame.Surface((size, size), pygame.SRCALPHA)
        r, g, b = config.COLORS["enemy_eye"]
        c = size // 2
        for rad, a in ((c, 40), (int(c * 0.65), 90), (int(c * 0.4), 170)):
            pygame.draw.circle(surf, (r, g, b, a), (c, c), max(1, rad))
        return surf

    # ------------------------------------------------------------------
    def _enter(self, state: CrawlerState) -> None:
        self.state = state
        self.state_time = 0.0

    def _sees_player(self, player) -> bool:
        if player is None or not player.alive:
            return False
        cx, cy = self.center
        px, py = player.rect.center
        return math.hypot(px - cx, py - cy) <= self.detect_range

    def on_stagger(self) -> None:
        # 予備動作・飛びかかりを含め、現在の行動を中断する。
        # LUNGE の攻撃判定は keep_alive（state == LUNGE）で即座に無効化される。
        self._enter(CrawlerState.STAGGER)

    def on_teleported(self, world) -> None:
        super().on_teleported(world)
        if self.airborne and self.state in (CrawlerState.WINDUP, CrawlerState.LUNGE):
            # 空中では飛びかかれない。攻撃判定は keep_alive で即座に消える
            self._enter(CrawlerState.RECOVERY)
            self.attack_lock = self.params["recovery_time"] + self.params["cooldown_time"]

    def _can_attack(self, player, terrain) -> bool:
        if self.attack_lock > EPS:
            return False
        cx, cy = self.center
        px, py = player.rect.center
        if abs(px - cx) > self.attack_range or abs(py - cy) > self.attack_vertical_range:
            return False
        # 攻撃可能な足場にいる（足元に地面がある）
        return terrain.has_ground_at(self.x, self.foot_y)

    def lunge_hitbox(self) -> pygame.FRect:
        r = self.body_rect
        ext = self.params["lunge_hitbox_extend"]
        r.width += ext
        if self.lunge_dir < 0:
            r.x -= ext
        return r

    # ------------------------------------------------------------------
    def update(self, dt: float, world) -> None:
        super().update(dt, world)   # 点滅・怯みタイマー・ノックバック・落下
        if self.airborne:
            return   # 落下中は行動しない（着地後に再開）
        self.state_time += dt
        self.attack_lock = max(0.0, self.attack_lock - dt)
        terrain = world.terrain
        player = world.player
        p = self.params
        st = self.state

        if st == CrawlerState.STAGGER:
            # 怯み中は移動・追跡・攻撃をしない（ノックバックのみ）
            if not self.is_staggered:
                self._enter(CrawlerState.CHASE if self._sees_player(player) else CrawlerState.PATROL)
            return

        if st in (CrawlerState.PATROL, CrawlerState.CHASE):
            sees = self._sees_player(player)
            if sees and self._can_attack(player, terrain):
                dx = player.rect.centerx - self.x
                self.lunge_dir = (1 if dx > 0 else -1) if abs(dx) > EPS else self.facing
                self.facing = self.lunge_dir   # 予備動作中は向きを固定
                self._enter(CrawlerState.WINDUP)
                return
            wanted = CrawlerState.CHASE if sees else CrawlerState.PATROL
            if wanted != st:
                self._enter(wanted)
            self._move(dt, player, terrain)

        elif st == CrawlerState.WINDUP:
            if self.state_time >= p["windup_time"] - EPS:
                self._enter(CrawlerState.LUNGE)
                world.combat.spawn(AttachedAttack(
                    self, p["lunge_damage"], self.lunge_hitbox, p["lunge_time"],
                    keep_alive=lambda: self.alive and self.state == CrawlerState.LUNGE))

        elif st == CrawlerState.LUNGE:
            # 決定済みの方向へ突進。崖・地形の手前で止まる（無理に追尾しない）
            self.try_move(self.lunge_dir * p["lunge_speed"] * dt, terrain)
            if self.state_time >= p["lunge_time"] - EPS:
                self._enter(CrawlerState.RECOVERY)
                self.attack_lock = p["recovery_time"] + p["cooldown_time"]

        elif st == CrawlerState.RECOVERY:
            if self.state_time >= p["recovery_time"] - EPS:
                self._enter(CrawlerState.COOLDOWN)

        elif st == CrawlerState.COOLDOWN:
            if self.state_time >= p["cooldown_time"] - EPS:
                self._enter(CrawlerState.CHASE if self._sees_player(player) else CrawlerState.PATROL)

    def _move(self, dt, player, terrain) -> None:
        if self.state == CrawlerState.CHASE:
            dx = player.rect.centerx - self.x
            direction = 0 if abs(dx) < 4 else (1 if dx > 0 else -1)
        else:
            if self.x >= self.home_x + self.patrol_range:
                self.facing = -1
            elif self.x <= self.home_x - self.patrol_range:
                self.facing = 1
            direction = self.facing
        if direction == 0:
            return
        self.facing = direction
        if not self.try_move(direction * self.speed * dt, terrain):
            if self.state == CrawlerState.PATROL:
                self.facing = -direction   # 崖・壁の手前で方向転換
            # 追跡中は崖の手前で停止する

    # ------------------------------------------------------------------
    def draw(self, surface: pygame.Surface, camera) -> None:
        sx = self.x - camera.x
        fy = self.foot_y - camera.y
        w, h = self.width, self.height
        t = self.anim_time
        f = self.facing
        st = self.state
        p = self.params

        # 状態ごとの姿勢
        squash, stretch, shake, lean = 1.0, 1.0, 0.0, 0.0
        leg_speed = 14 if st == CrawlerState.CHASE else 9
        moving = st in (CrawlerState.PATROL, CrawlerState.CHASE)
        if st == CrawlerState.WINDUP:
            k = min(1.0, self.state_time / p["windup_time"])
            squash = 1.0 - 0.35 * k          # 身体を縮める
            stretch = 1.0 + 0.15 * k
            shake = math.sin(t * 70) * 1.5 * k
            lean = -f * 4 * k                # 後ろへ引く
        elif st == CrawlerState.LUNGE:
            squash, stretch, lean = 0.8, 1.35, f * 6
        elif st == CrawlerState.RECOVERY:
            squash, stretch = 0.75, 1.1      # へたり込む（反撃チャンス）
        elif st == CrawlerState.STAGGER:
            # 姿勢を崩す: のけぞって身体が浮き、小刻みに揺れる
            squash, stretch = 1.15, 0.85
            lean = self.stagger_dir * 5
            shake = math.sin(t * 90) * 2

        if self.hurt_flash > 0:
            body_col = (200, 170, 230) if int(self.hurt_flash * 40) % 2 == 0 else (90, 50, 120)
        else:
            body_col = config.COLORS["silhouette"]
        cx = sx + shake + lean
        bw, bh = w * stretch, (h - 4) * squash

        # 脚の形（縁取りと本体で同じ形を2回描く）
        legs = []
        for i in range(4):
            lx = cx - bw / 2 + 6 + i * (bw - 12) / 3
            swing = math.sin(t * leg_speed + i * 1.7) * 4 if moving else 0
            if st == CrawlerState.LUNGE:
                swing = -f * 6
            if st == CrawlerState.STAGGER:
                # 脚がばたつき、地面から浮く
                legs.append(((lx, fy - 6), (lx + math.sin(t * 40 + i) * 5, fy - 3)))
            else:
                legs.append(((lx, fy - 6), (lx + swing - f * 3, fy)))
        bob = math.sin(t * leg_speed) * 1.5 if moving else 0
        body = pygame.Rect(0, 0, int(bw), max(4, int(bh)))
        body.midbottom = (int(cx), int(fy - 2 + bob))
        head = pygame.Rect(0, 0, 16, 12)
        head.center = (int(cx + f * (bw / 2 - 4)), int(body.centery - 1))

        # v2.3 視認性: 背後の淡い光と縁取り（暗い瓦礫・地面に紛れないように。描画のみ）
        vis = config.VISIBILITY
        if vis["enemy_halo_alpha"] > 0:
            halo = _halo(int(bw) + 30, int(bh) + 22, vis["enemy_halo_alpha"])
            surface.blit(halo, (cx - halo.get_width() / 2, body.centery - halo.get_height() / 2))
        rim = vis["enemy_rim_width"]
        if rim > 0:
            rim_col = config.COLORS["enemy_rim"]
            for a, b in legs:
                pygame.draw.line(surface, rim_col, a, b, 2 + rim * 2)
            pygame.draw.ellipse(surface, rim_col, body.inflate(rim * 2, rim * 2))
            pygame.draw.ellipse(surface, rim_col, head.inflate(rim * 2, rim * 2))

        # 脚・胴体・頭
        for a, b in legs:
            pygame.draw.line(surface, body_col, a, b, 2)
        pygame.draw.ellipse(surface, body_col, body)
        pygame.draw.ellipse(surface, body_col, head)
        # 朽ちた布
        cloth_x = cx - f * 6
        pygame.draw.polygon(surface, (52, 36, 34), [
            (cloth_x - 7, body.top + 3), (cloth_x + 6, body.top + 2),
            (cloth_x + 3 - f * 4, body.bottom + 3 + math.sin(t * 6) * 2),
            (cloth_x - 5 - f * 6, body.bottom + 1)])
        # 枯草
        for i in range(5):
            gx = cx - bw / 2 + 8 + i * 5
            pygame.draw.line(surface, (110, 92, 58), (gx, body.top + 3),
                             (gx - f * 4 + math.sin(t * 4 + i) * 2, body.top - 5), 1)
        # 紫に光る目（予備動作中は強く発光、硬直中は弱く）
        ex, ey = head.centerx + f * 2, head.centery - 1
        strong = st in (CrawlerState.WINDUP, CrawlerState.LUNGE)
        for off in (-3, 3):
            if strong:
                g = self._glow_strong
                surface.blit(g, (ex + off - g.get_width() // 2, ey - g.get_height() // 2))
                pygame.draw.rect(surface, (255, 230, 255), (ex + off - 1, ey - 1, 3, 3))
            elif st == CrawlerState.RECOVERY:
                pygame.draw.rect(surface, (120, 70, 150), (ex + off - 1, ey - 1, 2, 2))
            elif st == CrawlerState.STAGGER:
                # 目が乱れる（×印）
                c = (220, 180, 255)
                pygame.draw.line(surface, c, (ex + off - 2, ey - 2), (ex + off + 2, ey + 2), 1)
                pygame.draw.line(surface, c, (ex + off - 2, ey + 2), (ex + off + 2, ey - 2), 1)
            else:
                surface.blit(self._glow, (ex + off - 8, ey - 8))
                pygame.draw.rect(surface, (230, 180, 255), (ex + off - 1, ey - 1, 2, 2))
        # HPバー（被弾後のみ）
        if self.hp < self.max_hp:
            hb = 30
            pygame.draw.rect(surface, (30, 10, 30), (sx - hb / 2, fy - h - 12, hb, 4))
            pygame.draw.rect(surface, (180, 90, 230),
                             (sx - hb / 2, fy - h - 12, hb * max(0, self.hp) / self.max_hp, 4))
