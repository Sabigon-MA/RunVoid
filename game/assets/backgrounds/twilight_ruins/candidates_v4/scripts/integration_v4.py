"""In-memory QA adapter for v4 (no production edits; writes only under candidates_v4/qa_v4/integration).

Reuses Codex's read-only candidate_profile() (imported, not modified): it verifies size + protected RGBA
against the v3 prep_manifest geometry (v4 geometry is identical) and renders L1/L2 with the original
960/1672 sampling grid plus the separately scaled pad strip; L3 pads rendered outside the atlas core.
Run with the audit venv (pygame-ce):  python -B <this>
"""
import json, os, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
V4 = HERE.parent
TR = V4.parent
sys.path.insert(0, str(TR / 'qa_integration_codex'))
import render_integration as ri  # noqa: E402  (module import has no file-writing side effects)
import pygame  # noqa: E402
from stages import parse_stage  # noqa: E402
from stages.background import ParallaxImageBackground  # noqa: E402
from systems.world import World  # noqa: E402
from ui.hud import HUD  # noqa: E402

OUT = V4 / 'qa_v4' / 'integration'
OUT.mkdir(parents=True, exist_ok=True)
V3C = TR / 'candidates_v3' / 'candidates'
V4C = V4 / 'candidates'
PROFILES = {
    'current_draft_v1': None,
    'v3_all_unapproved': {'L1': V3C / 'L1_candidate.png', 'L2': V3C / 'L2_candidate.png', 'L3': V3C / 'L3_candidate.png'},
    'v4_all_REJECTED_unapproved': {'L1': V4C / 'L1_v4_candidate.png', 'L2': V4C / 'L2_v4_candidate.png',
                                   'L3': V4C / 'L3_v4_candidate.png'},
}
CAMS = (0, 600, 1200, 1600, 2240)

pygame.init(); pygame.display.set_mode((960, 540))
raw = json.loads((ri.ROOT / 'game/stages/stage_1.json').read_text(encoding='utf-8'))
stage = parse_stage(raw)
active = ParallaxImageBackground(stage.background, 960, 540)
result = {'status': 'QA only, NOT approved, no production edits', 'profiles': {}}
world = World(stage); hud = HUD()
for name, paths in PROFILES.items():
    if paths is None:
        bg, proof = active, {}
    else:
        bg, proof = ri.candidate_profile(active, paths)
    result['profiles'][name] = {k: {kk: (str(vv) if isinstance(vv, Path) else vv) for kk, vv in v.items()}
                                for k, v in proof.items()}
    world.background = bg
    for cam in CAMS:
        world.camera.x = cam; world.player.rect.x = cam + 300
        world.wall.segments[0].front_x = cam + 140
        world.hover_target = next((e for e in world.enemies if world.camera.is_visible(e.body_rect)
                                   and e.body_rect.right > cam + 180), None)
        if world.hover_target:
            x, y = world.camera.to_screen(*world.hover_target.center); world.mouse_screen = (min(950, max(10, x)), y)
        t = pygame.Surface((960, 540)); world.draw(t); hud.draw(t, world)
        pygame.image.save(t, str(OUT / f'{name}_cam{cam}.png'))
    for layer in bg.layers[1:]:
        b = layer.period / layer.factor
        for d in (-60, 0):
            t = pygame.Surface((960, 540)); bg.draw(t, b + d)
            pygame.image.save(t, str(OUT / f'{name}_{layer.id}_wrap{d:+}.png'))
        # inner join (x=1672 source px of the layer) brought to screen centre, background only
        inner = (1672 * 960 / 1672 - 480) / layer.factor
        t = pygame.Surface((960, 540)); bg.draw(t, inner)
        pygame.image.save(t, str(OUT / f'{name}_{layer.id}_innerjoin_centre.png'))
(OUT / 'integration_v4.json').write_text(json.dumps(result, indent=1), encoding='utf-8')
pygame.quit(); print(json.dumps(result, indent=1)[:1500])
