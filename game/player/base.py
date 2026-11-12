"""プレイヤーの共通処理（移動・ジャンプ・ダッシュ・被弾・描画）。

v2.0 で操作キャラクターは主人公1人になり、直接攻撃は廃止された。
キャラクター固有の処理はサブクラス（player/protagonist.py）で以下のフックを実装する。
    on_landed()                      … 着地時
    on_teleported()                  … テレポートで位置が交換された直後
    draw_extra(surface, camera)      … 装備などの追加描画
"""
from __future__ import annotations

import itertools
import math

import pygame

import config
from systems.collision import approach

_uid_counter = itertools.count(1)


class Player:
    def __init__(self, cfg: dict, x: float, y: float):
        self.uid = next(_uid_counter)
        self.cfg = cfg
        self.name = cfg["name"]
        self.stats = cfg["stats"]
        w, h = config.PLAYER_SIZE
        self.rect = pygame.FRect(x, y, w, h)
        self.vx = 0.0
        self.vy = 0.0
        self.facing = 1
        self.move_dir = 0
        self.on_ground = False
        self.on_one_way = False
        # ?????????????????????????????
        self.teleport_grounded = False
        self.hp = self.stats["max_hp"]
        self.alive = True
        self.invuln = 0.0
        # ジャンプ
        self.coyote = 0.0
        self.jump_buffer = 0.0
        self.jumping = False
        self.drop_timer = 0.0
        # ダッシュ
        self.dash_timer = 0.0
        self.dash_cooldown = 0.0
        self.dash_dir = 1
        # ジャンプ回数と空中ダッシュ使用権は独立して管理する
        self.max_jumps = int(self.stats["max_jumps"])
        self.jumps_used = 0
        self.max_air_dashes = int(self.stats["max_air_dashes"])
        self.air_dashes_remaining = self.max_air_dashes
        # 描画用
        self.anim_time = 0.0
        self.trail: list[tuple[float, float, float]] = []

    # ------------------------------------------------------------------
    # プロパティ
    # ------------------------------------------------------------------
    @property
    def hurtbox(self) -> pygame.FRect:
        return self.rect

    @property
    def move_speed(self) -> float:
        return self.stats["move_speed"]

    @property
    def is_dashing(self) -> bool:
        return self.dash_timer > 0

    # -- テレポート用: 当たり判定の足元中央を基準に位置を扱う ----------------
    @property
    def foot_center(self) -> tuple[float, float]:
        return self.rect.centerx, self.rect.bottom

    def rect_at_foot(self, fx: float, fy: float) -> pygame.FRect:
        """足元中央が (fx, fy) になる位置の当たり判定（自身は動かさない）。"""
        r = self.rect.copy()
        r.centerx = fx
        r.bottom = fy
        return r

    def place_foot(self, fx: float, fy: float) -> None:
        self.rect.centerx = fx
        self.rect.bottom = fy

    # ------------------------------------------------------------------
    # サブクラス用フック
    # ------------------------------------------------------------------
    def on_landed(self) -> None:
        pass

    def on_teleported(self, world) -> None:
        pass

    def draw_extra(self, surface, camera) -> None:
        pass

    # ------------------------------------------------------------------
    # 更新
    # ------------------------------------------------------------------
    def update(self, dt: float, inp, world) -> None:
        if not self.alive:
            return
        p = config.PHYSICS
        self.anim_time += dt
        # 浮動小数点誤差で1フレーム延びないよう、ごく小さい残りは0とみなす
        self.invuln = self.invuln - dt if self.invuln - dt > 1e-9 else 0.0
        self.coyote = max(0.0, self.coyote - dt)
        self.jump_buffer = max(0.0, self.jump_buffer - dt)
        self.drop_timer = max(0.0, self.drop_timer - dt)
        self.dash_cooldown = max(0.0, self.dash_cooldown - dt)

        self.move_dir = (1 if inp.held("right") else 0) - (1 if inp.held("left") else 0)
        if self.move_dir:
            self.facing = self.move_dir

        # ジャンプ / 降下入力
        if inp.pressed("jump"):
            if inp.held("down") and self.on_one_way:
                self.drop_timer = p["drop_through_time"]
                self.on_ground = False
                self.on_one_way = False
                self.coyote = 0.0
            else:
                self.jump_buffer = p["jump_buffer_time"]

        if inp.pressed("dash"):
            self.try_dash()

        self._normal_motion(dt, inp, world)

        if self.dash_timer > 0:
            self.dash_timer = max(0.0, self.dash_timer - dt)

        # 残像
        if self.is_dashing:
            self.trail.append((self.rect.x, self.rect.y, 0.18))
        self.trail = [(x, y, t - dt) for (x, y, t) in self.trail if t - dt > 0]

    def try_dash(self) -> bool:
        if self.dash_cooldown > 0 or self.dash_timer > 0:
            return False
        if (not self.on_ground or self.teleport_grounded) and self.air_dashes_remaining <= 0:
            return False
        self.dash_dir = self.move_dir or self.facing
        self.facing = self.dash_dir
        self.dash_timer = self.stats["dash_duration"]
        self.dash_cooldown = self.stats["dash_cooldown"]
        if not self.on_ground or self.teleport_grounded:
            self.air_dashes_remaining -= 1
        self.jumping = False
        self.vy = 0.0
        return True

    def cancel_motion(self) -> None:
        """テレポート直後: ダッシュを解除し、速度を 0 にする。"""
        self.dash_timer = 0.0
        self.jumping = False
        self.vx = 0.0
        self.vy = 0.0

    def _start_jump(self, speed: float) -> None:
        # 現在の垂直速度を上向きの初速で置き換える（二段目は落下速度がリセットされる）
        self.vy = -speed
        self.jumping = True    # 可変ジャンプは二段目にも適用
        self.jump_buffer = 0.0
        self.coyote = 0.0
        self.on_ground = False
        self.dash_timer = 0.0

    def _normal_motion(self, dt: float, inp, world) -> None:
        p = config.PHYSICS
        # 水平
        if self.dash_timer > 0:
            self.vx = self.dash_dir * self.stats["dash_speed"]
            self.vy = 0.0
        else:
            target = self.move_dir * self.move_speed
            if self.on_ground:
                rate = p["ground_accel"] if self.move_dir else p["ground_decel"]
            else:
                rate = p["air_accel"] if self.move_dir else p["air_decel"]
            self.vx = approach(self.vx, target, rate * dt)

        # ジャンプ（押した瞬間のみ。長押しで自動的に二段目は出ない）
        if self.jump_buffer > 0:
            ground_jump = ((self.on_ground or self.coyote > 0)
                           and (not self.teleport_grounded or self.jumps_used == 0))
            if ground_jump:
                # 地上ジャンプ（コヨーテタイム中も地上扱い）= 1回目
                self._start_jump(self.stats["jump_speed"])
                self.jumps_used = 1
            else:
                # 足場から落ちただけの場合は1回目を消費済みとみなす → 空中で1回跳べる
                used = max(self.jumps_used, 1)
                if used < self.max_jumps:
                    self._start_jump(self.stats["double_jump_speed"])
                    self.jumps_used = used + 1
                    world.effects.burst(self.rect.centerx, self.rect.bottom, (215, 40, 50),
                                        count=10, speed=110, life=0.22, size=2, gravity=0.0)
                # 回数を使い切っている場合はバッファを残し、着地直後のジャンプに使う

        # 可変ジャンプ
        if self.jumping:
            if self.vy >= 0:
                self.jumping = False
            elif not inp.held("jump"):
                self.vy *= p["jump_cut_multiplier"]
                self.jumping = False

        # 重力
        if self.dash_timer <= 0:
            g = p["gravity"] * (p["jump_hold_gravity_scale"] if self.jumping else 1.0)
            self.vy = min(self.vy + g * dt, p["max_fall_speed"])

        res = world.terrain.move(self.rect, self.vx * dt, self.vy * dt,
                                 ignore_one_way=self.drop_timer > 0)
        self._after_move(res, world)

    def _after_move(self, res, world) -> None:
        if res.hit_x:
            self.vx = 0.0
        if res.hit_ceiling and self.vy < 0:
            self.vy = 0.0
            self.jumping = False
        grounded, one_way = world.terrain.ground_state(self.rect, ignore_one_way=self.drop_timer > 0)
        if grounded and self.vy >= 0:
            # 着地でジャンプ回数と空中ダッシュ使用権を回復
            if not self.teleport_grounded:
                self.jumps_used = 0
                self.air_dashes_remaining = self.max_air_dashes
            if not self.on_ground:
                self.on_landed()
            self.on_ground = True
            self.on_one_way = one_way
            self.coyote = 0.0 if self.teleport_grounded else config.PHYSICS["coyote_time"]
            self.vy = 0.0
        else:
            self.teleport_grounded = False
            self.on_ground = False
            self.on_one_way = False

    # ------------------------------------------------------------------
    # 被弾
    # ------------------------------------------------------------------
    def can_be_hit(self) -> bool:
        return self.alive and self.invuln <= 0

    def receive_contact(self, damage: int) -> bool:
        """敵本体との接触。"""
        if not self.can_be_hit():
            return False
        self._apply_damage(damage)
        return True

    def take_damage(self, amount: float, source=None) -> bool:
        """敵の攻撃判定・飛び道具による被弾。死亡したら True。"""
        if not self.can_be_hit():
            return False
        self._apply_damage(amount)
        return self.hp <= 0

    def _apply_damage(self, amount: float) -> None:
        self.hp -= amount
        self.invuln = self.stats["invuln_time"]
        if self.hp <= 0:
            self.hp = 0

    def kill(self) -> None:
        self.alive = False

    # ------------------------------------------------------------------
    # 描画
    # ------------------------------------------------------------------
    def draw(self, surface: pygame.Surface, camera) -> None:
        # 残像
        for (x, y, t) in self.trail:
            ghost = pygame.Surface((self.rect.w + 8, self.rect.h), pygame.SRCALPHA)
            ghost.fill((150, 20, 30, int(200 * t / 0.18)))
            surface.blit(ghost, (x - camera.x - 4, y - camera.y), special_flags=0)
        if self.invuln > 0 and int(self.invuln * 20) % 2 == 0:
            return
        self._draw_body(surface, camera)
        self.draw_extra(surface, camera)

    def _draw_body(self, surface, camera) -> None:
        sil = config.COLORS["silhouette"]
        x = self.rect.x - camera.x
        y = self.rect.y - camera.y
        w, h = self.rect.w, self.rect.h
        f = self.facing
        cx = x + w / 2
        t = self.anim_time
        # マント（進行方向の反対側になびく）
        speed_factor = min(1.0, abs(self.vx) / 400)
        flutter = math.sin(t * 12) * 3
        back = -f
        shoulder = (cx - back * 2, y + 12)
        tip_len = 14 + 16 * speed_factor
        tip = (cx + back * tip_len, y + h - 4 + flutter * 0.5 - speed_factor * 10)
        mid = (cx + back * (tip_len * 0.6), y + 22 + flutter)
        cape = [shoulder, (cx + back * 6, y + 10), mid, tip, (cx + back * 2, y + h - 6)]
        pygame.draw.polygon(surface, config.COLORS["cape_dark"], [(px, py + 1) for px, py in cape])
        pygame.draw.polygon(surface, config.COLORS["cape"], cape)
        # 胴体
        pygame.draw.rect(surface, sil, (x + 4, y + 11, w - 8, h - 21), border_radius=4)
        # 頭
        pygame.draw.circle(surface, sil, (cx, y + 7), 7)
        self._draw_head_detail(surface, cx, y, f)
        # 脚（走りアニメ）
        if self.on_ground and abs(self.vx) > 20:
            swing = math.sin(t * 18) * 5
        else:
            swing = 3 if not self.on_ground else 0
        pygame.draw.line(surface, sil, (cx - 3, y + h - 12), (cx - 3 - swing, y + h), 4)
        pygame.draw.line(surface, sil, (cx + 3, y + h - 12), (cx + 3 + swing, y + h), 4)
        # 目
        pygame.draw.rect(surface, (230, 80, 70), (cx + f * 3 - 1, y + 5, 3, 2))

    def _draw_head_detail(self, surface, cx, y, f) -> None:
        pass
