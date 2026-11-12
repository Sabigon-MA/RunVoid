"""敵キャラクター。新しい敵は ENEMY_TYPES に登録するとステージJSONから配置できる。"""
from enemies.base import Enemy
from enemies.shadow_crawler import CrawlerState, ShadowCrawler

ENEMY_TYPES = {
    ShadowCrawler.TYPE: ShadowCrawler,
}


def create_enemy(enemy_def) -> Enemy:
    cls = ENEMY_TYPES.get(enemy_def.type)
    if cls is None:
        raise ValueError(f"未知の敵タイプ: {enemy_def.type}")
    return cls(enemy_def.x, enemy_def.foot_y, enemy_def.id)


__all__ = ["Enemy", "ShadowCrawler", "CrawlerState", "ENEMY_TYPES", "create_enemy"]
