"""描画フレームの待機（v2.4）。物理は従来どおり main.Game の固定タイムステップ（1/60秒）で進み、
ここは「次の描画フレームまでどう待つか」と「実際の経過時間」だけを扱う。

方式（config.FRAME_WAIT）:
    tick     … pygame.time.Clock.tick(fps)。SDL_Delay（ms 単位の Sleep）で待つ。v2.3 までの方式
    busy     … Clock.tick_busy_loop(fps)。待ち時間をすべて空回りで待つ（CPU 1コアを使い切る）
    sleep    … 絶対時刻の締切まで time.sleep で待つ（Windows の Python 3.11+ は高分解能タイマー）
    hybrid   … 締切の spin_ms 前まで time.sleep、残りを空回り

sleep / hybrid は「前フレームの終わり + 1/60秒」ではなく「締切 += 1/60秒」の絶対時刻で刻むので、
1 フレームの寝坊が次の締切を後ろへずらさない。1 フレーム以上遅れたときは締切を現在時刻に合わせ直し、
遅れを取り戻すための連続フレームは作らない（物理の追いつきは従来どおり固定タイムステップ側が行う）。
"""
from __future__ import annotations

import time

import pygame

MODES = ("tick", "busy", "sleep", "hybrid")


class FrameClock:
    def __init__(self, fps: float, mode: str = "tick", spin_ms: float = 1.5, timer=time.perf_counter,
                 sleep=time.sleep):
        if mode not in MODES:
            raise ValueError(f"unknown frame wait mode: {mode!r}")
        self.fps = fps
        self.mode = mode
        self.period = 1.0 / fps
        self.spin = spin_ms / 1000.0
        self._timer = timer
        self._sleep = sleep
        self._clock = pygame.time.Clock()
        self._deadline = None
        self._last = None
        self.last_wait = 0.0     # 直前の wait() で待った時間（秒、計測用）

    def reset(self) -> None:
        """計測の基準を今に合わせる（ループ開始時）。"""
        self._clock.tick()
        now = self._timer()
        self._last = now
        self._deadline = now + self.period

    def wait(self) -> float:
        """次のフレームまで待ち、前回の wait() からの実経過時間（秒）を返す。"""
        if self._last is None:
            self.reset()
        start = self._timer()
        if self.mode == "tick":
            self._clock.tick(self.fps)
        elif self.mode == "busy":
            self._clock.tick_busy_loop(self.fps)
        else:
            target = self._deadline
            if self.mode == "hybrid":
                remaining = target - self.spin - self._timer()
                if remaining > 0:
                    self._sleep(remaining)
                while self._timer() < target:
                    pass
            else:
                remaining = target - self._timer()
                if remaining > 0:
                    self._sleep(remaining)
            now = self._timer()
            self._deadline = target + self.period
            if now - self._deadline > -0.25 * self.period:
                # 1 フレーム近く遅れている: 締切を今から刻み直す（取り戻しの連続フレームを作らない）
                self._deadline = now + self.period
        now = self._timer()
        self.last_wait = now - start
        elapsed = now - self._last
        self._last = now
        return elapsed
