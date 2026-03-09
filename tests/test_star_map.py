import unittest
from types import SimpleNamespace

from game.runtime import require_pygame
from game.scenes.star_map import DeliveryContract, PlayerShip, StarMapScene, StarSystem


class StarMapSceneTests(unittest.TestCase):
    def setUp(self) -> None:
        self.scene = StarMapScene(4000, 2400, 1280, 720, star_count=8)

    def _configure_linear_lane_scene(self) -> StarMapScene:
        scene = StarMapScene(1000, 700, 800, 600, star_count=0)
        scene._stars = [
            StarSystem("Aster", 100.0, 250.0, 10, 0.0, 2, (220, 220, 255), "Hydrogen", 50.0, 100.0, 2.0),
            StarSystem("Helios", 200.0, 250.0, 10, 0.1, 3, (220, 220, 255), "Crystal", 60.0, 120.0, 3.0),
            StarSystem("Kepler", 300.0, 250.0, 10, 0.2, 4, (220, 220, 255), "Metal", 70.0, 140.0, 4.0),
            StarSystem("Orion", 400.0, 250.0, 10, 0.3, 5, (220, 220, 255), "Hydrogen", 80.0, 160.0, 5.0),
        ]
        scene._lanes = ((0, 1), (1, 2), (2, 3))
        scene._ships = [
            PlayerShip("Flagship", "Command", 0, speed=200.0, color=(170, 245, 255)),
            PlayerShip(
                "Miner-1",
                "Miner",
                0,
                speed=200.0,
                color=(255, 216, 150),
                can_mine=True,
                mining_rate=10.0,
            ),
        ]
        scene._selected_ship_index = 0
        scene._selected_star = None
        scene._credits = 0.0
        scene._delivery_contracts = []
        scene._empire_resources = {"Hydrogen": 0.0, "Crystal": 0.0, "Metal": 0.0}
        return scene

    def _configure_disconnected_scene(self) -> StarMapScene:
        scene = self._configure_linear_lane_scene()
        scene._lanes = ((0, 1), (1, 2))
        return scene

    def _select_miner(self, scene: StarMapScene) -> PlayerShip:
        return scene.cycle_selected_ship()

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

    def test_left_click_can_select_a_miner_ship(self) -> None:
        pygame = require_pygame()
        scene = self._configure_linear_lane_scene()
        miner = scene.ships[1]
        ship_pos = scene._ship_world_position(miner)
        self.assertIsNotNone(ship_pos)
        screen_x, screen_y = scene.world_to_screen(ship_pos)
        offset_x, offset_y = scene._ship_draw_offset(1)

        scene.handle_event(
            SimpleNamespace(
                type=pygame.MOUSEBUTTONDOWN,
                button=1,
                pos=(int(screen_x + offset_x), int(screen_y + offset_y)),
            )
        )

        self.assertIs(scene.selected_ship, miner)
        self.assertIs(scene.selected_star, scene.stars[0])

    def test_ship_click_target_is_forgiving_near_marker_edge(self) -> None:
        scene = self._configure_linear_lane_scene()
        miner = scene.ships[1]
        ship_pos = scene._ship_world_position(miner)
        self.assertIsNotNone(ship_pos)
        screen_x, screen_y = scene.world_to_screen(ship_pos)
        offset_x, offset_y = scene._ship_draw_offset(1)

        selected = scene.ship_at_screen_pos((int(screen_x + offset_x + 16), int(screen_y + offset_y)))

        self.assertIs(selected, miner)

    def test_ship_roles_use_distinct_icon_shapes(self) -> None:
        scene = self._configure_linear_lane_scene()
        flagship_points = scene._ship_icon_points("Command", (200.0, 180.0), 10)
        miner_points = scene._ship_icon_points("Miner", (200.0, 180.0), 10)

        self.assertEqual(len(flagship_points), 4)
        self.assertEqual(len(miner_points), 6)
        self.assertNotEqual(flagship_points, miner_points)

    def test_lane_network_connects_every_star(self) -> None:
        frontier = [self.scene.ship_star]
        visited_ids = {id(self.scene.ship_star)}

        while frontier:
            star = frontier.pop()
            for neighbor in self.scene.connected_stars_for(star):
                if id(neighbor) not in visited_ids:
                    visited_ids.add(id(neighbor))
                    frontier.append(neighbor)

        self.assertEqual(len(visited_ids), len(self.scene.stars))

    def test_ship_can_travel_to_a_connected_star_and_arrive(self) -> None:
        origin = self.scene.ship_star
        destination = self.scene.connected_stars_for(origin)[0]

        self.assertTrue(self.scene.can_travel_to_star(destination))
        self.assertTrue(self.scene.issue_travel_order(destination))
        self.assertTrue(self.scene.ship_is_traveling)
        self.assertIs(self.scene.ship_destination, destination)

        self.scene.update(0.5)
        self.assertNotEqual(
            self.scene.ship_world_position,
            (origin.x, origin.y),
        )

        for _ in range(40):
            self.scene.update(0.5)
            if not self.scene.ship_is_traveling:
                break

        self.assertFalse(self.scene.ship_is_traveling)
        self.assertIs(self.scene.ship_star, destination)
        self.assertEqual(self.scene.ship_world_position, (destination.x, destination.y))

    def test_pathfinding_returns_multi_hop_route_to_non_neighbor(self) -> None:
        scene = self._configure_linear_lane_scene()
        target = scene.stars[3]

        self.assertNotIn(target, scene.connected_stars_for(scene.ship_star))
        self.assertEqual(scene.path_to_star(target), scene.stars)
        self.assertTrue(scene.can_travel_to_star(target))

    def test_ship_can_follow_multi_hop_route_and_arrive(self) -> None:
        scene = self._configure_linear_lane_scene()
        target = scene.stars[3]

        self.assertTrue(scene.issue_travel_order(target))
        self.assertIs(scene.ship_destination, scene.stars[1])
        self.assertEqual(scene.ship_route, scene.stars[1:])
        self.assertIs(scene.ship_final_destination, target)

        scene.update(0.5)
        self.assertIs(scene.ship_star, scene.stars[1])
        self.assertTrue(scene.ship_is_traveling)
        self.assertIs(scene.ship_destination, scene.stars[2])
        self.assertEqual(scene.ship_route, scene.stars[2:])

        scene.update(0.5)
        self.assertIs(scene.ship_star, scene.stars[2])
        self.assertTrue(scene.ship_is_traveling)
        self.assertIs(scene.ship_destination, scene.stars[3])

        scene.update(0.5)
        self.assertFalse(scene.ship_is_traveling)
        self.assertIs(scene.ship_star, target)
        self.assertEqual(scene.ship_route, tuple())

    def test_ship_rejects_travel_when_no_route_exists(self) -> None:
        scene = self._configure_disconnected_scene()
        unreachable = scene.stars[3]

        self.assertEqual(scene.path_to_star(unreachable), tuple())
        self.assertFalse(scene.can_travel_to_star(unreachable))
        self.assertFalse(scene.issue_travel_order(unreachable))
        self.assertFalse(scene.ship_is_traveling)
        self.assertIs(scene.ship_star, scene.stars[0])

    def test_resources_regenerate_up_to_capacity(self) -> None:
        scene = self._configure_linear_lane_scene()
        star = scene.stars[0]
        star.resource_stock = 95.0
        star.resource_capacity = 100.0
        star.production_rate = 10.0

        scene.update(1.0)

        self.assertEqual(star.resource_stock, 100.0)

    def test_mining_loads_resources_into_miner_cargo(self) -> None:
        scene = self._configure_linear_lane_scene()
        miner = self._select_miner(scene)
        star = scene.ship_star
        star.resource_type = "Hydrogen"
        star.resource_stock = 50.0
        star.production_rate = 0.0
        miner.mining_rate = 10.0

        self.assertTrue(scene.toggle_mining(star))

        scene.update(2.0)

        self.assertTrue(scene.ship_is_mining)
        self.assertEqual(star.resource_stock, 30.0)
        self.assertEqual(miner.cargo_resource_type, "Hydrogen")
        self.assertEqual(miner.cargo_amount, 20.0)
        self.assertEqual(scene.empire_resources["Hydrogen"], 0.0)

    def test_mining_can_only_start_at_current_system(self) -> None:
        scene = self._configure_linear_lane_scene()
        self._select_miner(scene)

        self.assertFalse(scene.toggle_mining(scene.stars[1]))
        self.assertFalse(scene.ship_is_mining)

    def test_flagship_cannot_start_mining(self) -> None:
        scene = self._configure_linear_lane_scene()

        self.assertEqual(scene.selected_ship.role, "Command")
        self.assertFalse(scene.toggle_mining(scene.ship_star))

    def test_mining_stops_after_star_is_depleted(self) -> None:
        scene = self._configure_linear_lane_scene()
        miner = self._select_miner(scene)
        star = scene.ship_star
        star.resource_type = "Hydrogen"
        star.resource_stock = 8.0
        star.production_rate = 5.0
        miner.mining_rate = 10.0

        self.assertTrue(scene.toggle_mining(star))

        scene.update(1.0)
        first_total = miner.cargo_amount

        self.assertEqual(first_total, 8.0)
        self.assertFalse(scene.ship_is_mining)

        scene.update(1.0)

        self.assertEqual(miner.cargo_amount, first_total)

    def test_delivery_contract_awards_credits_when_cargo_reaches_destination(self) -> None:
        scene = self._configure_linear_lane_scene()
        miner = self._select_miner(scene)
        miner.cargo_resource_type = "Hydrogen"
        miner.cargo_amount = 12.0
        scene._delivery_contracts = [DeliveryContract(2, "Hydrogen", 10.0, 6)]

        self.assertTrue(scene.issue_travel_order(scene.stars[2]))

        scene.update(0.5)
        scene.update(0.5)

        self.assertIs(scene.ship_star, scene.stars[2])
        self.assertEqual(scene.credits, 60.0)
        self.assertEqual(miner.cargo_amount, 2.0)
        self.assertEqual(miner.cargo_resource_type, "Hydrogen")
        self.assertEqual(scene.empire_resources["Hydrogen"], 10.0)
        self.assertEqual(scene.delivery_contracts, tuple())

    def test_miner_ship_can_travel_and_mine_after_arrival(self) -> None:
        scene = self._configure_linear_lane_scene()
        miner = self._select_miner(scene)
        target = scene.stars[2]
        target.resource_type = "Metal"
        target.resource_stock = 30.0
        target.production_rate = 0.0
        miner.mining_rate = 6.0

        self.assertEqual(scene.selected_ship.role, "Miner")
        self.assertTrue(scene.issue_travel_order(target))

        scene.update(0.5)
        self.assertIs(scene.ship_star, scene.stars[1])
        scene.update(0.5)
        self.assertIs(scene.ship_star, target)
        self.assertFalse(scene.ship_is_traveling)

        self.assertTrue(scene.toggle_mining(target))
        scene.update(2.0)

        self.assertEqual(miner.cargo_resource_type, "Metal")
        self.assertEqual(miner.cargo_amount, 12.0)
        self.assertEqual(target.resource_stock, 18.0)


if __name__ == "__main__":
    unittest.main()
