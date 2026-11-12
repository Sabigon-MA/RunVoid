"""QA only: render integrated 960x540 frames for active config vs finish_v2 candidate config.
Does not modify artwork or stage files (candidate config is an in-memory dict)."""
import sys, os, json, copy
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy'); os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
root = sys.argv[1]; out = sys.argv[2]
sys.path.insert(0, os.path.join(root, 'game')); os.chdir(os.path.join(root, 'game'))
import pygame
pygame.init(); pygame.display.set_mode((960, 540))
import config
from stages import loader, background as bgmod
from systems.world import World
raw = json.load(open('stages/stage_1.json', encoding='utf-8'))
cand = copy.deepcopy(raw)
b = cand['background']; b['asset_dir'] = 'assets/backgrounds/twilight_ruins/finish_v2'
b['layers'][0]['image'] = '../draft_v1/01_sky.png'
for L in b['layers'][1:]: L['seam'] = {'mode': 'none'}
b['decorations']['image'] = '../draft_v1/04_near_debris.png'
variants = {'after': raw}
cams = [float(c) for c in sys.argv[3].split(',')]
for name, data in variants.items():
    bgmod.clear_cache()
    stage = loader.parse_stage(data)
    for cx in cams:
        w = World(stage)
        cam = w.camera
        cam.x = min(max(cx, 0.0), cam.max_x)
        w.player.rect.x = int(cam.x + 300)
        w.wall.segments[0].front_x = cam.x + 140
        vis = [e for e in w.enemies if cam.is_visible(e.body_rect, 0)]
        w.hover_target = vis[0] if vis else None
        s = pygame.Surface((960, 540)); w.draw(s)
        pygame.image.save(s, f'{out}/game_{name}_cam{cx:g}.png')
        print(name, cx, 'cam.x', cam.x, 'hover', bool(vis))
    # background-only frames around wrap boundaries (camera beyond clamp allowed for bg)
    bg = bgmod.build_background(stage.background, 960, 540)
    for cx in [float(c) for c in sys.argv[4].split(',')]:
        s = pygame.Surface((960, 540)); bg.draw(s, cx)
        pygame.image.save(s, f'{out}/bgonly_{name}_cam{cx:g}.png')
