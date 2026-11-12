"""マウスカーソルによるテレポート対象の選択。

座標変換:
    ウィンドウ座標 → 内部解像度座標 … main.py の pygame.SCALED が行う
                                        （イベントの pos は常に 960x540 基準）
    内部座標 → ワールド座標         … Camera.to_world（カメラオフセットを加算）

選択条件:
    - 対象が can_be_teleported()（生存中・消滅処理中でない）
    - 対象の当たり判定が現在の画面内に表示されている（画面外は不可・距離制限なし）
    - カーソルが「当たり判定 + pick_margin」の範囲内にある
    - 複数が重なる場合は手前に描画されている敵（描画順で後ろの敵）を優先
"""
from __future__ import annotations

import config


def pick_rect(enemy, margin: float | None = None):
    m = config.TELEPORT["pick_margin"] if margin is None else margin
    return enemy.hurtbox.inflate(m * 2, m * 2)


def is_targetable(enemy, camera) -> bool:
    return enemy.can_be_teleported() and camera.view_rect.colliderect(enemy.hurtbox)


def find_target(enemies_in_draw_order, camera, mouse_world):
    """カーソル位置にいるテレポート可能な敵（いなければ None）。"""
    mx, my = mouse_world
    if not camera.view_rect.collidepoint(mx, my):
        return None
    for enemy in reversed(enemies_in_draw_order):   # 後に描画された敵ほど手前
        if not is_targetable(enemy, camera):
            continue
        if pick_rect(enemy).collidepoint(mx, my):
            return enemy
    return None
