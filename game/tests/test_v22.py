"""v2.2 contracts: teleport resources, atomicity, input and boss integration."""
import unittest
import pygame
from test_gameplay import DT, InputState, step
from test_v20 import custom_world, teleport_world
import test_v20 as v20
from bosses import Boss
from systems.world import CLEAR, PLAYING
from systems.combat import AttachedAttack
from stages import parse_stage
from stages.loader import StageFormatError


class ResourceTests(unittest.TestCase):
    def test_air_swap_preserves_used_resources_until_normal_landing(self):
        w, inp, e = teleport_world()
        p = w.player
        p.place_foot(p.rect.centerx, 300)
        p.on_ground = False
        p.jumps_used = 2
        p.air_dashes_remaining = 0
        result = w.teleport.try_teleport(w, e)
        self.assertTrue(result.ok)
        self.assertEqual(w.teleport.cooldown_remaining, 2.0)
        for _ in range(5):
            step(w, inp)
            self.assertEqual((p.jumps_used, p.air_dashes_remaining), (2, 0))
        self.assertFalse(p.try_dash())
        inp.simulate_press("jump")
        step(w, inp)
        self.assertEqual((p.jumps_used, p.air_dashes_remaining), (2, 0))
        self.assertTrue(p.on_ground)
        # Leave the surface, then perform a normal landing.
        p.place_foot(p.rect.centerx, 300)
        p.on_ground = False
        inp.simulate_release("jump")
        for _ in range(120):
            step(w, inp)
            if p.on_ground:
                break
        self.assertTrue(p.on_ground)
        self.assertEqual((p.jumps_used, p.air_dashes_remaining), (0, 1))

    def test_air_to_air_does_not_grant_third_jump(self):
        w, inp, e = teleport_world()
        p = w.player
        p.place_foot(p.rect.centerx, 300)
        e.place_foot(e.x, 300)
        p.on_ground = False
        p.jumps_used, p.air_dashes_remaining = 2, 0
        self.assertTrue(w.teleport.try_teleport(w, e).ok)
        inp.simulate_press("jump")
        step(w, inp)
        self.assertEqual((p.jumps_used, p.air_dashes_remaining), (2, 0))
        self.assertGreaterEqual(p.vy, 0)

    def test_blocked_swap_preserves_both_entities_and_resources(self):
        w = custom_world([(0,422,3000,118),(400,394,400,10)], enemies=[(600,422)])
        p, e = w.player, w.enemies[0]
        p.jumps_used, p.air_dashes_remaining = 2, 0
        before = (p.rect.copy(), e.body_rect.copy(), p.jumps_used, p.air_dashes_remaining)
        self.assertFalse(w.teleport.try_teleport(w, e).ok)
        self.assertEqual((p.rect,e.body_rect,p.jumps_used,p.air_dashes_remaining),before)
        self.assertEqual((w.teleport.count,w.teleport.cooldown_remaining),(0,0))

    def test_partial_air_resources_are_preserved(self):
        w, inp, e = teleport_world()
        p = w.player
        p.place_foot(p.rect.centerx,300)
        p.on_ground = False
        p.jumps_used, p.air_dashes_remaining = 1, 1
        self.assertTrue(w.teleport.try_teleport(w,e).ok)
        step(w,inp,3)
        self.assertEqual((p.jumps_used,p.air_dashes_remaining),(1,1))
        inp.simulate_press("jump")
        step(w,inp)
        self.assertEqual(p.jumps_used,2)
        self.assertLess(p.vy,0)
        self.assertTrue(p.try_dash())
        self.assertEqual(p.air_dashes_remaining,0)

    def test_failed_cooldown_and_offscreen_swaps_preserve_state(self):
        for reason in ("cooldown","offscreen"):
            with self.subTest(reason=reason):
                w,inp,e = teleport_world()
                p = w.player
                p.jumps_used,p.air_dashes_remaining = 2,0
                if reason == "cooldown":
                    w.teleport.cooldown_remaining = 1.0
                else:
                    e.x = w.camera.view_rect.right + 100
                before = (p.rect.copy(),e.body_rect.copy(),p.jumps_used,
                          p.air_dashes_remaining,w.teleport.cooldown_remaining)
                self.assertFalse(w.teleport.try_teleport(w,e).ok)
                self.assertEqual((p.rect,e.body_rect,p.jumps_used,
                                  p.air_dashes_remaining,w.teleport.cooldown_remaining),before)

    def test_attack_can_damage_player_during_swap_contact_grace(self):
        w,inp,e = teleport_world()
        self.assertTrue(w.teleport.try_teleport(w,e).ok)
        hp = w.player.hp
        w.combat.spawn(AttachedAttack(e,1,lambda: w.player.rect.copy(),0.2))
        step(w,inp)
        self.assertGreater(w.contact_grace,0)
        self.assertEqual(w.player.hp,hp-1)


