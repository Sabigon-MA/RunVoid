"""敵の共通基底クラス。

座標規約: x = 中心, foot_y = 足元。
「本体（body_rect）」は接触ダメージ用、「hurtbox」は被弾判定用。
武器攻撃・飛び道具は CombatSystem に target_team="player" の Attack として出す
（本体接触とは別系統で処理される）。

怯み（stagger）は共通処理として実装する。
    stagger_duration（攻撃側）× (1 - stagger_resistance) の時間だけ行動不能になる。
    stagger_immunity=True の敵（将来の大型敵・ボス等）は怯まない。
    サブクラスは on_stagger() で行動の中断、is_staggered で行動停止を実装する。

v2.0: 主人公は直接攻撃できないため、雑魚敵の怯みは通常プレイでは発生しない
（環境攻撃・ボスの攻撃など将来の拡張用に共通処理として残している）。

テレポート（位置交換）:
    can_be_teleported() で対象にできるか、foot_center / rect_at_foot / place_foot で
    足元中央を基準に位置を扱う。交換直後に on_teleported(world) が呼ばれる。
    足場のない位置へ交換された場合は重力で落下する（落下中は AI を止める）。

死亡は die(cause) で記録し、演出などの後処理は World が一元的に行う。
    cause: "attack"（攻撃。ボスの自傷を含む） / "wall"（追跡壁） / "fall"（落下・環境）
"""
from __future__ import annotations

import itertools

import pygame

_uid_counter = itertools.count(1)


