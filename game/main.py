"""終焉を背に - プロトタイプ エントリーポイント。

    python main.py

物理更新は固定タイムステップ(1/60秒)、描画は 960x540 の内部サーフェスに行い、
ウィンドウサイズに合わせて拡大表示する（ゲーム内の挙動はウィンドウサイズに依存しない）。
"""
from __future__ import annotations

import argparse
import os
import sys

# どのディレクトリから起動してもモジュールを解決できるようにする
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pygame  # noqa: E402

import config  # noqa: E402
from stages import load_stage  # noqa: E402
from stages.renderer import make_background  # noqa: E402
from systems.input import InputState  # noqa: E402
from systems.world import CLEAR, DEAD, World  # noqa: E402
from ui.hud import HUD  # noqa: E402
from ui.screens import (TitleScreen, make_clear_screen, make_death_screen,  # noqa: E402
                        make_pause_screen)

TITLE, PLAY, PAUSED, DEAD_SCREEN, CLEAR_SCREEN = ("title", "play", "paused", "dead", "clear")


class Game:
    def __init__(self, stage_file: str = config.DEFAULT_STAGE):
        os.environ["SDL_RENDER_SCALE_QUALITY"] = "nearest"
        pygame.init()
        pygame.display.set_caption(config.WINDOW_TITLE)
        size = (config.SCREEN_WIDTH, config.SCREEN_HEIGHT)
        try:
            # SCALED: 内部解像度を保ったままウィンドウ拡大。マウス座標も内部座標に変換される
            self.window = pygame.display.set_mode(size, pygame.SCALED | pygame.RESIZABLE)
        except pygame.error:
            self.window = pygame.display.set_mode(size)
        self.screen = pygame.Surface(size)
        self.clock = pygame.time.Clock()
        self.stage = load_stage(stage_file)
        self.input = InputState()
        self.hud = HUD()
        self.menu_background = make_background(self.stage.theme, *size, self.stage.background)
        self.world: World | None = None
        self.overlay = None
        self.state = TITLE
        self.scene = TitleScreen(self.menu_background)
        self.running = True
        self.accumulator = 0.0

    # ------------------------------------------------------------------
    # 画面遷移
    # ------------------------------------------------------------------
    def go_title(self):
        self.state = TITLE
        self.world = None
        self.overlay = None
        self.scene = TitleScreen(self.menu_background)
        self._update_cursor()

    def start_play(self):
        # タイトルから直接開始（キャラクター選択なし）。
        # リトライ時もマップ・プレイヤー・敵・追跡壁・タイマーを丸ごと作り直す
        self.world = World(self.stage)
        self.overlay = None
        self.state = PLAY
        self.input.reset()
        self.input.mouse_pos = pygame.mouse.get_pos()
        self.accumulator = 0.0
        self._update_cursor()

    def _update_cursor(self):
        # プレイ中は OS のカーソルを隠し、HUD の照準を表示する
        try:
            pygame.mouse.set_visible(self.state != PLAY)
        except pygame.error:
            pass

    # ------------------------------------------------------------------
    # イベント
    # ------------------------------------------------------------------
    def handle_event(self, event):
        if event.type == pygame.QUIT:
            self.running = False
            return
        if self.state == TITLE:
            action = self.scene.handle_event(event)
            if action == "start":
                self.start_play()
            elif action == "quit":
                self.running = False
        elif self.state == PLAY:
            if event.type == pygame.KEYDOWN and event.key in config.KEY_BINDINGS["pause"]:
                self.state = PAUSED
                self.overlay = make_pause_screen()
                self.input.reset()
                self._update_cursor()
                return
            self.input.process_event(event)
        elif self.state in (PAUSED, DEAD_SCREEN, CLEAR_SCREEN):
            if (self.state == PAUSED and event.type == pygame.KEYDOWN
                    and event.key in config.KEY_BINDINGS["pause"]):
                self._resume()
                return
            action = self.overlay.handle_event(event)
            if action == "resume":
                self._resume()
            elif action == "retry":
                self.start_play()
            elif action == "title":
                self.go_title()

    def _resume(self):
        self.state = PLAY
        self.overlay = None
        self.input.reset()
        self.input.mouse_pos = pygame.mouse.get_pos()
        self.accumulator = 0.0
        self._update_cursor()

    # ------------------------------------------------------------------
    # 更新・描画
    # ------------------------------------------------------------------
    def fixed_update(self, dt: float):
        if self.state == PLAY and self.world:
            # ヒットストップ中は入力エッジを消費しない（止まっている間の入力を取りこぼさない）
            if self.world.update(dt, self.input):
                self.input.clear_edges()
            if self.world.state == DEAD:
                self.state = DEAD_SCREEN
                self.overlay = make_death_screen(self.world)
                self._update_cursor()
            elif self.world.state == CLEAR:
                self.state = CLEAR_SCREEN
                self.overlay = make_clear_screen(self.world)
                self._update_cursor()
        elif self.state == TITLE:
            self.scene.update(dt)
        else:
            # ポーズ中はゲーム内時間（壁・敵・テレポートのクールダウン）を止める。
            # 死亡・クリア画面では演出（粒子）だけ進める
            if self.world and self.state != PAUSED:
                self.world.update(dt, self.input)
            if self.overlay:
                self.overlay.update(dt)
        self.hud.update(dt)

    def draw(self):
        surf = self.screen
        if self.state == TITLE:
            self.scene.draw(surf)
        elif self.world:
            self.world.draw(surf)
            if self.state in (PLAY, PAUSED):
                self.hud.draw(surf, self.world)
            if self.overlay:
                self.overlay.draw(surf)
        self.window.blit(surf, (0, 0))
        pygame.display.flip()

    def step_frame(self, frame_time: float):
        """1描画フレーム分の処理。固定タイムステップで物理を進める。"""
        for event in pygame.event.get():
            self.handle_event(event)
        self.accumulator += min(frame_time, config.MAX_FRAME_TIME)
        while self.accumulator >= config.FIXED_DT and self.running:
            self.fixed_update(config.FIXED_DT)
            self.accumulator -= config.FIXED_DT
        self.draw()

    def run(self, max_frames: int | None = None):
        frames = 0
        self.clock.tick()
        while self.running:
            frame_time = self.clock.tick(config.FPS) / 1000.0
            self.step_frame(frame_time)
            frames += 1
            if max_frames is not None and frames >= max_frames:
                break
        pygame.quit()


def main(argv=None):
    parser = argparse.ArgumentParser(description="終焉を背に - Prototype")
    parser.add_argument("--stage", default=config.DEFAULT_STAGE, help="ステージJSONファイル")
    parser.add_argument("--frames", type=int, default=None, help="指定フレーム数で自動終了（動作確認用）")
    args = parser.parse_args(argv)
    Game(args.stage).run(max_frames=args.frames)


if __name__ == "__main__":
    main()