class InputAndResolutionTests(unittest.TestCase):
    def test_button_event_position_selects_enemy_without_motion(self):
        w, inp, e = teleport_world()
        pos = w.camera.to_screen(*e.hurtbox.center)
        inp.mouse_pos = (0,0)
        inp.process_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=pos))
        step(w,inp)
        self.assertEqual(w.teleport.count,1)

    def test_non_native_stage_resolution_is_rejected(self):
        for resolution in ([1920,1080],[960,540,1],[],[960.5,540]):
            with self.subTest(resolution=resolution), self.assertRaises(StageFormatError):
                parse_stage(dict(spawn=dict(x=100,y=100),platforms=[],goal_x=1000,resolution=resolution))


class BossSafetyTests(unittest.TestCase):
    def test_boss_swap_into_pit_is_atomic_failure(self):
        w = custom_world([(0,422,200,118),(500,422,500,118)],spawn=(300,280))
        boss = Boss(700,422)
        w.enemies.append(boss)
        before = (w.player.rect.copy(),boss.body_rect.copy())
        self.assertFalse(w.teleport.try_teleport(w,boss).ok)
        self.assertEqual((w.player.rect,boss.body_rect),before)
        self.assertEqual(w.teleport.cooldown_remaining,0)

    def test_boss_swap_into_wall_region_fails_without_cooldown(self):
        w,inp,e = teleport_world()
        boss = Boss(e.x,422)
        w.enemies = [boss]
        w.wall.segments[0].front_x = w.player.rect.right + 100
        before = (w.player.rect.copy(),boss.body_rect.copy())
        self.assertFalse(w.teleport.try_teleport(w,boss).ok)
        self.assertEqual((w.player.rect,boss.body_rect),before)
        self.assertEqual(w.teleport.cooldown_remaining,0)

    def test_large_boss_cannot_fit_at_player_destination(self):
        w = custom_world([(0,422,3000,118),(50,350,300,10)],spawn=(100,382))
        boss = Boss(700,422)
        w.enemies.append(boss)
        before = (w.player.rect.copy(),boss.body_rect.copy())
        self.assertFalse(w.teleport.try_teleport(w,boss).ok)
        self.assertEqual((w.player.rect,boss.body_rect),before)

    def test_living_boss_blocks_goal_and_attack_defeat_clears(self):
        w,inp,boss = v20.BossTests()._world()
        step(w,inp)
        w.player.rect.right = w.stage.goal_x
        step(w,inp)
        self.assertEqual(w.state,PLAYING)
        boss.take_damage(boss.hp)
        w.kill_enemy(boss,"attack")
        step(w,inp)
        self.assertEqual(w.state,CLEAR)

    def test_environment_death_does_not_clear_or_stop_wall_permanently(self):
        for cause in ("fall","wall"):
            with self.subTest(cause=cause):
                w,inp,boss = v20.BossTests()._world()
                step(w,inp)
                boss.stops_wall_permanently = True
                w.kill_enemy(boss,cause)
                w.player.rect.right = w.stage.goal_x
                step(w,inp)
                self.assertEqual(w.state,PLAYING)
                self.assertFalse(w.wall_halted)
