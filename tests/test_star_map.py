import unittest
from math import hypot
from types import SimpleNamespace

from game.runtime import require_pygame
from game.scenes.star_map import (
    AsteroidField,
    SectorPlanet,
    STRUCTURE_DEFENSE_STATION,
    STRUCTURE_MINING_STATION,
    STRUCTURE_SHIPYARD,
    DeliveryContract,
    EnemyShip,
    PirateBase,
    PlayerShip,
    StarMapScene,
    StarSystem,
)


class StarMapSceneTests(unittest.TestCase):
    def setUp(self) -> None:
        self.scene = StarMapScene(4000, 2400, 1280, 720, star_count=8, enemy_count=0)

    def _configure_linear_lane_scene(self) -> StarMapScene:
        scene = StarMapScene(1000, 700, 800, 600, star_count=0, enemy_count=0)
        scene._stars = [
            StarSystem("Aster", 100.0, 250.0, 10, 0.0, 2, (220, 220, 255), "Hydrogen", 50.0, 100.0, 2.0),
            StarSystem("Helios", 200.0, 250.0, 10, 0.1, 3, (220, 220, 255), "Crystal", 60.0, 120.0, 3.0),
            StarSystem("Kepler", 300.0, 250.0, 10, 0.2, 4, (220, 220, 255), "Metal", 70.0, 140.0, 4.0),
            StarSystem("Orion", 400.0, 250.0, 10, 0.3, 5, (220, 220, 255), "Hydrogen", 80.0, 160.0, 5.0),
        ]
        scene._lanes = ((0, 1), (1, 2), (2, 3))
        scene._star_regions = (0, 0, 1, 2)
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
        scene._stars[0].owner = "Player"
        scene._selected_ship_index = 0
        scene._selected_star = None
        scene._selected_object_id = None
        scene._credits = 0.0
        scene._delivery_contracts = []
        scene._enemy_ships = []
        scene._empire_resources = {"Hydrogen": 0.0, "Crystal": 0.0, "Metal": 0.0}
        scene._rebuild_sector_interiors()
        for ship in scene._ships:
            scene._dock_ship_in_sector(ship, ship.current_star_index)
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

    def test_new_scene_starts_with_500_credits(self) -> None:
        self.assertEqual(self.scene.credits, 500.0)

    def test_new_scene_starts_with_home_shipyard_level_one(self) -> None:
        home_star = self.scene.stars[0]

        self.assertEqual(home_star.owner, "Player")
        self.assertEqual(home_star.structure, STRUCTURE_SHIPYARD)
        self.assertEqual(home_star.structure_level, 1)

    def test_new_scene_starts_with_slower_ship_speeds(self) -> None:
        command_ship = self.scene.ships[0]
        miner_ships = self.scene.ships[1:]

        self.assertEqual(command_ship.speed, 270.0)
        self.assertTrue(all(ship.speed == 225.0 for ship in miner_ships))

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
        planet = scene.sector_planets[0]
        ship_pos = scene._ship_world_position(miner)
        self.assertIsNotNone(ship_pos)
        screen_x, screen_y = scene.world_to_screen(ship_pos)
        offset_x, offset_y = scene._ship_draw_offset(miner, 1, scene._ships)

        scene.handle_event(
            SimpleNamespace(
                type=pygame.MOUSEBUTTONDOWN,
                button=1,
                pos=(int(screen_x + offset_x), int(screen_y + offset_y)),
            )
        )

        self.assertIs(scene.selected_sector_object, planet)
        self.assertFalse(scene.show_ship_details)

        scene.handle_event(
            SimpleNamespace(
                type=pygame.MOUSEBUTTONDOWN,
                button=1,
                pos=(int(screen_x + offset_x), int(screen_y + offset_y)),
            )
        )

        self.assertIs(scene.selected_ship, miner)
        self.assertIs(scene.selected_star, scene.stars[0])
        self.assertTrue(scene.show_ship_details)

    def test_left_clicking_planet_center_prefers_planet_over_docked_ship(self) -> None:
        pygame = require_pygame()
        scene = self._configure_linear_lane_scene()
        planet = scene.sector_planets[0]
        screen_pos = scene.world_to_screen(scene._sector_object_world_position(planet))

        scene.handle_event(
            SimpleNamespace(
                type=pygame.MOUSEBUTTONDOWN,
                button=1,
                pos=(int(screen_pos[0]), int(screen_pos[1])),
            )
        )

        self.assertIs(scene.selected_sector_object, planet)
        self.assertIs(scene.selected_star, scene.stars[0])
        self.assertFalse(scene.show_ship_details)

    def test_left_clicking_star_center_defaults_to_planet_selection(self) -> None:
        pygame = require_pygame()
        scene = self._configure_linear_lane_scene()
        star = scene.stars[1]
        planet = scene.sector_planets[1]
        screen_pos = scene.world_to_screen((star.x, star.y))

        scene.handle_event(
            SimpleNamespace(
                type=pygame.MOUSEBUTTONDOWN,
                button=1,
                pos=(int(screen_pos[0]), int(screen_pos[1])),
            )
        )

        self.assertIs(scene.selected_star, star)
        self.assertIs(scene.selected_sector_object, planet)
        self.assertFalse(scene.show_ship_details)

    def test_linear_scene_rebuilds_scattered_sector_contents(self) -> None:
        scene = self._configure_linear_lane_scene()

        planet_counts = {star_index: 0 for star_index in range(len(scene.stars))}
        asteroid_counts = {star_index: 0 for star_index in range(len(scene.stars))}
        for planet in scene.sector_planets:
            planet_counts[planet.star_index] += 1
        for asteroid in scene.asteroid_fields:
            asteroid_counts[asteroid.star_index] += 1

        self.assertTrue(all(count >= 1 for count in planet_counts.values()))
        self.assertTrue(any(count > 1 for count in planet_counts.values()))
        self.assertTrue(all(count >= 4 for count in asteroid_counts.values()))
        self.assertTrue(all(isinstance(planet, SectorPlanet) for planet in scene.sector_planets))
        self.assertTrue(all(isinstance(asteroid, AsteroidField) for asteroid in scene.asteroid_fields))

        for star_index in range(len(scene.stars)):
            planets = [planet for planet in scene.sector_planets if planet.star_index == star_index]
            asteroids = [asteroid for asteroid in scene.asteroid_fields if asteroid.star_index == star_index]
            self.assertTrue(all(planets[0].radius > asteroid.radius for asteroid in asteroids))
            sector_left, sector_top, sector_size = scene._sector_world_rect(star_index)
            sector_right = sector_left + sector_size
            sector_bottom = sector_top + sector_size

            for sector_object in (*planets, *asteroids):
                world_x, world_y = scene._sector_object_world_position(sector_object)
                self.assertGreaterEqual(world_x, sector_left)
                self.assertLessEqual(world_x, sector_right)
                self.assertGreaterEqual(world_y, sector_top)
                self.assertLessEqual(world_y, sector_bottom)

            for asteroid_index, asteroid in enumerate(asteroids):
                for other in asteroids[asteroid_index + 1 :]:
                    spacing = hypot(asteroid.offset_x - other.offset_x, asteroid.offset_y - other.offset_y)
                    self.assertGreaterEqual(spacing, 10.0)

    def test_selecting_a_star_hides_ship_detail_panel(self) -> None:
        scene = self._configure_linear_lane_scene()
        scene._show_ship_details = True

        star = scene.stars[1]
        screen_pos = scene.world_to_screen((star.x, star.y))
        selected = scene.select_star_at_screen_pos((int(screen_pos[0]), int(screen_pos[1])))

        self.assertIs(selected, star)
        self.assertFalse(scene.show_ship_details)

    def test_help_button_click_toggles_help_panel(self) -> None:
        pygame = require_pygame()
        scene = self._configure_linear_lane_scene()
        button_rect = scene._help_button_rect()

        scene.handle_event(
            SimpleNamespace(
                type=pygame.MOUSEBUTTONDOWN,
                button=1,
                pos=button_rect.center,
            )
        )

        self.assertTrue(scene.show_help_panel)

        scene.handle_event(
            SimpleNamespace(
                type=pygame.MOUSEBUTTONDOWN,
                button=1,
                pos=button_rect.center,
            )
        )

        self.assertFalse(scene.show_help_panel)

    def test_h_key_toggles_help_panel(self) -> None:
        pygame = require_pygame()
        scene = self._configure_linear_lane_scene()

        scene.handle_event(SimpleNamespace(type=pygame.KEYDOWN, key=pygame.K_h))
        self.assertTrue(scene.show_help_panel)

        scene.handle_event(SimpleNamespace(type=pygame.KEYDOWN, key=pygame.K_h))
        self.assertFalse(scene.show_help_panel)

    def test_escape_key_closes_help_panel(self) -> None:
        pygame = require_pygame()
        scene = self._configure_linear_lane_scene()
        scene._show_help_panel = True
        scene._show_operations_panel = True

        scene.handle_event(SimpleNamespace(type=pygame.KEYDOWN, key=pygame.K_ESCAPE))

        self.assertFalse(scene.show_help_panel)
        self.assertFalse(scene.show_operations_panel)

    def test_selected_planet_summary_lines_include_structure_details(self) -> None:
        scene = self._configure_linear_lane_scene()
        star = scene.stars[0]
        planet = scene.sector_planets[0]
        star.structure = STRUCTURE_SHIPYARD
        star.structure_level = 2
        scene._selected_star = star
        scene._selected_object_id = planet.id

        lines = scene._selection_panel_lines(scene.selected_ship)

        self.assertIn(f"{planet.name} | {star.name} | Owner {star.owner} | Richness {star.richness}/5", lines)
        self.assertIn("Structure: Shipyard Lv2", lines)
        self.assertIn(scene._structure_description(STRUCTURE_SHIPYARD, 2), lines)
        self.assertIn(f"Upgrade: press U for Lv3 ({scene._structure_upgrade_cost(star)} c)", lines)
        self.assertIn(scene._shipyard_production_text(star), lines)

    def test_help_panel_lines_include_structure_guidance(self) -> None:
        scene = self._configure_linear_lane_scene()
        lines = scene._help_panel_lines()

        self.assertIn("Owned star: 1 Shipyard | 2 Defense | 3 Mining | U upgrade", lines)
        self.assertIn("Shipyard: 4 buy Miner | 5 buy Escort at Lv3", lines)
        self.assertNotIn("Use Planet Ops for build, upgrade, and repair details", lines)

    def test_ship_click_target_is_forgiving_near_marker_edge(self) -> None:
        scene = self._configure_linear_lane_scene()
        miner = scene.ships[1]
        ship_pos = scene._ship_world_position(miner)
        self.assertIsNotNone(ship_pos)
        screen_x, screen_y = scene.world_to_screen(ship_pos)
        offset_x, offset_y = scene._ship_draw_offset(miner, 1, scene._ships)

        selected = scene.ship_at_screen_pos((int(screen_x + offset_x + 16), int(screen_y + offset_y)))

        self.assertIs(selected, miner)

    def test_ships_only_spread_apart_when_multiple_are_docked_together(self) -> None:
        scene = self._configure_linear_lane_scene()

        flagship = scene.ships[0]
        miner = scene.ships[1]
        flagship_offset = scene._ship_draw_offset(flagship, 0, scene._ships)
        miner_offset = scene._ship_draw_offset(miner, 1, scene._ships)
        distance = ((miner_offset[0] - flagship_offset[0]) ** 2 + (miner_offset[1] - flagship_offset[1]) ** 2) ** 0.5

        self.assertGreaterEqual(distance, 25.0)

        miner.current_star_index = 1
        miner.origin_star_index = 0
        miner.destination_star_index = 1
        miner.travel_progress = 0.5
        self.assertEqual(scene._ship_draw_offset(miner, 1, scene._ships), (0, 0))

        flagship.current_star_index = 0
        miner.current_star_index = 1
        miner.origin_star_index = None
        miner.destination_star_index = None
        miner.travel_progress = 0.0
        self.assertEqual(scene._ship_draw_offset(flagship, 0, scene._ships), (0, 0))
        self.assertEqual(scene._ship_draw_offset(miner, 1, scene._ships), (0, 0))

    def test_ship_roles_use_distinct_icon_shapes(self) -> None:
        scene = self._configure_linear_lane_scene()
        flagship_points = scene._ship_icon_points("Command", (200.0, 180.0), 10)
        miner_points = scene._ship_icon_points("Miner", (200.0, 180.0), 10)

        self.assertEqual(len(flagship_points), 4)
        self.assertEqual(len(miner_points), 4)
        self.assertNotEqual(flagship_points, miner_points)

    def test_ship_render_radius_is_larger_for_visibility(self) -> None:
        scene = self._configure_linear_lane_scene()

        self.assertEqual(scene._ship_render_radius(False), 11)
        self.assertEqual(scene._ship_render_radius(True), 14)
        self.assertGreater(scene._ship_click_radius(False), 20.0)

    def test_ship_health_bar_geometry_uses_hull_fraction_for_fill_width(self) -> None:
        scene = self._configure_linear_lane_scene()
        ship = scene.ships[0]
        ship.max_hull = 100.0
        ship.hull = 50.0

        background_rect, fill_rect = scene._ship_health_bar_geometry(200.0, 180.0, 10, ship)

        self.assertEqual(background_rect, (186, 161, 28, 4))
        self.assertEqual(fill_rect, (187, 162, 13, 2))

    def test_ship_health_bar_geometry_clamps_empty_and_overfull_hull(self) -> None:
        scene = self._configure_linear_lane_scene()
        ship = scene.ships[1]
        ship.max_hull = 72.0
        ship.hull = -5.0

        background_rect, fill_rect = scene._ship_health_bar_geometry(150.0, 120.0, 8, ship)
        self.assertEqual(fill_rect[2], 0)

        ship.hull = 150.0
        _, full_fill_rect = scene._ship_health_bar_geometry(150.0, 120.0, 8, ship)
        self.assertEqual(full_fill_rect[2], background_rect[2] - 2)

    def test_flagship_can_claim_adjacent_neutral_star(self) -> None:
        scene = self._configure_linear_lane_scene()
        target = scene.stars[1]
        scene._credits = scene._claim_cost(target)

        self.assertTrue(scene.issue_travel_order(target))
        scene.update(0.5)
        self.assertIs(scene.ship_star, target)
        self.assertTrue(scene.can_claim_star(target))
        self.assertTrue(scene.claim_star(target))
        self.assertEqual(target.owner, "Player")
        self.assertEqual(scene.credits, 0.0)

    def test_miner_cannot_claim_star(self) -> None:
        scene = self._configure_linear_lane_scene()
        target = scene.stars[1]
        scene._credits = 500.0
        self._select_miner(scene)

        self.assertTrue(scene.issue_travel_order(target))
        scene.update(0.5)
        self.assertFalse(scene.can_claim_star(target))
        self.assertFalse(scene.claim_star(target))
        self.assertEqual(target.owner, "Neutral")

    def test_cannot_claim_without_enough_credits(self) -> None:
        scene = self._configure_linear_lane_scene()
        target = scene.stars[1]
        scene._credits = scene._claim_cost(target) - 1

        self.assertTrue(scene.issue_travel_order(target))
        scene.update(0.5)
        self.assertFalse(scene.can_claim_star(target))
        self.assertFalse(scene.claim_star(target))
        self.assertEqual(target.owner, "Neutral")

    def test_cannot_claim_star_that_does_not_border_owned_territory(self) -> None:
        scene = self._configure_linear_lane_scene()
        target = scene.stars[2]
        scene._credits = 500.0

        self.assertTrue(scene.issue_travel_order(target))
        scene.update(0.5)
        scene.update(0.5)
        self.assertIs(scene.ship_star, target)
        self.assertFalse(scene.can_claim_star(target))
        self.assertFalse(scene.claim_star(target))
        self.assertEqual(target.owner, "Neutral")

    def test_home_system_alone_does_not_generate_passive_income(self) -> None:
        scene = self._configure_linear_lane_scene()

        scene.update(5.0)

        self.assertEqual(scene.passive_income_rate, 0.0)
        self.assertEqual(scene.credits, 0.0)

    def test_claimed_territory_generates_passive_income(self) -> None:
        scene = self._configure_linear_lane_scene()
        target = scene.stars[1]
        scene._credits = scene._claim_cost(target)

        self.assertTrue(scene.issue_travel_order(target))
        scene.update(0.5)
        self.assertTrue(scene.claim_star(target))

        expected_rate = scene._territory_income_rate(target)
        scene.update(2.0)

        self.assertEqual(scene.passive_income_rate, expected_rate)
        self.assertAlmostEqual(scene.credits, expected_rate * 2.0)

    def test_can_build_structure_on_owned_star_and_spends_credits(self) -> None:
        scene = self._configure_linear_lane_scene()
        star = scene.stars[0]
        scene._selected_star = star
        scene._credits = scene._structure_cost(STRUCTURE_SHIPYARD)

        self.assertTrue(scene.can_build_structure(STRUCTURE_SHIPYARD, star))
        self.assertTrue(scene.build_structure(STRUCTURE_SHIPYARD, star))
        self.assertEqual(star.structure, STRUCTURE_SHIPYARD)
        self.assertEqual(star.structure_level, 1)
        self.assertEqual(scene.credits, 0.0)

    def test_cannot_build_structure_on_unowned_or_already_built_star(self) -> None:
        scene = self._configure_linear_lane_scene()
        target = scene.stars[1]
        scene._credits = 500.0

        self.assertFalse(scene.build_structure(STRUCTURE_MINING_STATION, target))

        target.owner = "Player"
        self.assertTrue(scene.build_structure(STRUCTURE_MINING_STATION, target))
        self.assertFalse(scene.build_structure(STRUCTURE_DEFENSE_STATION, target))

    def test_can_upgrade_structure_on_owned_star_and_spends_credits(self) -> None:
        scene = self._configure_linear_lane_scene()
        star = scene.stars[0]
        star.structure = STRUCTURE_SHIPYARD
        star.structure_level = 1
        scene._selected_star = star
        scene._credits = scene._structure_upgrade_cost(star)

        self.assertTrue(scene.can_upgrade_structure(star))
        self.assertTrue(scene.upgrade_structure(star))
        self.assertEqual(star.structure_level, 2)
        self.assertEqual(scene.credits, 0.0)

    def test_purchase_miner_at_shipyard_creates_ship_and_spends_credits(self) -> None:
        scene = self._configure_linear_lane_scene()
        star = scene.stars[0]
        star.structure = STRUCTURE_SHIPYARD
        star.structure_level = 1
        scene._selected_star = star
        scene._credits = scene._ship_purchase_cost("Miner")
        ship_count = len(scene.ships)

        self.assertTrue(scene.purchase_ship("Miner", star))

        new_ship = scene.ships[-1]
        self.assertEqual(len(scene.ships), ship_count + 1)
        self.assertEqual(new_ship.role, "Miner")
        self.assertTrue(new_ship.can_mine)
        self.assertEqual(new_ship.current_star_index, 0)
        self.assertIs(scene.selected_ship, new_ship)
        self.assertEqual(scene.credits, 0.0)

    def test_escort_purchase_unlocks_at_shipyard_level_three(self) -> None:
        scene = self._configure_linear_lane_scene()
        star = scene.stars[0]
        star.structure = STRUCTURE_SHIPYARD
        scene._selected_star = star
        scene._credits = 1000.0

        self.assertFalse(scene.can_purchase_ship("Escort", star))

        star.structure_level = 3
        self.assertTrue(scene.can_purchase_ship("Escort", star))
        self.assertTrue(scene.purchase_ship("Escort", star))
        self.assertEqual(scene.ships[-1].role, "Escort")
        self.assertFalse(scene.ships[-1].can_mine)

    def test_keyboard_upgrade_and_purchase_controls_work_on_shipyard(self) -> None:
        pygame = require_pygame()
        scene = self._configure_linear_lane_scene()
        star = scene.stars[0]
        star.structure = STRUCTURE_SHIPYARD
        star.structure_level = 1
        scene._selected_star = star
        scene._credits = 1000.0
        ship_count = len(scene.ships)

        scene.handle_event(SimpleNamespace(type=pygame.KEYDOWN, key=pygame.K_4))
        scene.handle_event(SimpleNamespace(type=pygame.KEYDOWN, key=pygame.K_u))
        scene.handle_event(SimpleNamespace(type=pygame.KEYDOWN, key=pygame.K_u))
        scene.handle_event(SimpleNamespace(type=pygame.KEYDOWN, key=pygame.K_5))

        self.assertEqual(len(scene.ships), ship_count + 2)
        self.assertEqual(star.structure_level, 3)
        self.assertEqual(scene.ships[-2].role, "Miner")
        self.assertEqual(scene.ships[-1].role, "Escort")

    def test_number_key_builds_selected_star_structure(self) -> None:
        pygame = require_pygame()
        scene = self._configure_linear_lane_scene()
        scene._selected_star = scene.stars[0]
        scene._credits = 500.0

        scene.handle_event(SimpleNamespace(type=pygame.KEYDOWN, key=pygame.K_2))

        self.assertEqual(scene.stars[0].structure, STRUCTURE_DEFENSE_STATION)

    def test_selected_asteroid_blocks_building_until_planet_is_selected(self) -> None:
        scene = self._configure_linear_lane_scene()
        star = scene.stars[0]
        asteroid = scene.asteroid_fields[0]
        planet = scene.sector_planets[0]
        scene._selected_star = star
        scene._selected_object_id = asteroid.id
        scene._credits = scene._structure_cost(STRUCTURE_DEFENSE_STATION)

        self.assertFalse(scene.can_build_structure(STRUCTURE_DEFENSE_STATION))

        scene._selected_object_id = planet.id
        self.assertTrue(scene.can_build_structure(STRUCTURE_DEFENSE_STATION))

    def test_structure_marker_style_uses_expected_palette(self) -> None:
        scene = self._configure_linear_lane_scene()

        self.assertEqual(scene._structure_marker_style(STRUCTURE_SHIPYARD), ("plus", (92, 230, 146)))
        self.assertEqual(scene._structure_marker_style(STRUCTURE_DEFENSE_STATION), ("triangle", (235, 96, 96)))
        self.assertEqual(scene._structure_marker_style(STRUCTURE_MINING_STATION), ("square", (244, 208, 90)))

    def test_shipyard_repairs_docked_player_ships(self) -> None:
        scene = self._configure_linear_lane_scene()
        star = scene.stars[0]
        ship = scene.ships[0]
        star.structure = STRUCTURE_SHIPYARD
        ship.hull = 80.0

        scene.update(2.0)

        self.assertEqual(ship.hull, ship.max_hull)

    def test_shipyard_repairs_scale_with_structure_level(self) -> None:
        scene = self._configure_linear_lane_scene()
        star = scene.stars[0]
        ship = scene.ships[0]
        star.structure = STRUCTURE_SHIPYARD
        star.structure_level = 3
        ship.hull = 60.0

        scene.update(1.0)

        self.assertEqual(ship.hull, 84.0)

    def test_mining_station_boosts_star_regeneration(self) -> None:
        scene = self._configure_linear_lane_scene()
        star = scene.stars[0]
        star.structure = STRUCTURE_MINING_STATION
        star.resource_stock = 50.0
        star.resource_capacity = 100.0
        star.production_rate = 4.0

        scene.update(2.0)

        self.assertEqual(star.resource_stock, 64.0)

    def test_mining_station_upgrade_increases_star_regeneration(self) -> None:
        scene = self._configure_linear_lane_scene()
        star = scene.stars[0]
        star.structure = STRUCTURE_MINING_STATION
        star.structure_level = 2
        star.resource_stock = 50.0
        star.resource_capacity = 100.0
        star.production_rate = 4.0

        scene.update(2.0)

        self.assertEqual(star.resource_stock, 68.0)

    def test_pirate_base_generation_prefers_outer_non_adjacent_stars(self) -> None:
        scene = self._configure_linear_lane_scene()

        bases = scene._generate_pirate_bases(home_star_index=0, pirate_base_count=2)

        self.assertEqual([base.star_index for base in bases], [3, 1])

    def test_pirate_base_does_not_spawn_raider_after_cooldown(self) -> None:
        scene = self._configure_linear_lane_scene()
        scene._pirate_bases = [PirateBase(star_index=3, spawn_cooldown_remaining=0.0, spawn_interval=12.0)]

        scene._update_pirate_bases(1.0)

        self.assertEqual(scene.enemy_ships, tuple())
        self.assertEqual(scene.pirate_bases[0].spawn_cooldown_remaining, 0.0)

    def test_defeated_base_raider_is_removed_and_does_not_respawn_after_cooldown(self) -> None:
        scene = self._configure_linear_lane_scene()
        base = PirateBase(star_index=3, spawn_cooldown_remaining=0.0, spawn_interval=12.0)
        scene._pirate_bases = [base]

        raider = EnemyShip("Base-Raider-1", current_star_index=3, home_star_index=3, spawned_from_base=True)
        scene._enemy_ships = [raider]
        scene._reset_enemy_ship_after_defeat(raider)
        self.assertEqual(scene.enemy_ships, tuple())
        self.assertEqual(base.spawn_cooldown_remaining, 12.0)

        scene._update_pirate_bases(11.0)
        self.assertEqual(scene.enemy_ships, tuple())

        scene._update_pirate_bases(1.0)
        self.assertEqual(scene.enemy_ships, tuple())

    def test_attacking_pirate_base_does_not_spawn_extra_defender(self) -> None:
        scene = self._configure_linear_lane_scene()
        flagship = scene.ships[0]
        flagship.current_star_index = 3
        scene._pirate_bases = [PirateBase(star_index=3, hull=35.0, max_hull=35.0)]

        scene._update_combat(0.1)

        self.assertEqual(scene.pirate_bases[0].hull, 25.0)
        self.assertEqual(scene.enemy_ships, tuple())

    def test_pirate_base_attacks_miner_in_range_and_spawns_laser(self) -> None:
        scene = self._configure_linear_lane_scene()
        flagship = scene.ships[0]
        miner = scene.ships[1]
        flagship.current_star_index = 3
        miner.current_star_index = 3
        flagship.attack_damage = 0.0
        miner.attack_damage = 0.0
        scene._pirate_bases = [PirateBase(star_index=3, attack_damage=17.0, attack_range=35.0)]

        scene._update_combat(0.1)

        self.assertEqual(flagship.hull, flagship.max_hull)
        self.assertEqual(miner.hull, miner.max_hull - 17.0)
        self.assertEqual(len(scene._laser_effects), 1)

    def test_pirate_base_does_not_attack_ships_outside_range(self) -> None:
        scene = self._configure_linear_lane_scene()
        flagship = scene.ships[0]
        miner = scene.ships[1]
        flagship.current_star_index = 3
        miner.current_star_index = 3
        flagship.local_position = (48.0, 0.0)
        miner.local_position = (52.0, 0.0)
        flagship.local_target_id = None
        miner.local_target_id = None
        flagship.attack_damage = 0.0
        miner.attack_damage = 0.0
        scene._pirate_bases = [PirateBase(star_index=3, attack_damage=17.0, attack_range=20.0)]

        scene._update_combat(0.1)

        self.assertEqual(flagship.hull, flagship.max_hull)
        self.assertEqual(miner.hull, miner.max_hull)
        self.assertEqual(len(scene._laser_effects), 0)

    def test_pirate_base_blocks_claim_until_destroyed(self) -> None:
        scene = self._configure_linear_lane_scene()
        target = scene.stars[1]
        flagship = scene.ships[0]
        flagship.current_star_index = 1
        scene._selected_star = target
        scene._credits = scene._claim_cost(target)
        scene._pirate_bases = [PirateBase(star_index=1, hull=10.0, max_hull=10.0, reward_credits=45)]

        self.assertFalse(scene.can_claim_star(target))

        scene._update_combat(0.1)

        self.assertEqual(scene.pirate_bases, tuple())
        self.assertEqual(scene.credits, scene._claim_cost(target) + 45)
        self.assertTrue(scene.can_claim_star(target))

    def test_owned_lane_pairs_only_include_connections_between_owned_stars(self) -> None:
        scene = self._configure_linear_lane_scene()

        self.assertEqual(scene._owned_lane_pairs(), set())

        scene.stars[1].owner = "Player"
        self.assertEqual(scene._owned_lane_pairs(), {(0, 1)})

        scene.stars[2].owner = "Player"
        self.assertEqual(scene._owned_lane_pairs(), {(0, 1), (1, 2)})

    def test_owned_sector_uses_green_territory_color(self) -> None:
        scene = self._configure_linear_lane_scene()

        neutral_color = scene._sector_zone_color(1)
        scene.stars[1].owner = "Player"

        self.assertEqual(scene._sector_zone_color(1), scene._PLAYER_TERRITORY_COLOR)
        self.assertNotEqual(scene._sector_zone_color(1), neutral_color)

    def test_preview_route_prefers_hovered_sector_over_selected_sector(self) -> None:
        scene = self._configure_linear_lane_scene()
        scene._selected_star = scene.stars[1]
        scene._hovered_star_index = 3

        self.assertEqual(scene._preview_route_indices(), (0, 1, 2, 3))

    def test_active_route_indices_track_remaining_travel_path(self) -> None:
        scene = self._configure_linear_lane_scene()

        self.assertTrue(scene.issue_travel_order(scene.stars[3]))
        self.assertEqual(scene._active_route_indices(), (0, 1, 2, 3))

        scene.update(0.5)
        self.assertEqual(scene._active_route_indices(), (1, 2, 3))

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

    def test_generated_map_uses_multiple_regions_with_cross_region_links(self) -> None:
        self.assertEqual(len(self.scene._star_regions), len(self.scene.stars))
        region_count = len(set(self.scene._star_regions))

        self.assertGreaterEqual(region_count, 3)
        self.assertEqual(self.scene._star_regions[0], 0)
        self.assertGreater(len(self.scene._bridge_lane_pairs()), 0)

    def test_generated_map_places_systems_on_square_sector_centers(self) -> None:
        self.assertGreater(self.scene._sector_size, 0.0)
        self.assertEqual(self.scene._sector_columns * self.scene._sector_rows, len(self.scene.stars))

        origin_x, origin_y = self.scene._sector_grid_origin
        for star_index, star in enumerate(self.scene.stars):
            column = star_index % self.scene._sector_columns
            row = star_index // self.scene._sector_columns
            expected_x = origin_x + (column + 0.5) * self.scene._sector_size
            expected_y = origin_y + (row + 0.5) * self.scene._sector_size

            self.assertAlmostEqual(star.x, expected_x)
            self.assertAlmostEqual(star.y, expected_y)

    def test_default_star_count_fills_the_sector_grid_without_empty_cells(self) -> None:
        scene = StarMapScene(4000, 2400, 1280, 720, star_count=30, enemy_count=0)

        self.assertEqual(scene._sector_columns * scene._sector_rows, len(scene.stars))

    def test_generated_map_routes_across_diagonal_sector_shortcuts(self) -> None:
        scene = StarMapScene(2400, 2400, 1280, 720, star_count=9, enemy_count=0)

        self.assertEqual(scene._find_path_indices(0, 8), (0, 4, 8))

    def test_generated_map_contains_multi_hop_frontier(self) -> None:
        hop_counts = [len(self.scene._find_path_indices(0, index)) - 1 for index in range(1, len(self.scene.stars))]

        self.assertGreaterEqual(max(hop_counts), 3)

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
        current_object = self.scene._ship_sector_object(self.scene.selected_ship)
        self.assertIsNotNone(current_object)
        self.assertEqual(self.scene.ship_world_position, self.scene._sector_object_world_position(current_object))

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

    def test_selected_asteroid_starts_local_move_before_mining(self) -> None:
        scene = self._configure_linear_lane_scene()
        miner = self._select_miner(scene)
        star = scene.ship_star
        asteroid = scene.asteroid_fields[0]
        star.resource_stock = 40.0
        star.production_rate = 0.0
        miner.mining_rate = 10.0
        scene._selected_star = star
        scene._selected_object_id = asteroid.id

        self.assertTrue(scene.toggle_mining(star))
        self.assertEqual(miner.mining_asteroid_id, asteroid.id)
        self.assertEqual(miner.local_target_id, asteroid.id)

        scene.update(0.01)
        self.assertEqual(miner.cargo_amount, 0.0)

        scene.update(1.0)
        self.assertGreater(miner.cargo_amount, 0.0)
        self.assertEqual(scene._ship_sector_object(miner), asteroid)

    def test_issue_travel_order_can_target_local_sector_object_in_current_system(self) -> None:
        scene = self._configure_linear_lane_scene()
        asteroid = scene.asteroid_fields[0]
        scene._selected_star = scene.stars[0]
        scene._selected_object_id = asteroid.id

        self.assertTrue(scene.issue_travel_order(scene.stars[0]))
        self.assertEqual(scene.selected_ship.local_target_id, asteroid.id)

        scene.update(1.0)
        self.assertEqual(scene._ship_sector_object(scene.selected_ship), asteroid)

    def test_issue_travel_order_can_target_remote_asteroid_directly(self) -> None:
        scene = self._configure_linear_lane_scene()
        asteroid = next(field for field in scene.asteroid_fields if field.star_index == 2)

        self.assertTrue(scene.issue_travel_order(asteroid))
        self.assertIs(scene.selected_star, scene.stars[2])
        self.assertIs(scene.selected_sector_object, asteroid)
        self.assertEqual(scene.selected_ship.local_target_id, asteroid.id)

        scene.update(0.5)
        scene.update(0.5)
        self.assertIs(scene.ship_star, scene.stars[2])
        self.assertEqual(scene.selected_ship.local_target_id, asteroid.id)

        scene.update(1.0)
        self.assertEqual(scene._ship_sector_object(scene.selected_ship), asteroid)

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

    def test_enemy_chases_player_ship_within_detection_range(self) -> None:
        scene = self._configure_linear_lane_scene()
        enemy = EnemyShip("Pirate-1", current_star_index=2, home_star_index=2, detection_range=2)
        scene._enemy_ships = [enemy]

        scene._update_enemy_orders()

        self.assertEqual(enemy.destination_star_index, 1)
        self.assertEqual(enemy.route_star_indices, [0])

    def test_defense_station_attacks_enemy_within_one_hop(self) -> None:
        scene = self._configure_linear_lane_scene()
        defended_star = scene.stars[1]
        defended_star.owner = "Player"
        defended_star.structure = STRUCTURE_DEFENSE_STATION
        enemy = EnemyShip(
            "Pirate-1",
            current_star_index=2,
            home_star_index=2,
            hull=40.0,
            max_hull=40.0,
        )
        scene._enemy_ships = [enemy]

        scene._update_structures(1.0)

        self.assertEqual(enemy.hull, 24.0)

    def test_level_three_defense_station_attacks_enemy_within_two_hops(self) -> None:
        scene = self._configure_linear_lane_scene()
        defended_star = scene.stars[1]
        defended_star.owner = "Player"
        defended_star.structure = STRUCTURE_DEFENSE_STATION
        defended_star.structure_level = 3
        enemy = EnemyShip(
            "Pirate-1",
            current_star_index=3,
            home_star_index=3,
            hull=40.0,
            max_hull=40.0,
        )
        scene._enemy_ships = [enemy]

        scene._update_structures(1.0)

        self.assertEqual(enemy.hull, 8.0)

    def test_defense_station_visual_range_scales_with_level(self) -> None:
        scene = self._configure_linear_lane_scene()
        defended_star = scene.stars[1]
        defended_star.owner = "Player"
        defended_star.structure = STRUCTURE_DEFENSE_STATION
        defended_star.structure_level = 1

        level_one_range = scene._defense_station_visual_range(1, defended_star)

        defended_star.structure_level = 3
        level_three_range = scene._defense_station_visual_range(1, defended_star)

        self.assertEqual(level_one_range, 128.0)
        self.assertEqual(level_three_range, 228.0)
        self.assertGreater(level_three_range, level_one_range)

    def test_defense_station_no_longer_blocks_enemy_entry(self) -> None:
        scene = self._configure_linear_lane_scene()
        defended_star = scene.stars[1]
        defended_star.owner = "Player"
        defended_star.structure = STRUCTURE_DEFENSE_STATION
        miner = scene.ships[1]
        miner.current_star_index = 1
        enemy = EnemyShip(
            "Pirate-1",
            current_star_index=2,
            home_star_index=2,
            detection_range=2,
            patrol_star_indices=(2,),
        )
        scene._enemy_ships = [enemy]

        scene._update_enemy_orders()

        self.assertTrue(enemy.is_traveling)
        self.assertEqual(enemy.destination_star_index, 1)

    def test_enemy_ignores_player_ship_outside_detection_range(self) -> None:
        scene = self._configure_linear_lane_scene()
        enemy = EnemyShip(
            "Pirate-1",
            current_star_index=3,
            home_star_index=3,
            detection_range=2,
            patrol_star_indices=(3,),
        )
        scene._enemy_ships = [enemy]

        scene._update_enemy_orders()

        self.assertFalse(enemy.is_traveling)
        self.assertIsNone(enemy.destination_star_index)

    def test_enemy_targets_miner_first_in_same_system(self) -> None:
        scene = self._configure_linear_lane_scene()
        flagship = scene.ships[0]
        miner = scene.ships[1]
        flagship.current_star_index = 1
        miner.current_star_index = 1
        enemy = EnemyShip("Pirate-1", current_star_index=1, home_star_index=1, attack_damage=15.0)
        scene._enemy_ships = [enemy]

        scene._update_combat(0.1)

        self.assertEqual(flagship.hull, flagship.max_hull)
        self.assertEqual(miner.hull, miner.max_hull - 15.0)

    def test_enemy_does_not_hit_ships_outside_attack_range_within_same_system(self) -> None:
        scene = self._configure_linear_lane_scene()
        flagship = scene.ships[0]
        miner = scene.ships[1]
        flagship.current_star_index = 1
        miner.current_star_index = 1
        flagship.local_position = (48.0, 0.0)
        miner.local_position = (52.0, 0.0)
        flagship.local_target_id = None
        miner.local_target_id = None
        flagship.attack_damage = 0.0
        miner.attack_damage = 0.0
        enemy = EnemyShip(
            "Pirate-1",
            current_star_index=1,
            home_star_index=1,
            attack_damage=15.0,
            attack_range=20.0,
        )
        scene._enemy_ships = [enemy]

        scene._update_combat(0.1)

        self.assertEqual(flagship.hull, flagship.max_hull)
        self.assertEqual(miner.hull, miner.max_hull)
        self.assertEqual(len(scene._laser_effects), 0)

    def test_player_ship_attacks_enemy_within_range_and_spawns_laser(self) -> None:
        scene = self._configure_linear_lane_scene()
        flagship = scene.ships[0]
        flagship.current_star_index = 1
        scene.ships[1].current_star_index = 0
        enemy = EnemyShip(
            "Pirate-1",
            current_star_index=1,
            home_star_index=1,
            hull=40.0,
            max_hull=40.0,
            attack_damage=0.0,
            attack_range=0.0,
        )
        scene._enemy_ships = [enemy]

        scene._update_combat(0.1)

        self.assertEqual(enemy.hull, 30.0)
        self.assertEqual(len(scene._laser_effects), 1)

    def test_laser_effects_expire_after_duration(self) -> None:
        scene = self._configure_linear_lane_scene()
        flagship = scene.ships[0]
        flagship.current_star_index = 1
        scene.ships[1].current_star_index = 0
        enemy = EnemyShip(
            "Pirate-1",
            current_star_index=1,
            home_star_index=1,
            attack_damage=0.0,
            attack_range=0.0,
        )
        scene._enemy_ships = [enemy]

        scene._update_combat(0.1)
        self.assertEqual(len(scene._laser_effects), 1)

        scene._update_laser_effects(scene._LASER_EFFECT_DURATION)

        self.assertEqual(scene._laser_effects, [])

    def test_defeated_player_ship_resets_home_and_loses_cargo(self) -> None:
        scene = self._configure_linear_lane_scene()
        miner = scene.ships[1]
        scene._selected_ship_index = 1
        miner.current_star_index = 2
        miner.mining_star_index = 2
        miner.cargo_resource_type = "Metal"
        miner.cargo_amount = 18.0
        enemy = EnemyShip("Pirate-1", current_star_index=2, home_star_index=2, attack_damage=200.0)
        scene._enemy_ships = [enemy]

        scene._update_combat(0.1)

        self.assertEqual(miner.current_star_index, 0)
        self.assertIsNone(miner.destination_star_index)
        self.assertIsNone(miner.mining_star_index)
        self.assertIsNone(miner.cargo_resource_type)
        self.assertEqual(miner.cargo_amount, 0.0)
        self.assertEqual(miner.hull, miner.max_hull)
        self.assertIs(scene.selected_star, scene.stars[0])

    def test_defeated_enemy_ship_resets_to_home_star(self) -> None:
        scene = self._configure_linear_lane_scene()
        flagship = scene.ships[0]
        flagship.current_star_index = 1
        enemy = EnemyShip(
            "Pirate-1",
            current_star_index=1,
            home_star_index=3,
            hull=10.0,
            max_hull=90.0,
            attack_damage=1.0,
        )
        scene._enemy_ships = [enemy]

        scene._update_combat(0.1)

        self.assertEqual(enemy.current_star_index, 3)
        self.assertEqual(enemy.hull, enemy.max_hull)
        self.assertIsNone(enemy.destination_star_index)
        self.assertEqual(enemy.route_star_indices, [])


if __name__ == "__main__":
    unittest.main()
