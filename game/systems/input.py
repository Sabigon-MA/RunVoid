"""入力状態の管理。

pygame のイベントをアクション名（"jump" など）単位の状態に変換する。
押下/解放のエッジは固定タイムステップの最初の1ステップでのみ有効になり、
描画フレームと物理ステップの回数がずれても入力を取りこぼさない。
"""
from __future__ import annotations

import pygame

import config


class InputState:
    def __init__(self, key_bindings=None, mouse_bindings=None):
        self.key_bindings = key_bindings or config.KEY_BINDINGS
        self.mouse_bindings = mouse_bindings or config.MOUSE_BINDINGS
        self._key_to_action: dict[int, str] = {}
        for action, keys in self.key_bindings.items():
            for k in keys:
                self._key_to_action[k] = action
        self._button_to_action = {b: a for a, b in self.mouse_bindings.items()}
        self._held_keys: dict[str, set[int]] = {a: set() for a in self.key_bindings}
        self._held: set[str] = set()
        self._pressed: set[str] = set()
        self._released: set[str] = set()
        self.mouse_pos: tuple[float, float] = (0.0, 0.0)

    # -- イベント処理 -----------------------------------------------------
    def process_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN:
            action = self._key_to_action.get(event.key)
            if action:
                if not self._held_keys[action]:
                    self._press(action)
                self._held_keys[action].add(event.key)
        elif event.type == pygame.KEYUP:
            action = self._key_to_action.get(event.key)
            if action:
                self._held_keys[action].discard(event.key)
                if not self._held_keys[action]:
                    self._release(action)
        elif event.type == pygame.MOUSEBUTTONDOWN:
            action = self._button_to_action.get(event.button)
            if action:
                self._press(action)
        elif event.type == pygame.MOUSEBUTTONUP:
            action = self._button_to_action.get(event.button)
            if action:
                self._release(action)
        elif event.type == pygame.MOUSEMOTION:
            self.mouse_pos = event.pos
        elif event.type == pygame.WINDOWFOCUSLOST:
            # キーを押したままフォーカスを失った場合に入力が残らないようにする
            self.reset()

    def _press(self, action: str) -> None:
        if action not in self._held:
            self._pressed.add(action)
        self._held.add(action)

    def _release(self, action: str) -> None:
        if action in self._held:
            self._released.add(action)
        self._held.discard(action)

    # -- 問い合わせ -------------------------------------------------------
    def held(self, action: str) -> bool:
        return action in self._held

    def pressed(self, action: str) -> bool:
        return action in self._pressed

    def released(self, action: str) -> bool:
        return action in self._released

    # -- 状態管理 ---------------------------------------------------------
    def clear_edges(self) -> None:
        """物理ステップで押下/解放を消費した後に呼ぶ。"""
        self._pressed.clear()
        self._released.clear()

    def reset(self) -> None:
        """シーン切替時やフォーカス喪失時に全状態を破棄する。"""
        for keys in self._held_keys.values():
            keys.clear()
        self._held.clear()
        self.clear_edges()

    # -- テスト・自動操作用 ------------------------------------------------
    def simulate_press(self, action: str) -> None:
        self._press(action)

    def simulate_release(self, action: str) -> None:
        self._release(action)
