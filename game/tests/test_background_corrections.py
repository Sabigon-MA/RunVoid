"""Anchor-preserving crop extension and behind-scenery ground connection."""
import copy
import dataclasses
import json
from pathlib import Path
import unittest

import test_background as baseline
from test_gameplay import STAGE_1
import pygame
from stages.background import BackgroundConfigError, ParallaxImageBackground, build_background, clear_cache
from stages import load_stage, parse_stage
from stages.loader import StageFormatError
from stages.renderer import TwilightRuinsBackground, make_background


def raw_stage():
    return json.loads((Path(__file__).resolve().parents[1]/"stages/stage_1.json").read_text(encoding="utf-8"))


def previous_stage():
    raw=raw_stage()
    raw["background"].pop("ground_connector",None)
    sprite=raw["background"]["decorations"]["sprites"]["ruin_right"]
    sprite["src"]=sprite.pop("anchor_src")
    return parse_stage(raw)


class AnchoredCropTests(unittest.TestCase):
    def setUp(self):
        self.old=ParallaxImageBackground(previous_stage().background,960,540).decorations
        self.new=ParallaxImageBackground(STAGE_1.background,960,540).decorations

    def test_existing_rock_pixels_and_sampling_grid_are_exactly_preserved(self):
        old_img=self.old.sprites["ruin_right"]
        new_img=self.new.sprites["ruin_right"]
        padding=round(90*960/1672)
        self.assertGreater(new_img.get_width(),old_img.get_width())
        kept=new_img.subsurface((padding,0,*old_img.get_size()))
        self.assertEqual(pygame.image.tobytes(kept,"RGBA"),pygame.image.tobytes(old_img,"RGBA"))
        # Added grass is real content, not just transparent padding.
        self.assertGreater(new_img.subsurface((0,0,padding,new_img.get_height())).get_bounding_rect().width,0)

    def test_existing_object_screen_coordinates_do_not_move(self):
        old_p=next(p for p in self.old.items if p.sprite=="ruin_right")
        new_p=next(p for p in self.new.items if p.sprite=="ruin_right")
        self.assertEqual(old_p,new_p)
        padding=round(90*960/1672)
        for cam in (-5000.25,-.01,0,123.75,600,1200,2240,3360,90000):
            for offset in (-3360,0,3360):
                with self.subTest(cam=cam,offset=offset):
                    ox,oy=self.old.screen_pos(old_p,cam,offset)
                    nx,ny=self.new.screen_pos(new_p,cam,offset)
                    self.assertEqual((nx+padding,ny),(ox,oy))

    def test_extension_is_culled_by_full_visible_extent(self):
        p=next(p for p in self.new.items if p.sprite=="ruin_right")
        for cam in (0,600,1200,2200,2240,3000,5000):
            expected=[]
            for off in (n*3360 for n in range(-5,6)):
                for item in self.new.items:
                    x,y=self.new.screen_pos(item,cam,off)
                    if x<960 and x+self.new.sprites[item.sprite].get_width()>0:
                        expected.append((item.sprite,x,y))
            self.assertEqual(sorted(self.new.visible(cam)),sorted(expected))

    def test_invalid_anchor_rectangles_fail_during_parse(self):
        for anchor in ([0,0,10,10],[1330,640,0,10],[1330,640,True,10],"rect",[1330,640,342]):
            raw=raw_stage();raw["background"]["decorations"]["sprites"]["ruin_right"]["anchor_src"]=anchor
            with self.subTest(anchor=anchor),self.assertRaises(StageFormatError):
                parse_stage(raw)

    def test_programmatic_anchor_outside_crop_is_rejected(self):
        config=STAGE_1.background;dd=config.decorations
        wrong=dataclasses.replace(dd.sprites[-1],anchor_src=(0,0,10,10))
        config=dataclasses.replace(config,decorations=dataclasses.replace(dd,sprites=(*dd.sprites[:-1],wrong)))
        with self.assertRaises(BackgroundConfigError):ParallaxImageBackground(config,960,540)