class Enemy:
    def __init__(self, x: float, foot_y: float, width: float, height: float,
                 hp: float, contact_damage: int, enemy_id: str = "",
                 knockback_speed: float = 0.0, knockback_time: float = 0.0,
                 stagger_resistance: float = 0.0, stagger_immunity: bool = False,
                 gravity: float = 1400.0, max_fall_speed: float = 900.0):
        self.uid = next(_uid_counter)
        self.enemy_id = enemy_id
        self.x = float(x)
        self.foot_y = float(foot_y)
        self.home_x = float(x)
        self.width = width
        self.height = height
        self.max_hp = hp
        self.hp = hp
        self.contact_damage = contact_damage
        self.alive = True
        self.death_cause: str | None = None
        self.death_processed = False   # World が後処理済みか（報酬の二重取得防止）
        self.facing = -1
        self.hurt_flash = 0.0
        self.anim_time = 0.0
        self.knockback_speed = knockback_speed
        self.knockback_time = knockback_time
        self.knockback_vx = 0.0
        self.knockback_timer = 0.0
        # 怯み
        self.stagger_resistance = stagger_resistance   # 0.0〜1.0（1.0 で実質無効）
        self.stagger_immunity = stagger_immunity
        self.stagger_timer = 0.0
        self.stagger_dir = 1      # 怯んだ方向（ノックバック方向）。姿勢の描画用
        # 落下（テレポートで足場のない位置へ出たとき）
        self.gravity = gravity
        self.max_fall_speed = max_fall_speed
        self.vy = 0.0
        self.airborne = False

    @property
    def is_staggered(self) -> bool:
        return self.stagger_timer > 0

    def apply_stagger(self, duration: float, direction: int = 0) -> bool:
        """怯ませる。怯み中に再度受けた場合は残り時間を更新（長い方を採用）する。"""
        if self.stagger_immunity or duration <= 0 or not self.alive:
            return False
        effective = duration * max(0.0, 1.0 - self.stagger_resistance)
        if effective <= 0:
            return False
        self.stagger_timer = max(self.stagger_timer, effective)
        if direction:
            self.stagger_dir = direction
        self.on_stagger()
        return True

    def on_stagger(self) -> None:
        """怯みが始まった/更新されたとき（サブクラスで行動を中断する）。"""

    @property
    def body_rect(self) -> pygame.FRect:
        return pygame.FRect(self.x - self.width / 2, self.foot_y - self.height,
                            self.width, self.height)

    @property
    def hurtbox(self) -> pygame.FRect:
        return self.body_rect

    @property
    def center(self) -> tuple[float, float]:
        return self.x, self.foot_y - self.height / 2

    # -- テレポート --------------------------------------------------------
    def can_be_teleported(self) -> bool:
        """テレポート対象にできる状態か（死亡済み・消滅処理中は不可）。"""
        return self.alive and not self.death_processed

    @property
    def foot_center(self) -> tuple[float, float]:
        return self.x, self.foot_y

    def rect_at_foot(self, fx: float, fy: float) -> pygame.FRect:
        return pygame.FRect(fx - self.width / 2, fy - self.height, self.width, self.height)

    def place_foot(self, fx: float, fy: float) -> None:
        self.x = float(fx)
        self.foot_y = float(fy)

    def on_teleported(self, world) -> None:
        """位置交換の直後。巡回の基準点を新しい位置へ移し、移動を止める。"""
        self.home_x = self.x
        self.knockback_timer = 0.0
        self.knockback_vx = 0.0
        self.vy = 0.0
        self.airborne = not world.terrain.ground_state(self.body_rect)[0]

    def can_be_hit(self) -> bool:
        return self.alive

    def take_damage(self, amount: float, source=None) -> bool:
        """ダメージを受ける。この攻撃で倒れたら True。"""
        if not self.alive:
            return False
        self.hp -= amount
        self.hurt_flash = 0.15
        direction = source.push_direction(self) if source is not None else 0
        if direction and self.knockback_time > 0:
            self.knockback_vx = direction * self.knockback_speed
            self.knockback_timer = self.knockback_time
        if self.hp <= 0:
            # 攻撃者の判定（プレイヤーかどうか）は World が行い、死亡原因を確定させる
            self.die("attack")
            return True
        if source is not None:
            self.apply_stagger(getattr(source, "stagger_duration", 0.0), direction)
        return False

    def die(self, cause: str) -> None:
        if self.alive:
            self.alive = False
            self.death_cause = cause

    # -- 地面を歩く敵向けの移動補助 -----------------------------------------
    def can_step(self, nx: float, direction: int, terrain) -> bool:
        """x を nx に動かしてよいか（崖・段差・壁の手前では False）。"""
        front = nx + direction * (self.width / 2)
        if not terrain.has_ground_at(front, self.foot_y):
            return False
        body = pygame.FRect(nx - self.width / 2, self.foot_y - self.height, self.width, self.height - 1)
        return not terrain.overlaps_solid(body)

    def try_move(self, dx: float, terrain) -> bool:
        if dx == 0:
            return True
        direction = 1 if dx > 0 else -1
        nx = self.x + dx
        if self.can_step(nx, direction, terrain):
            self.x = nx
            return True
        return False

    def _apply_knockback(self, dt: float, terrain) -> None:
        if self.knockback_timer <= 0:
            return
        self.knockback_timer = max(0.0, self.knockback_timer - dt)
        if not self.try_move(self.knockback_vx * dt, terrain):
            self.knockback_timer = 0.0

    def update(self, dt: float, world) -> None:
        self.anim_time += dt
        self.hurt_flash = max(0.0, self.hurt_flash - dt)
        # 浮動小数点誤差で1フレーム延びないよう、ごく小さい残りは0とみなす
        self.stagger_timer = self.stagger_timer - dt if self.stagger_timer - dt > 1e-9 else 0.0
        # ノックバックは can_step で判定するため地形・崖を貫通しない
        self._apply_knockback(dt, world.terrain)
        self._apply_gravity(dt, world.terrain)

    def _apply_gravity(self, dt: float, terrain) -> None:
        """足場がなければ落下する。通常の歩行中は崖判定で足場から出ないため発生しない。"""
        body = self.body_rect
        grounded, _ = terrain.ground_state(body)
        if grounded and self.vy >= 0:
            self.vy = 0.0
            self.airborne = False
            return
        self.airborne = True
        self.vy = min(self.vy + self.gravity * dt, self.max_fall_speed)
        res = terrain.move(body, 0.0, self.vy * dt)
        self.x = body.centerx
        self.foot_y = body.bottom
        if res.landed:
            self.vy = 0.0
            self.airborne = False
        elif res.hit_ceiling:
            self.vy = 0.0

    def draw(self, surface: pygame.Surface, camera) -> None:
        r = self.body_rect.move(-camera.x, -camera.y)
        pygame.draw.rect(surface, (0, 0, 0), r)
