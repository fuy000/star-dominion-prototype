import unittest

from game.scenes.star_map import StarMapScene


class StarMapSceneTests(unittest.TestCase):
    def setUp(self) -> None:
        self.scene = StarMapScene(4000, 2400, 1280, 720, star_count=8)

    def test_world_and_screen_coordinate_conversion_round_trips(self) -> None:
        point = (2130.0, 1190.0)
        screen_point = self.scene.world_to_screen(point)
        round_trip = self.scene.screen_to_world((int(screen_point[0]), int(screen_point[1])))

        self.assertAlmostEqual(round_trip[0], point[0], places=4)
        self.assertAlmostEqual(round_trip[1], point[1], places=4)

    def test_zoom_anchor_keeps_world_position_under_cursor_stable(self) -> None:
        cursor = (930, 410)
        before = self.scene.screen_to_world(cursor)

        self.scene.change_zoom(1, cursor)
        after = self.scene.screen_to_world(cursor)

        self.assertAlmostEqual(before[0], after[0], places=4)
        self.assertAlmostEqual(before[1], after[1], places=4)

    def test_camera_clamps_inside_world_bounds(self) -> None:
        self.scene.move_camera(100000, 100000)
        x, y = self.scene.camera_position

        self.assertLessEqual(x, self.scene.world_size[0])
        self.assertLessEqual(y, self.scene.world_size[1])

    def test_clicking_star_selects_it(self) -> None:
        star = self.scene.stars[0]
        screen_pos = self.scene.world_to_screen((star.x, star.y))
        selected = self.scene.select_star_at_screen_pos((int(screen_pos[0]), int(screen_pos[1])))

        self.assertIsNotNone(selected)
        self.assertEqual(selected.name, star.name)
        self.assertEqual(self.scene.selected_star, selected)


if __name__ == "__main__":
    unittest.main()