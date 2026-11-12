"""QA-only A candidate: isolate repaint to edge bands, keep center EXACT.

Uses rejected finish_v2 only as experimental edge pixels, never active assets.
This demonstrates why unconstrained AI edges do not constitute an accepted fix.
"""
from pathlib import Path
import json
import pygame
import review_methods as study


def run():
    pygame.init();pygame.display.set_mode(study.SIZE)
    output=Path(__file__).resolve().parent/"results"
    sky=pygame.transform.smoothscale(pygame.image.load(str(study.ART/"01_sky.png")),study.SIZE)
    metrics={}
    for label,name,band in [("L1","02_far_castle.png",115),("L2","03_mid_invasion.png",126)]:
        src=pygame.transform.smoothscale(pygame.image.load(str(study.ART/name)),study.SIZE)
        rejected=pygame.transform.smoothscale(pygame.image.load(str(study.ART.parent/"finish_v2"/name)),study.SIZE)
        trial=src.copy()
        # Replace, do not alpha-blend: only the declared edge bands differ.
        trial.fill((0,0,0,0),(0,0,band,540))
        trial.fill((0,0,0,0),(960-band,0,band,540))
        trial.blit(rejected,(0,0),(0,0,band,540),special_flags=pygame.BLEND_RGBA_ADD)
        trial.blit(rejected,(960-band,0),(960-band,0,band,540),special_flags=pygame.BLEND_RGBA_ADD)
        center=(band,0,960-2*band,540)
        invariant=pygame.image.tobytes(src.subsurface(center),"RGBA")==pygame.image.tobytes(trial.subsurface(center),"RGBA")
        tile=trial.premul_alpha()
        sheet=study.join_sheet(tile,sky)
        study.save(sheet,output/f"{label}_A_local_patch_2tiles.png")
        study.save(pygame.transform.scale(sheet.subsurface((810,120,300,330)),(600,660)),
                   output/f"{label}_A_local_patch_join2x.png")
        # Mark the precise edits. This is a scope map, not revised artwork.
        scope=study.compose(src.premul_alpha(),sky,0,0)
        mask=pygame.Surface(study.SIZE,pygame.SRCALPHA)
        mask.fill((255,200,0,55),(0,0,band,540));mask.fill((255,200,0,55),(960-band,0,band,540))
        scope.blit(mask,(0,0));pygame.draw.line(scope,(255,220,40),(band,0),(band,539),2)
        pygame.draw.line(scope,(255,220,40),(960-band,0),(960-band,539),2)
        study.save(scope,output/f"{label}_A_edit_scope.png")
        factor=.15 if label=="L1" else .4
        frames=[study.compose(tile,sky,(960-480)/factor+(i-12)*336/30,factor) for i in range(24)]
        study.apng(frames,output/f"{label}_A_local_patch_scroll.png")
        metrics[label]={"internal_edge_band":band,"central_rgba_exact":invariant,
            "boundary_rgba_mae":study.column_error(tile,959,0),
            "left_patch_internal_cut_mae":study.column_error(tile,band-1,band),
            "right_patch_internal_cut_mae":study.column_error(tile,959-band,960-band),
            "status":"experimental rejected-candidate edges only; NOT active or accepted"}
    (output/"local_patch_metrics.json").write_text(json.dumps(metrics,indent=2),encoding="utf-8")
    pygame.quit()


if __name__=="__main__":run()