class GroundConnectorTests(unittest.TestCase):
    def test_layer_shapes_positions_periods_and_pixels_are_unchanged(self):
        old=ParallaxImageBackground(previous_stage().background,960,540)
        new=ParallaxImageBackground(STAGE_1.background,960,540)
        for a,b in zip(old.layers,new.layers):
            self.assertEqual((a.id,a.y,a.factor,a.period),(b.id,b.y,b.factor,b.period))
            self.assertEqual(pygame.image.tobytes(a.surface,"RGBA"),pygame.image.tobytes(b.surface,"RGBA"))

    def test_connector_changes_only_lower_backdrop_without_decorations(self):
        config=dataclasses.replace(STAGE_1.background,decorations=None)
        old=ParallaxImageBackground(dataclasses.replace(config,ground_connector=None),960,540)
        new=ParallaxImageBackground(config,960,540)
        for camera in (0,600,1200,2159.9,2160,2160.1,2240):
            a=pygame.Surface((960,540));b=a.copy();old.draw(a,camera);new.draw(b,camera)
            self.assertEqual(pygame.image.tobytes(a.subsurface((0,0,960,360)),"RGB"),
                             pygame.image.tobytes(b.subsurface((0,0,960,360)),"RGB"))
            self.assertNotEqual(pygame.image.tobytes(a.subsurface((0,390,960,28)),"RGB"),
                                pygame.image.tobytes(b.subsurface((0,390,960,28)),"RGB"))

    def test_connector_is_drawn_before_named_layer(self):
        bg=ParallaxImageBackground(STAGE_1.background,960,540)
        calls=[]
        class Layer:
            def __init__(self,name):self.id=name
            def draw(self,target,camera):calls.append((self.id,target.get_at((900,430))[:3]))
        bg.layers=[Layer("L0_sky"),Layer("L1_far_castle"),Layer("L2_mid_invasion")]
        bg.decorations=None;bg.shade=None
        target=pygame.Surface((960,540));target.fill((255,100,100));bg.draw(target,0)
        self.assertEqual(calls[0][1],(255,100,100))
        self.assertEqual(calls[1][1],(38,23,29))
        self.assertEqual(calls[2][1],(38,23,29))

    def test_unknown_or_sky_target_is_invalid(self):
        for name in ("missing","L0_sky"):
            raw=raw_stage();raw["background"]["ground_connector"]["before_layer"]=name
            with self.subTest(name=name),self.assertRaises(StageFormatError):parse_stage(raw)

    def test_optional_connector_keeps_legacy_config_compatible(self):
        self.assertIsNone(previous_stage().background.ground_connector)
        legacy=load_stage(Path(__file__).parent/"fixtures/legacy_stage.json")
        self.assertIsNone(legacy.background)

    def test_cache_distinguishes_connector_settings(self):
        clear_cache();a=build_background(STAGE_1.background,960,540)
        no_connector=dataclasses.replace(STAGE_1.background,ground_connector=None)
        b=build_background(no_connector,960,540)
        self.assertIsNot(a,b)
        self.assertIs(a,build_background(STAGE_1.background,960,540))

    def test_missing_assets_still_fall_back_with_connector_and_anchor(self):
        clear_cache();config=dataclasses.replace(STAGE_1.background,asset_dir="assets/does-not-exist-codex-qa")
        with self.assertLogs("runvoid.background",level="WARNING"):
            bg=make_background(STAGE_1.theme,960,540,config)
        self.assertIsInstance(bg,TwilightRuinsBackground)

    def test_gameplay_trace_matches_pre_correction_background(self):
        run=baseline.GameplayIndependenceTests.scripted_run
        self.assertEqual(run(STAGE_1,True),run(previous_stage(),True))


if __name__=="__main__":unittest.main()
