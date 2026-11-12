"""QA profiles only. Never writes stage JSON, assets, or renderer settings.

Optional --candidate L1=path --candidate L2=path --candidate L3=path loads
unapproved widened v3 canvases using prep_manifest source registration.
"""
import argparse
import copy
import json
import os
from pathlib import Path
import sys

os.environ.setdefault("SDL_VIDEODRIVER","dummy")
os.environ.setdefault("SDL_AUDIODRIVER","dummy")
ROOT=Path(__file__).resolve().parents[5]
sys.path.insert(0,str(ROOT/"game"))
import pygame
from stages import parse_stage
from stages.background import ParallaxImageBackground, ImageLayer, DecorationLayer
from systems.world import World
from ui.hud import HUD

HERE=Path(__file__).resolve().parent


def raw_copy(target,source,pos):
    target.fill((0,0,0,0),(*pos,*source.get_size()))
    target.blit(source,pos,special_flags=pygame.BLEND_RGBA_ADD)


def candidate_profile(active, paths, right_only=False):
    manifest_path=HERE.parent/"candidates_v3/prep_manifest.json"
    manifest=json.loads(manifest_path.read_text(encoding="utf-8"))
    bg=copy.copy(active);bg.layers=list(active.layers)
    proof={}
    source_size=tuple(manifest["source_size"])
    for key,path in paths.items():
        info=manifest["layers"][key]
        candidate=pygame.image.load(str(path))
        offset=tuple(info["source_offset_in_candidate"])
        if candidate.get_size()!=tuple(info["candidate_canvas_size"]):
            raise ValueError(f"{key}: candidate size does not match declared manifest")
        original=pygame.image.load(str(HERE.parent/info["source_file"]))
        restored=candidate.subsurface((*offset,*source_size))
        unchanged=pygame.image.tobytes(restored,"RGBA")==pygame.image.tobytes(original,"RGBA")
        if not unchanged:raise ValueError(f"{key}: protected source RGBA changed")
        proof[key]={"file":str(path),"source_rgba_equal":unchanged,"source_offset":offset,
                    "size":candidate.get_size(),"approved":False}
        if key in ("L1","L2"):
            # Keep original 960px sampling grid. Scale only the added strip separately.
            original_view=pygame.transform.smoothscale(restored,(960,540))
            added=candidate.get_width()-source_size[0]
            strip_w=round(added*960/source_size[0])
            tile=pygame.Surface((960+strip_w,540),pygame.SRCALPHA)
            raw_copy(tile,original_view,(0,0))
            strip=pygame.transform.smoothscale(candidate.subsurface((1672,0,added,941)),(strip_w,540))
            raw_copy(tile,strip,(960,0))
            idx=1 if key=="L1" else 2
            bg.layers[idx]=ImageLayer(active.layers[idx].id,tile.premul_alpha(),active.layers[idx].factor,0,True,True)
            proof[key]["qa_period"]=tile.get_width()
        else:
            # Extend only outside original atlas; unchanged core keeps its sampling/origin.
            deco=active.decorations
            sprites=dict(deco.sprites);origins=dict(deco.origins)
            for name,left in (("ruin_left",True),("ruin_right",False)):
                if right_only and left:
                    continue
                sd=next(s for s in active.config.decorations.sprites if s.id==name)
                core=sprites[name]
                pad=offset[0] if left else candidate.get_width()-offset[0]-1672
                px=0 if left else offset[0]+1672
                patch=candidate.subsurface((px,sd.src[1],pad,sd.src[3]))
                pad_w=round(pad*960/1672)
                patch=pygame.transform.smoothscale(patch,(pad_w,core.get_height()))
                extended=pygame.Surface((core.get_width()+pad_w,core.get_height()),pygame.SRCALPHA)
                raw_copy(extended,core,(pad_w if left else 0,0))
                raw_copy(extended,patch,(0 if left else core.get_width(),0))
                sprites[name]=extended
                if left:origins[name]=(origins[name][0]-pad_w,origins[name][1])
            bg.decorations=DecorationLayer(deco.id,sprites,deco.items,deco.factor,960,deco.period,origins)
            proof[key]["note"]="QA adapter retains active core/fade settings; source padding rendered separately"
    return bg,proof


def run(candidate_paths, right_only=False):
    pygame.init();pygame.display.set_mode((960,540))
    raw=json.loads((ROOT/"game/stages/stage_1.json").read_text(encoding="utf-8"))
    before=json.loads((HERE/"before_stage.json").read_text(encoding="utf-8"))
    stage=parse_stage(raw)
    active=ParallaxImageBackground(stage.background,960,540)
    profiles={"before":ParallaxImageBackground(parse_stage(before).background,960,540),"corrected":active}
    proof={}
    profile_name="candidate_L3_right_only_unapproved" if right_only else "candidate_unapproved"
    if candidate_paths:
        profiles[profile_name],proof=candidate_profile(active,candidate_paths,right_only)
    result={"candidate_status":"QA only, not approved" if candidate_paths else "waiting for assembled v3 candidates",
            "candidate_protection":proof,"profiles":list(profiles),"scene_geometry_unchanged":True}
    stripped_before=copy.deepcopy(before);stripped_before.pop("background",None)
    stripped_now=copy.deepcopy(raw);stripped_now.pop("background",None)
    if stripped_before!=stripped_now:raise ValueError("Non-background stage fields changed")
    world=World(stage);hud=HUD()
    for name,bg in profiles.items():
        world.background=bg
        for camera in (0,600,1200,2240):
            world.camera.x=camera;world.player.rect.x=camera+300
            world.wall.segments[0].front_x=camera+140
            world.hover_target=next((e for e in world.enemies if world.camera.is_visible(e.body_rect)
                                    and e.body_rect.right>camera+180),None)
            if world.hover_target:
                x,y=world.camera.to_screen(*world.hover_target.center);world.mouse_screen=(min(950,max(10,x)),y)
            target=pygame.Surface((960,540));world.draw(target);hud.draw(target,world)
            pygame.image.save(target,str(HERE/f"{name}_cam{camera}.png"))
        # Background-only frames on both sides of every active material period.
        for layer in bg.layers[1:]:
            boundary=layer.period/layer.factor
            for delta in (-1,0,1):
                target=pygame.Surface((960,540));bg.draw(target,boundary+delta)
                pygame.image.save(target,str(HERE/f"{name}_{layer.id}_wrap{delta:+}.png"))
    # Source-object alignment comparisons at actual 960x540 rendering scale.
    old=profiles["before"].decorations;new=active.decorations
    sheet=pygame.Surface((960,540));sheet.fill((28,22,28))
    for row,deco in enumerate((old,new)):
        p=next(p for p in deco.items if p.sprite=="ruin_right")
        x,y=deco.screen_pos(p,1420)
        sheet.blit(deco.sprites["ruin_right"],(x,y-200+row*240))
    pygame.image.save(sheet,str(HERE/"ruin_right_before_top_corrected_bottom.png"))
    (HERE/"qa_profiles.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    if candidate_paths:
        (HERE/f"qa_profiles_{profile_name}.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    pygame.quit();print(json.dumps(result,indent=2))


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate",action="append",default=[],help="L1=PNG, L2=PNG or L3=PNG")
    parser.add_argument("--l3-right-only",action="store_true",help="QA only: keep the existing L3 left side")
    args=parser.parse_args()
    paths={}
    for entry in args.candidate:
        key,value=entry.split("=",1)
        if key not in ("L1","L2","L3"):parser.error("unknown candidate layer")
        paths[key]=Path(value).resolve()
    run(paths,args.l3_right_only)
