"""Read-only material study. Only writes QA artifacts under --output.

Uses the existing qa_render.py for the unmodified integrated baseline, then
experiments with copies of surfaces/configs IN MEMORY. No production writes.
Run from any cwd with the pygame-ce environment.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import subprocess
import sys
import zlib

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / "game"))
import pygame
from stages import loader
from stages.background import ImageLayer, SeamDef, make_seamless
from systems.world import World

SIZE = (960, 540)
ART = ROOT / "game/assets/backgrounds/twilight_ruins/draft_v1"


def save(s, path):
    pygame.image.save(s, str(path))


def compose(tile, sky, camera, factor):
    out = sky.copy()
    ImageLayer("qa", tile, factor, 0, True, True).draw(out, camera)
    return out


def join_sheet(tile, sky):
    out = pygame.Surface((tile.get_width() * 2, 540))
    # A horizontally uniform backdrop avoids introducing a false SKY seam.
    # Integrated/camera frames below still use the original approved sky.
    out.fill((42, 26, 34))
    for x in (0, tile.get_width()):
        out.blit(tile, (x, 0), special_flags=pygame.BLEND_PREMULTIPLIED)
    return out


def roll(s, cut):
    w, h = s.get_size()
    out = pygame.Surface((w, h), pygame.SRCALPHA)
    out.blit(s, (0, 0), (cut, 0, w-cut, h), special_flags=pygame.BLEND_RGBA_ADD)
    out.blit(s, (w-cut, 0), (0, 0, cut, h), special_flags=pygame.BLEND_RGBA_ADD)
    return out


def hard_owner(s, width=96):
    """C: one source per pixel. No averaging. A cut, not a repair."""
    w, h = s.get_size()
    p = w-width
    a = s.premul_alpha()
    out = pygame.Surface((p, h), pygame.SRCALPHA)
    out.blit(a, (width, 0), (width, 0, w-2*width, h), special_flags=pygame.BLEND_RGBA_ADD)
    for x in range(width):
        # Alpha dominance preserves opaque architecture over transparent sky.
        for y in range(h):
            left = a.get_at((x, y))
            right = a.get_at((w-width+x, y))
            out.set_at((x, y), right if right.a >= left.a else left)
    return out


def feather_trial(s, width=96):
    """A diagnostic local-alpha edit, not a production solution."""
    return make_seamless(s, SeamDef("feather", width))


def absdiff(a, b):
    aa, bb = pygame.image.tobytes(a, "RGB"), pygame.image.tobytes(b, "RGB")
    return sum(abs(x-y) for x, y in zip(aa, bb)) / len(aa)


def column_error(s, x1, x2):
    return sum(abs(s.get_at((x1,y))[k]-s.get_at((x2,y))[k])
               for y in range(s.get_height()) for k in range(4)) / (s.get_height()*4)


def edge_rows(s, x, threshold=8):
    rows = [y for y in range(s.get_height()) if s.get_at((x,y)).a > threshold]
    return [min(rows), max(rows)] if rows else None


def sparse_cut(s):
    # Low architecture occupancy, restricted to left quarter (not central landmarks).
    scores=[]
    for x in range(48, 240):
        scores.append((sum(s.get_at((x,y)).a > 128 for y in range(0,340)), x))
    return min(scores)[1]


def apng(frames, path):
    """Half-size nearest preview; metrics/static QA retain full 960x540."""
    frames = [pygame.transform.scale(f, (480, 270)) for f in frames]
    def chunk(kind, data):
        return struct.pack(">I",len(data))+kind+data+struct.pack(">I",zlib.crc32(kind+data)&0xffffffff)
    w,h=frames[0].get_size()
    data=b"\x89PNG\r\n\x1a\n"+chunk(b"IHDR",struct.pack(">IIBBBBB",w,h,8,6,0,0,0))
    data+=chunk(b"acTL",struct.pack(">II",len(frames),0))
    seq=0
    for i,frame in enumerate(frames):
        data+=chunk(b"fcTL",struct.pack(">IIIIIHHBB",seq,w,h,0,0,1,30,0,0));seq+=1
        rgba=pygame.image.tobytes(frame,"RGBA")
        raw=b"".join(b"\0"+rgba[y*w*4:(y+1)*w*4] for y in range(h))
        compressed=zlib.compress(raw,6)
        if i==0:
            data+=chunk(b"IDAT",compressed)
        else:
            data+=chunk(b"fdAT",struct.pack(">I",seq)+compressed);seq+=1
    path.write_bytes(data+chunk(b"IEND",b""))


def alpha_trial(s):
    """L3 diagnostic local alpha-only mask: never changes RGB or original PNG."""
    out=s.copy()
    w,h=s.get_size()
    changed=0
    for x in range(w):
        for y in range(h):
            c=s.get_at((x,y))
            if not c.a:
                continue
            border=x<8 or x>=w-8 or y>=h-6
            a=c.a
            if border:
                distance=min(x,w-1-x,h-1-y)
                a=round(a*min(1,distance/6))
            if a!=c.a:
                out.set_at((x,y),(c.r,c.g,c.b,a));changed+=1
    return out,changed


def resampling_comparison(crop, output):
    size=(round(crop.get_width()*960/1672),round(crop.get_height()*540/941))
    straight=pygame.transform.smoothscale(crop,size)
    premul=pygame.transform.smoothscale(crop.premul_alpha(),size)
    sheet=pygame.Surface((1200,440));diffs={}
    for i,color in enumerate(((255,255,255),(0,255,255),(10,5,10))):
        panels=[]
        for row,(image,flag) in enumerate(((straight,0),(premul,pygame.BLEND_PREMULTIPLIED))):
            panel=pygame.Surface((400,220));panel.fill(color)
            panel.blit(image,(80,20),special_flags=flag)
            sheet.blit(panel,(i*400,row*220));panels.append(panel)
        diffs[str(color)]=absdiff(*panels)
    save(sheet,output/"L3_resample_straight_top_premul_bottom.png")
    (output/"L3_resampling_metrics.json").write_text(json.dumps(diffs,indent=2),encoding="utf-8")


def render_study(output):
    output.mkdir(parents=True, exist_ok=True)
    pygame.init();pygame.display.set_mode(SIZE)
    old=ROOT/"game/assets/backgrounds/twilight_ruins/qa_finish_v2/qa_render.py"
    subprocess.run([sys.executable,"-B",str(old),str(ROOT),str(output),"0,600,1200,2240",
                    "2159,2160,2161,2399,2400,2401,5759,5760"],check=True)
    sky=pygame.transform.smoothscale(pygame.image.load(str(ART/"01_sky.png")),SIZE)
    metrics={"scope":"QA only; all official assets/config/game code unchanged", "layers":{}}
    tiles={}
    for label,filename,factor in [("L1","02_far_castle.png",.15),("L2","03_mid_invasion.png",.4)]:
        original=pygame.image.load(str(ART/filename))
        s=pygame.transform.smoothscale(original,SIZE)
        cut=sparse_cut(s)
        raw=s.premul_alpha()
        variants={"raw":raw,"baseline_crossfade":make_seamless(s,SeamDef("crossfade",96)),
                  "A_alpha_only":feather_trial(s),"B_phase_shift":roll(raw,cut),
                  "C_single_owner":hard_owner(s)}
        lm={"source_size":original.get_size(),"source_edge_rows_alpha_gt8":{
            "left":edge_rows(original,0),"right":edge_rows(original,original.get_width()-1)},
            "sparse_cut_internal_x":cut,"phase_preserves_pixel_bytes":False,"variants":{}}
        lm["phase_preserves_pixel_bytes"]=pygame.image.tobytes(roll(variants["B_phase_shift"],960-cut),"RGBA")==pygame.image.tobytes(raw,"RGBA")
        for name,tile in variants.items():
            sheet=join_sheet(tile,sky);save(sheet,output/f"{label}_{name}_2tiles.png")
            join=sheet.subsurface((tile.get_width()-150,120,300,330))
            save(pygame.transform.scale(join,(600,660)),output/f"{label}_{name}_join2x.png")
            layer_frames=[]
            cameras=(0,600,1200,2240)
            for camera in cameras:
                frame=compose(tile,sky,camera,factor)
                save(frame,output/f"{label}_{name}_cam{camera}.png")
            # Steady 336px/s camera at 30fps near the old seam centered on screen.
            start=(tile.get_width()-480)/factor-12*336/30
            for i in range(24):
                layer_frames.append(compose(tile,sky,start+i*336/30,factor))
            apng(layer_frames,output/f"{label}_{name}_scroll.png")
            strip=pygame.Surface((480*4,270))
            for n,i in enumerate((0,7,15,23)):
                strip.blit(pygame.transform.scale(layer_frames[i],(480,270)),(480*n,0))
            save(strip,output/f"{label}_{name}_filmstrip.png")
            temporal=[absdiff(a,b) for a,b in zip(layer_frames,layer_frames[1:])]
            metrics_diff={str(cx):round(absdiff(compose(tile,sky,cx,factor),compose(variants["baseline_crossfade"],sky,cx,factor)),4)
                          for cx in cameras}
            seam=column_error(tile,tile.get_width()-1,0)
            # Phase shifting moves the OLD bad join to this interior coordinate.
            interior=column_error(tile,960-cut-1,960-cut) if name=="B_phase_shift" else None
            lm["variants"][name]={"period":tile.get_width(),"boundary_rgba_mae":round(seam,4),
                "relocated_original_cut_rgba_mae":interior,
                "rgb_mae_vs_baseline_by_camera":metrics_diff,
                "temporal_rgb_mae_mean":round(sum(temporal)/len(temporal),4),
                "temporal_rgb_mae_max":round(max(temporal),4)}
        metrics["layers"][label]=lm;tiles[label]=s

    # L3: exact source crop vs a wider crop retaining the original world alignment.
    near=pygame.image.load(str(ART/"04_near_debris.png"))
    rect=pygame.Rect(1330,640,342,301)
    expanded=pygame.Rect(1240,610,432,331)
    metrics["L3"]={"canvas_size":near.get_size(),"source_cut_rows":{
        "outer_left":edge_rows(near,0),"outer_right":edge_rows(near,1671),
        "crop_left_x1330":edge_rows(near,1330),"expanded_left_x1240":edge_rows(near,1240)}}
    cropped=near.subsurface(rect).copy()
    wider=near.subsurface(expanded).copy()
    resampling_comparison(cropped,output)
    alpha,changed=alpha_trial(cropped)
    metrics["L3"]["local_alpha_changed_pixels"]=changed
    metrics["L3"]["rgb_invariant_alpha_trial"]=pygame.image.tobytes(alpha,"RGB")==pygame.image.tobytes(cropped,"RGB")
    for label,img in [("original_crop",cropped),("expanded_crop",wider),("alpha_only_trial",alpha)]:
        sheet=pygame.Surface((640*3,500));sheet.fill((20,20,20))
        for n,color in enumerate(((255,255,255),(0,255,255),(10,5,10))):
            panel=pygame.Surface((640,500));panel.fill(color)
            # Align original source x1330/y640, not the center of a wider rectangle.
            dx=90 if label=="expanded_crop" else 0
            dy=30 if label=="expanded_crop" else 0
            panel.blit(img,(150-dx,100-dy));sheet.blit(panel,(n*640,0))
        save(sheet,output/f"L3_{label}_contrast.png")
    # Collect source alpha and extreme-red diagnostic counts without changing them.
    for name,s in [("L1",pygame.image.load(str(ART/"02_far_castle.png"))),
                   ("L2",pygame.image.load(str(ART/"03_mid_invasion.png"))),("L3",near)]:
        rgba=pygame.image.tobytes(s,"RGBA");hist=[0]*256;red=0
        for i in range(0,len(rgba),4):
            r,g,b,a=rgba[i:i+4];hist[a]+=1
            red+=bool(a>8 and r>180 and g<60 and b<60)
        metrics.setdefault("alpha",{})[name]={"alpha0":hist[0],"alpha1_32":sum(hist[1:33]),
            "alpha33_246":sum(hist[33:247]),"alpha247_254":sum(hist[247:255]),
            "alpha255":hist[255],"extreme_red_diagnostic_pixels":red}

    raw=json.loads((ROOT/"game/stages/stage_1.json").read_text(encoding="utf-8"))
    world=World(loader.parse_stage(raw));bg=world.background
    l2=bg.layers[2]
    alpha_rows=[]
    for x in range(l2.surface.get_width()):
        ys=[y+l2.y for y in range(l2.surface.get_height()) if l2.surface.get_at((x,y)).a>8]
        if ys:alpha_rows.append(max(ys))
    metrics["ground"]={"L2_bottom_internal_range_alpha_gt8":[min(alpha_rows),max(alpha_rows)],
                       "terrain_top":422,"existing_shade_top":bg.shade_y}
    # Ground prototypes: in-memory background draw wrappers, original render order retained.
    class GroundTrial:
        def __init__(self,mode):self.mode=mode
        def draw(self,target,camera_x):
            sky_layer=bg.layers[0];sky_layer.draw(target,camera_x)
            if self.mode=="bridge_color":
                overlay=pygame.Surface(SIZE,pygame.SRCALPHA)
                for y in range(360,540):
                    a=round(255*min(1,max(0,(y-360)/58)))
                    pygame.draw.line(overlay,(38,23,29,a),(0,y),(959,y))
                target.blit(overlay,(0,0))
            for layer in bg.layers[1:]:
                if layer is l2 and self.mode=="shift_down_36":
                    shifted=ImageLayer("qa",layer.surface,layer.factor,layer.y+36,True,True)
                    shifted.draw(target,camera_x)
                else:
                    layer.draw(target,camera_x)
            if self.mode=="lower_only_fill":
                # Diagnostic column extension, not claimed artwork reconstruction.
                p=l2.period;shift=(camera_x*l2.factor)%p
                for sx in range(960):
                    tx=(sx+int(shift))%p
                    ys=[y for y in range(l2.surface.get_height()) if l2.surface.get_at((tx,y)).a>128]
                    if not ys:continue
                    bottom=max(ys)+l2.y
                    if bottom<422:
                        c=l2.surface.get_at((tx,max(ys)))
                        a=max(1,c.a)
                        color=tuple(min(255,round(c[i]*255/a)) for i in range(3))
                        pygame.draw.line(target,color,(sx,bottom+1),(sx,422))
            if bg.decorations:bg.decorations.draw(target,camera_x)
            if bg.shade is not None:target.blit(bg.shade,(0,bg.shade_y))
    for mode in ("baseline","shift_down_36","bridge_color","lower_only_fill"):
        for cx in (0,600,1200,2240):
            world.camera.x=cx;world.player.rect.x=cx+300
            world.wall.segments[0].front_x=cx+140
            world.hover_target=next((e for e in world.enemies if world.camera.is_visible(e.body_rect)
                                     and e.body_rect.right > cx+180),None)
            if world.hover_target:
                mx,my=world.camera.to_screen(*world.hover_target.center)
                world.mouse_screen=(min(950,max(10,mx)),my)
            else:
                world.mouse_screen=(480,300)
            world.background=bg if mode=="baseline" else GroundTrial(mode)
            frame=pygame.Surface(SIZE);world.draw(frame)
            from ui.hud import HUD
            HUD().draw(frame,world)
            save(frame,output/f"ground_{mode}_cam{cx}.png")
    metrics["source_hashes"]={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in ART.glob("*.png")}
    (output/"metrics.json").write_text(json.dumps(metrics,indent=2),encoding="utf-8")
    pygame.quit()
    print("QA artifacts:",output)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,default=Path(__file__).resolve().parent/"results")
    render_study(parser.parse_args().output.resolve())
