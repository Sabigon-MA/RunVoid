"""Opt-in native SDL aiming probe; never imported by unittest discovery.

Run: python game/tests/manual_aim_probe.py --output <outside-repo-directory>
R resets, C moves the camera, Space toggles ordinary simulation, Escape exits.
An optional command.json in the output directory accepts id, size, reset,
camera_x, live and quit. This only controls the diagnostic fixture.
"""
from __future__ import annotations

import argparse
import ctypes
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pygame
from pygame._sdl2 import Window
from main import Game
from systems.targeting import find_target


def run(output: Path, display_mode: str = "pixel_perfect", high_dpi: bool = False) -> None:
    output.mkdir(parents=True, exist_ok=True)
    game = Game(display_mode=display_mode, high_dpi=high_dpi)
    if pygame.display.get_driver() == "dummy":
        pygame.quit()
        raise RuntimeError("Native probe requires a real SDL video driver, not dummy")
    pygame.display.set_caption("RunVoid - Native Aim Probe")
    window = Window.from_display_module()
    window.size = (960, 540)
    live = False
    command_id = None

    def reset():
        game.start_play()
        w = game.world
        w.wall.paused = True
        for enemy in w.enemies:
            enemy.speed = 0
            enemy.attack_range = -1

    def snapshot():
        w = game.world
        dpi = None
        if sys.platform == "win32":
            dpi = ctypes.windll.user32.GetDpiForWindow(pygame.display.get_wm_info()["window"])
        return dict(command_id=command_id, live=live, dpi=dpi, display_mode=game.display.mode,
                    integer_scale=game.display.integer_scale_enabled(),
                    high_dpi=game.settings.high_dpi,
                    window_size=pygame.display.get_window_size(),
                    surface_size=game.screen.get_size(), camera_x=w.camera.x,
                    mouse=game.input.mouse_pos, mouse_get_pos=pygame.mouse.get_pos(), cooldown=w.teleport.cooldown_remaining,
                    count=w.teleport.count, state=w.state,
                    hover=getattr(w.hover_target, "enemy_id", None),
                    enemies=[dict(id=e.enemy_id, screen_center=w.camera.to_screen(*e.center))
                             for e in w.enemies if w.camera.is_visible(e.body_rect)])

    reset()
    try:
        while game.running:
            game.clock.tick(60)
            path = output / "command.json"
            if path.exists():
                try:
                    command = json.loads(path.read_text(encoding="utf-8-sig"))
                except (ValueError, OSError):
                    command = {}
                if command.get("id") != command_id and "id" in command:
                    command_id = command["id"]
                    if command.get("reset"):
                        reset()
                    if "size" in command:
                        window.size = tuple(command["size"])
                    if "camera_x" in command:
                        game.world.camera.x = float(command["camera_x"])
                    live = command.get("live", live)
                    if command.get("quit"):
                        break
            for event in pygame.event.get():
                if event.type == pygame.KEYDOWN and event.key == pygame.K_r:
                    reset()
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_c:
                    game.world.camera.x += 80
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE:
                    live = not live
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    game.running = False
                else:
                    game.handle_event(event)
                if event.type == pygame.MOUSEBUTTONDOWN:
                    w = game.world
                    target = find_target(w.enemies, w.camera, w.camera.to_world(*event.pos))
                    before = snapshot()
                    game.fixed_update(0.0)
                    record = dict(event_pos=event.pos, selected=getattr(target, "enemy_id", None),
                                  before=before, after=snapshot())
                    with (output / "clicks.jsonl").open("a", encoding="utf-8") as f:
                        f.write(json.dumps(record) + "\n")
            if live:
                game.fixed_update(1 / 60)
            else:
                game.world._update_mouse(game.input)
            game.draw()
            # Visible native cursor allows comparison with the game's reticle.
            pygame.mouse.set_visible(True)
            temporary = output / "state.tmp"
            temporary.write_text(json.dumps(snapshot()), encoding="utf-8")
            for _ in range(50):   # 読み取り側が開いている間は Windows で置換に失敗するため再試行
                try:
                    temporary.replace(output / "state.json")
                    break
                except PermissionError:
                    time.sleep(0.01)
    finally:
        pygame.quit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--display", choices=("pixel_perfect", "fit"), default="pixel_perfect")
    parser.add_argument("--high-dpi", action="store_true")
    args = parser.parse_args()
    run(args.output, args.display, args.high_dpi)
