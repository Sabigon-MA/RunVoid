"""1回分のプレイ（ステージ・プレイヤー・敵・追跡壁・カメラ・タイマー）を保持する。

リトライ時は World を作り直すだけで、すべての状態が初期化される。

1物理ステップの処理順:
    1. テレポート（左クリック押下時のみ）… 位置交換はここで完結する
    2. プレイヤー移動 → 敵 → 追跡壁 → 攻撃判定
    3. 追跡壁の即死判定 → 敵本体との接触 → 敵の消滅 → 落下・ゴール判定
    4. カメラ追従・演出
"""
from __future__ import annotations

import config
from enemies import create_enemy
from player import create_protagonist
from stages.renderer import TerrainRenderer, make_background
from systems.camera import Camera
from systems.chasing_wall import ChasingWall
from systems.collision import Terrain
from systems.combat import CombatSystem
from systems.effects import Effects, draw_outline
from systems.targeting import find_target
from systems.teleport import TeleportSystem

PLAYING, DEAD, CLEAR = "playing", "dead", "clear"


class World:
    def __init__(self, stage, with_graphics: bool = True):
        self.stage = stage
        self.with_graphics = with_graphics
        view_w, view_h = stage.resolution
        self.terrain = Terrain([r.to_rect() for r in stage.platforms],
                               [r.to_rect() for r in stage.one_way_platforms])
        self.combat = CombatSystem()
        self.effects = Effects()
        self.teleport = TeleportSystem()
        self.player = create_protagonist(*stage.spawn)
        self.enemies = [create_enemy(e) for e in stage.enemies]
        self.wall = ChasingWall(stage.wall.start_x, stage.wall.speed, stage.wall.thickness)
        self.camera = Camera(view_w, view_h, stage.world_width, view_h)
        self.camera.snap_to(self.player.rect)
        self.mouse_screen = (0.0, 0.0)
        self.mouse_world = self.player.rect.center
        self.hover_target = None
        self.contact_grace = 0.0      # テレポート直後の本体接触ダメージ無効時間
        self.required_bosses = {e for e in self.enemies if getattr(e, "is_boss", False)}
        self.active_boss = None
        self.wall_halted = False      # 最終ボス撃破で True（以後は二度と動かない）
        self.elapsed = 0.0
        self.max_x = self.player.rect.x
        self.state = PLAYING
        self.death_cause: str | None = None
        # ヒットストップ: 残りフレーム数。0 より大きい間は物理更新を丸ごと止める
        self.hitstop_frames = 0
        self.background = (make_background(stage.theme, view_w, view_h, stage.background)
                           if with_graphics else None)
        self.terrain_renderer = TerrainRenderer(stage) if with_graphics else None

    # ------------------------------------------------------------------
    @property
    def wall_distance(self) -> float:
        return self.wall.distance_to(self.player.rect)

    @property
    def wall_on_screen(self) -> bool:
        return self.wall.front_x > self.camera.x

    def _active_enemy(self, enemy) -> bool:
        """カメラから遠い敵は更新しない（処理負荷対策）。ボス・落下中の敵は常に更新。"""
        if getattr(enemy, "is_boss", False) or enemy.airborne:
            return True
        view = self.camera.view_rect.inflate(config.ENEMY_UPDATE_MARGIN * 2, 200)
        return view.colliderect(enemy.body_rect)

    @property
    def in_hitstop(self) -> bool:
        return self.hitstop_frames > 0

    def _update_mouse(self, inp) -> None:
        self.mouse_screen = inp.mouse_pos
        self.mouse_world = self.camera.to_world(*inp.mouse_pos)
        self.hover_target = find_target(self.enemies, self.camera, self.mouse_world)

    # ------------------------------------------------------------------
    def update(self, dt: float, inp) -> bool:
        """1物理ステップ進める。

        戻り値は入力の押下/解放を消費したかどうか。ヒットストップ中は False を返し、
        呼び出し側は入力エッジを保持したままにする（入力の取りこぼし防止）。
        """
        if self.state != PLAYING:
            self.effects.update(dt)
            return True
        if self.hitstop_frames > 0:
            # 追跡壁・敵・プレイヤー・攻撃・タイマー・エフェクトをすべて止める
            self.hitstop_frames -= 1
            self._update_mouse(inp)
            return False
        self.required_bosses.update(e for e in self.enemies if getattr(e, "is_boss", False))
        self._update_mouse(inp)
        self.elapsed += dt
        self.teleport.update(dt)
        self.contact_grace = max(0.0, self.contact_grace - dt)

        player = self.player
        # 1. テレポート（押下開始時のみ。押し続けても連続発動しない）
        if inp.pressed("teleport") and self.hover_target is not None:
            self.teleport.try_teleport(self, self.hover_target)
        player.device_ready = self.teleport.ready

        # 2. 移動（テレポートで瞬間移動した分は壁の掃引判定に含めない）
        prev_rect = player.rect.copy()
        player.update(dt, inp, self)
        self.max_x = max(self.max_x, player.rect.x)

        for enemy in self.enemies:
            if enemy.alive and self._active_enemy(enemy):
                enemy.update(dt, self)

        self.wall.update(dt)

        self.combat.update(dt, self.terrain,
                           {"enemy": self.enemies, "player": [player]},
                           on_hit=self._on_hit)

        # 3. 追跡壁は無敵中でも最優先で即死（移動経路も含めて判定）
        if self.wall.touches_swept(prev_rect, player.rect):
            self._kill_player("wall")
            return True

        # 敵本体との接触（ダメージはプレイヤーのみ、ノックバックなし）。
        # テレポート直後は交換と同時の接触ダメージを防ぐため本体接触だけ無効
        if self.contact_grace <= 0:
            for enemy in self.enemies:
                if enemy.alive and enemy.body_rect.colliderect(player.rect):
                    if player.receive_contact(enemy.contact_damage):
                        self.effects.burst(player.rect.centerx, player.rect.centery,
                                           (200, 30, 40), 8, 160, 0.35)
                        break

        # 追跡壁に飲み込まれた敵・落下した敵は消滅
        for enemy in self.enemies:
            if not enemy.alive:
                continue
            if self.wall.touches(enemy.body_rect):
                self.kill_enemy(enemy, "wall")
            elif enemy.foot_y - enemy.height > self.stage.kill_y:
                self.kill_enemy(enemy, "fall")
        self.enemies = [e for e in self.enemies if e.alive]

        if player.hp <= 0:
            self._kill_player("hp")
            return True
        if player.rect.top > self.stage.kill_y:
            self._kill_player("fall")
            return True
        bosses_defeated = bool(self.required_bosses) and all(
            b.death_processed and b.death_cause == "attack" for b in self.required_bosses)
        if bosses_defeated or (not self.required_bosses and player.rect.right >= self.stage.goal_x):
            self.state = CLEAR
            player.vx = 0
            return True

        # 4. カメラ・演出
        self.camera.follow(player.rect, dt)
        self.effects.update(dt)
        if self.background:
            self.background.update(dt)
        if self.terrain_renderer:
            self.terrain_renderer.update(dt)
        return True

    # ------------------------------------------------------------------
    # テレポート
    # ------------------------------------------------------------------
    def on_teleported(self, target, before) -> None:
        """TeleportSystem から位置交換の成功時に呼ばれる。"""
        self.contact_grace = config.TELEPORT["contact_grace"]
        before_player, before_target = before
        self.effects.teleport_arrive(before_player, before_target, self.player, target,
                                     config.COLORS["teleport"])
        # 大きく移動しても主人公が画面外に消えないよう、カメラを速やかに追従させる
        # （画面端の margin 内へは即座に寄せ、残りは高速スムーズ追従）
        self.camera.boost()
        self.camera.keep_in_view(self.player.rect)
        self.camera._clamp()
        self.hover_target = None

    # ------------------------------------------------------------------
    # ボス
    # ------------------------------------------------------------------
    def on_boss_engaged(self, boss) -> None:
        """ボス戦開始: 追跡壁を停止する。"""
        self.active_boss = boss
        self.wall.paused = True

    def _on_boss_defeated(self, boss) -> None:
        if self.active_boss is boss:
            self.active_boss = None
        if boss.stops_wall_permanently:
            self.wall_halted = True   # 壁発生源の破壊: 以後は完全停止
            self.wall.paused = True
        elif not self.wall_halted:
            self.wall.paused = False  # ステージ進行を再開

    # ------------------------------------------------------------------
    def _on_hit(self, attack, target, killed) -> None:
        cx, cy = target.hurtbox.center
        if target is self.player:
            self.effects.burst(cx, cy, (200, 30, 40), 8, 160, 0.35)
            return
        # 敵への命中（ボスの自傷など）。同フレームに複数命中しても加算せず最大値
        self.hitstop_frames = max(self.hitstop_frames, attack.hitstop_frames)
        self.effects.burst(cx, cy, (190, 110, 240), 8, 160, 0.25)
        self.effects.ring(cx, cy)
        if killed:
            self.kill_enemy(target, "attack")

    def kill_enemy(self, enemy, cause: str) -> None:
        """敵の死亡処理を一元管理する（演出の二重発生を防ぐ）。"""
        if enemy.death_processed:
            return
        enemy.die(cause)
        enemy.death_cause = cause
        enemy.death_processed = True
        cx, cy = enemy.hurtbox.center
        if cause == "wall":
            self.effects.burst(cx, cy, (90, 20, 60), 12, 120, 0.5)
        else:
            self.effects.burst(cx, cy, (40, 20, 50), 18, 200, 0.6)
            self.effects.burst(cx, cy, (190, 90, 255), 10, 140, 0.5)
        if getattr(enemy, "is_boss", False) and cause == "attack":
            self._on_boss_defeated(enemy)

    def _kill_player(self, cause: str) -> None:
        self.player.kill()
        self.state = DEAD
        self.death_cause = cause
        self.effects.burst(self.player.rect.centerx, self.player.rect.centery,
                           (170, 20, 28), 30, 260, 0.9)

    # ------------------------------------------------------------------
    def draw(self, surface) -> None:
        cam = self.camera
        if self.background:
            self.background.draw(surface, cam.x)
        if self.terrain_renderer:
            self.terrain_renderer.draw(surface, cam)
        for enemy in self.enemies:
            if cam.is_visible(enemy.body_rect, 40):
                enemy.draw(surface, cam)
        # テレポート対象の輪郭発光（クールダウン中は弱く）
        target = self.hover_target
        if target is not None and target.alive and self.state == PLAYING:
            alpha = 255 if self.teleport.ready else 90
            draw_outline(surface, target, cam, config.COLORS["teleport"], alpha)
        if self.player.alive:
            self.player.draw(surface, cam)
        self.combat.draw(surface, cam)
        self.effects.draw(surface, cam)
        self.wall.draw(surface, cam)
