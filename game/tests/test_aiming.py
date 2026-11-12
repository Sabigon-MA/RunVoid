"""Internal-coordinate regressions, NOT native window/DPI conversion tests.

pygame events supplied here are already in 960x540 coordinates. Real Windows
input, SDL letterboxing, resizing and DPI must be checked with manual_aim_probe.
"""
import unittest

from test_gameplay import DT, InputState, step
from test_v20 import aim, click, custom_world, teleport_world
import pygame


class AimingTests(unittest.TestCase):
    def test_selection_tracks_camera_follow_during_movement(self):
        w = custom_world([(0, 422, 3000, 118)], enemies=[(1300, 422)],
                         spawn=(800, 382))
        inp = InputState()
        step(w, inp, 2)
        enemy = w.enemies[0]
        initial_camera = w.camera.x
        inp.simulate_press("right")
        for _ in range(40):
            # This is the position in the last rendered camera, before update.
            aim(w, inp, enemy)
            old_camera = w.camera.x
            step(w, inp)
            self.assertIs(w.hover_target, enemy)
            self.assertAlmostEqual(w.mouse_world[0], inp.mouse_pos[0] + old_camera,
                                   delta=0.001)
        self.assertGreater(w.camera.x, initial_camera + 50)
        # A real input event in internal coordinates must select the same enemy.
        pos = w.camera.to_screen(*enemy.center)
        inp.process_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=pos))
        step(w, inp)
        self.assertEqual(w.teleport.count, 1)

    def test_camera_offsets_include_fractional_positions(self):
        for camera_x in (0, 108, 428.375, 1200.625):
            with self.subTest(camera_x=camera_x):
                w = custom_world([(0, 422, 3000, 118)],
                                 enemies=[(camera_x + 700, 422)])
                inp = InputState()
                w.camera.x = camera_x
                enemy = w.enemies[0]
                aim(w, inp, enemy)
                w._update_mouse(inp)
                self.assertIs(w.hover_target, enemy)
                self.assertAlmostEqual(w.mouse_world[0], enemy.x, delta=0.001)

    def test_after_swap_new_camera_selects_next_enemy_without_consuming_cd(self):
        w = custom_world([(0, 422, 3000, 118)],
                         enemies=[(1050, 422), (1300, 422)], spawn=(800, 382))
        inp = InputState()
        step(w, inp, 2)
        first, second = w.enemies
        old_camera = w.camera.x
        click(w, inp, first)
        self.assertEqual(w.teleport.count, 1)
        self.assertGreater(w.camera.x, old_camera)
        before = w.teleport.cooldown_remaining
        click(w, inp, second)
        self.assertIs(w.hover_target, second)
        self.assertEqual(w.teleport.last_result.reason, "cooldown")
        self.assertAlmostEqual(w.teleport.cooldown_remaining, before - DT)
        self.assertEqual(w.teleport.count, 1)
        while not w.teleport.ready:
            step(w, inp)
        click(w, inp, second)
        self.assertTrue(w.teleport.last_result.ok)
        self.assertEqual(w.teleport.count, 2)

    def test_misses_do_not_spend_ready_or_remaining_cooldown(self):
        for remaining in (0.0, 1.0):
            for pos in ((-1, 412), (960, 412), (500, -1), (500, 540), (0, 0)):
                with self.subTest(remaining=remaining, pos=pos):
                    w, inp, enemy = teleport_world()
                    before = (w.player.rect.copy(), enemy.body_rect.copy())
                    w.teleport.cooldown_remaining = remaining
                    inp.process_event(pygame.event.Event(
                        pygame.MOUSEBUTTONDOWN, button=1, pos=pos))
                    step(w, inp)
                    self.assertIsNone(w.hover_target)
                    self.assertEqual(w.teleport.count, 0)
                    self.assertIsNone(w.teleport.last_result)
                    self.assertAlmostEqual(w.teleport.cooldown_remaining,
                                           max(0, remaining - DT))
                    self.assertEqual((w.player.rect, enemy.body_rect), before)

    def test_outside_view_is_rejected_even_inside_enemy_pick_margin(self):
        w, inp, enemy = teleport_world()
        enemy.x = w.camera.view_rect.right - 1
        inp.process_event(pygame.event.Event(
            pygame.MOUSEBUTTONDOWN, button=1, pos=(961, 412)))
        step(w, inp)
        self.assertIsNone(w.hover_target)
        self.assertEqual((w.teleport.count, w.teleport.cooldown_remaining), (0, 0))

    def test_click_where_enemy_was_before_camera_shift_is_a_miss(self):
        w, inp, enemy = teleport_world()
        old_screen = w.camera.to_screen(*enemy.center)
        w.camera.x += 100
        inp.process_event(pygame.event.Event(
            pygame.MOUSEBUTTONDOWN, button=1, pos=old_screen))
        step(w, inp)
        self.assertIsNone(w.hover_target)
        self.assertEqual((w.teleport.count, w.teleport.cooldown_remaining), (0, 0))


if __name__ == "__main__":
    unittest.main()
