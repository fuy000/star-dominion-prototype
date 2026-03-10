from collections.abc import Callable
from dataclasses import dataclass, field
from heapq import heappop, heappush
from math import hypot, sin
from random import Random

from game.core.scene import Scene
from game.runtime import require_pygame


STRUCTURE_SHIPYARD = "Shipyard"
STRUCTURE_DEFENSE_STATION = "Defense Station"
STRUCTURE_MINING_STATION = "Mining Station"


@dataclass(slots=True)
class StarSystem:
    name: str
    x: float
    y: float
    radius: int
    phase: float
    richness: int
    color: tuple[int, int, int]
    resource_type: str
    resource_stock: float
    resource_capacity: float
    production_rate: float
    owner: str = "Neutral"
    structure: str | None = None


@dataclass(slots=True)
class PlayerShip:
    name: str
    role: str
    current_star_index: int
    speed: float = 360.0
    color: tuple[int, int, int] = (170, 245, 255)
    can_mine: bool = False
    origin_star_index: int | None = None
    destination_star_index: int | None = None
    travel_progress: float = 0.0
    route_star_indices: list[int] = field(default_factory=list)
    mining_star_index: int | None = None
    mining_rate: float = 18.0
    cargo_resource_type: str | None = None
    cargo_amount: float = 0.0
    cargo_capacity: float = 40.0
    hull: float = 100.0
    max_hull: float = 100.0
    attack_damage: float = 10.0
    attack_cooldown: float = 1.0
    attack_cooldown_remaining: float = 0.0

    @property
    def is_traveling(self) -> bool:
        return self.destination_star_index is not None

    @property
    def is_mining(self) -> bool:
        return self.mining_star_index is not None and not self.is_traveling

    @property
    def cargo_space_left(self) -> float:
        return max(0.0, self.cargo_capacity - self.cargo_amount)


@dataclass(slots=True)
class EnemyShip:
    name: str
    current_star_index: int
    home_star_index: int
    role: str = "Raider"
    speed: float = 270.0
    color: tuple[int, int, int] = (255, 126, 126)
    origin_star_index: int | None = None
    destination_star_index: int | None = None
    travel_progress: float = 0.0
    route_star_indices: list[int] = field(default_factory=list)
    hull: float = 90.0
    max_hull: float = 90.0
    attack_damage: float = 12.0
    attack_cooldown: float = 1.2
    attack_cooldown_remaining: float = 0.0
    patrol_star_indices: tuple[int, ...] = field(default_factory=tuple)
    patrol_step: int = 0
    detection_range: int = 2
    spawned_from_base: bool = False

    @property
    def is_traveling(self) -> bool:
        return self.destination_star_index is not None


@dataclass(slots=True)
class DeliveryContract:
    destination_star_index: int
    resource_type: str
    remaining_amount: float
    reward_per_unit: int


@dataclass(slots=True)
class PirateBase:
    star_index: int
    hull: float = 180.0
    max_hull: float = 180.0
    spawn_cooldown_remaining: float = 8.0
    spawn_interval: float = 14.0
    max_active_pirates: int = 2
    reward_credits: int = 70


class StarMapScene(Scene):
    _STRUCTURE_COSTS = {
        STRUCTURE_SHIPYARD: 90,
        STRUCTURE_DEFENSE_STATION: 120,
        STRUCTURE_MINING_STATION: 80,
    }
    _STRUCTURE_MARKER_STYLES = {
        STRUCTURE_SHIPYARD: ("plus", (92, 230, 146)),
        STRUCTURE_DEFENSE_STATION: ("triangle", (235, 96, 96)),
        STRUCTURE_MINING_STATION: ("square", (244, 208, 90)),
    }
    _STARTING_CREDITS = 500.0
    _SHIPYARD_REPAIR_RATE = 12.0
    _DEFENSE_STATION_DAMAGE_PER_SECOND = 16.0
    _DEFENSE_STATION_RANGE_HOPS = 1
    _MINING_STATION_MULTIPLIER = 1.75
    _PIRATE_BASE_FILL = (122, 80, 48)
    _PIRATE_BASE_ACCENT = (220, 132, 76)

    def __init__(
        self,
        world_width: int,
        world_height: int,
        viewport_width: int,
        viewport_height: int,
        star_count: int = 30,
        enemy_count: int = 1,
        pirate_base_count: int | None = None,
    ) -> None:
        rng = Random(7)
        self._world_size = (world_width, world_height)
        self._viewport_size = (viewport_width, viewport_height)
        self._camera_x = world_width / 2
        self._camera_y = world_height / 2
        self._zoom = 1.0
        self._time = 0.0
        self._font = None
        self._selected_star: StarSystem | None = None
        self._movement = {"left": False, "right": False, "up": False, "down": False}
        resource_types = ("Hydrogen", "Crystal", "Metal")
        star_names = [
            "Aster", "Helios", "Kepler", "Orion", "Vela", "Draco", "Nova", "Seris",
            "Cygnus", "Aquila", "Lumen", "Talos", "Persei", "Altair", "Erebus", "Lyra",
            "Janus", "Aquilae", "Icarus", "Nysa", "Theron", "Vesper", "Eos", "Solara",
        ]
        self._stars, self._star_regions = self._generate_stars(rng, star_count, resource_types, star_names)
        home_star_index = 0 if self._stars else -1
        if home_star_index >= 0:
            self._stars[home_star_index].owner = "Player"
        self._lanes = self._generate_lanes()
        if pirate_base_count is None:
            pirate_base_count = 3 if enemy_count > 0 else 0
        self._pirate_bases = self._generate_pirate_bases(home_star_index, pirate_base_count)
        self._ships = [
            PlayerShip(
                name="Flagship",
                role="Command",
                current_star_index=home_star_index,
                speed=360.0,
                color=(170, 245, 255),
                hull=140.0,
                max_hull=140.0,
                attack_damage=18.0,
                attack_cooldown=0.9,
            ),
            PlayerShip(
                name="Miner-1",
                role="Miner",
                current_star_index=home_star_index,
                speed=300.0,
                color=(255, 216, 150),
                can_mine=True,
                mining_rate=14.0,
                hull=72.0,
                max_hull=72.0,
                attack_damage=6.0,
                attack_cooldown=1.4,
            ),
            PlayerShip(
                name="Miner-2",
                role="Miner",
                current_star_index=home_star_index,
                speed=300.0,
                color=(140, 255, 170),
                can_mine=True,
                mining_rate=14.0,
                hull=72.0,
                max_hull=72.0,
                attack_damage=6.0,
                attack_cooldown=1.4,
            ),
        ]
        self._selected_ship_index = 0
        self._empire_resources = {resource: 0.0 for resource in resource_types}
        self._credits = self._STARTING_CREDITS
        self._delivery_contracts = self._generate_delivery_contracts(resource_types, home_star_index)
        self._enemy_ships = self._generate_enemy_ships(enemy_count, home_star_index)
        self._show_help_panel = False
        self._show_ship_details = False

    @property
    def world_size(self) -> tuple[int, int]:
        return self._world_size

    @property
    def viewport_size(self) -> tuple[int, int]:
        return self._viewport_size

    @property
    def camera_position(self) -> tuple[float, float]:
        return (self._camera_x, self._camera_y)

    @property
    def zoom(self) -> float:
        return self._zoom

    @property
    def stars(self) -> tuple[StarSystem, ...]:
        return tuple(self._stars)

    @property
    def selected_star(self) -> StarSystem | None:
        return self._selected_star

    @property
    def lanes(self) -> tuple[tuple[StarSystem, StarSystem], ...]:
        return tuple((self._stars[a], self._stars[b]) for a, b in self._lanes)

    @property
    def ships(self) -> tuple[PlayerShip, ...]:
        return tuple(self._ships)

    @property
    def enemy_ships(self) -> tuple[EnemyShip, ...]:
        return tuple(self._enemy_ships)

    @property
    def pirate_bases(self) -> tuple[PirateBase, ...]:
        return tuple(self._pirate_bases)

    @property
    def selected_ship(self) -> PlayerShip:
        return self._ships[self._selected_ship_index]

    @property
    def miner_ships(self) -> tuple[PlayerShip, ...]:
        return tuple(ship for ship in self._ships if ship.can_mine)

    @property
    def ship_star(self) -> StarSystem | None:
        ship = self.selected_ship
        if ship.current_star_index < 0:
            return None
        return self._stars[ship.current_star_index]

    @property
    def ship_destination(self) -> StarSystem | None:
        destination_index = self.selected_ship.destination_star_index
        if destination_index is None:
            return None
        return self._stars[destination_index]

    @property
    def ship_final_destination(self) -> StarSystem | None:
        route = self.ship_route
        if not route:
            return None
        return route[-1]

    @property
    def ship_is_traveling(self) -> bool:
        return self.selected_ship.is_traveling

    @property
    def ship_is_mining(self) -> bool:
        return self.selected_ship.is_mining

    @property
    def ship_route(self) -> tuple[StarSystem, ...]:
        ship = self.selected_ship
        route = []
        if ship.destination_star_index is not None:
            route.append(self._stars[ship.destination_star_index])
        route.extend(self._stars[index] for index in ship.route_star_indices)
        return tuple(route)

    @property
    def mining_star(self) -> StarSystem | None:
        mining_index = self.selected_ship.mining_star_index
        if mining_index is None:
            return None
        return self._stars[mining_index]

    @property
    def empire_resources(self) -> dict[str, float]:
        return dict(self._empire_resources)

    @property
    def credits(self) -> float:
        return self._credits

    @property
    def passive_income_rate(self) -> float:
        return sum(self._territory_income_rate(star) for star in self.owned_stars)

    @property
    def owned_stars(self) -> tuple[StarSystem, ...]:
        return tuple(star for star in self._stars if star.owner == "Player")

    @property
    def delivery_contracts(self) -> tuple[DeliveryContract, ...]:
        return tuple(self._delivery_contracts)

    @property
    def ship_world_position(self) -> tuple[float, float] | None:
        return self._ship_world_position(self.selected_ship)

    @property
    def show_help_panel(self) -> bool:
        return self._show_help_panel

    @property
    def show_ship_details(self) -> bool:
        return self._show_ship_details

    def handle_event(self, event: object) -> None:
        pygame = require_pygame()
        event_type = getattr(event, "type", None)

        if event_type == pygame.KEYDOWN:
            self._handle_key_change(getattr(event, "key", None), is_pressed=True)
        elif event_type == pygame.KEYUP:
            self._handle_key_change(getattr(event, "key", None), is_pressed=False)
        elif event_type == pygame.MOUSEBUTTONDOWN:
            button = getattr(event, "button", None)
            if button == 1:
                screen_pos = getattr(event, "pos", (0, 0))
                if self._help_button_rect().collidepoint(screen_pos):
                    self._toggle_help_panel()
                    return
                if self._show_help_panel and self._help_panel_rect().collidepoint(screen_pos):
                    return
                if self.select_ship_at_screen_pos(screen_pos) is None:
                    self.select_star_at_screen_pos(screen_pos)
            elif button == 3:
                screen_pos = getattr(event, "pos", (0, 0))
                if self._show_help_panel and self._help_panel_rect().collidepoint(screen_pos):
                    return
                star = self.star_at_screen_pos(screen_pos)
                if star is not None:
                    self._selected_star = star
                    self.issue_travel_order(star)
            elif button == 4:
                self.change_zoom(1, getattr(event, "pos", None))
            elif button == 5:
                self.change_zoom(-1, getattr(event, "pos", None))
        elif event_type == pygame.MOUSEWHEEL:
            self.change_zoom(getattr(event, "y", 0), pygame.mouse.get_pos())

    def update(self, dt: float) -> None:
        self._time += dt
        move_x = int(self._movement["right"]) - int(self._movement["left"])
        move_y = int(self._movement["down"]) - int(self._movement["up"])
        if move_x or move_y:
            speed = 900 / self._zoom
            magnitude = max(1.0, hypot(move_x, move_y))
            self.move_camera(speed * move_x * dt / magnitude, speed * move_y * dt / magnitude)
        self._update_pirate_bases(dt)
        self._update_ships(dt)
        self._update_combat(dt)
        self._update_mining(dt)
        self._update_deliveries()
        self._update_passive_income(dt)
        self._update_star_resources(dt)

    def render(self, surface: object) -> None:
        pygame = require_pygame()
        self._viewport_size = surface.get_size()
        width, height = self._viewport_size
        if self._font is None:
            self._font = pygame.font.SysFont("arial", 18)

        self._draw_grid(surface)
        self._draw_lanes(surface)

        for star_index, star in enumerate(self._stars):
            screen_x, screen_y = self.world_to_screen((star.x, star.y))
            if not (-40 <= screen_x <= width + 40 and -40 <= screen_y <= height + 40):
                continue

            twinkle = 155 + int(70 * (1 + sin(self._time * 2.0 + star.phase)) / 2)
            halo_radius = max(5, int(star.radius * self._zoom) + 10)
            core_radius = max(3, int(star.radius * self._zoom))
            halo_surface = pygame.Surface((halo_radius * 4, halo_radius * 4), pygame.SRCALPHA)
            pygame.draw.circle(
                halo_surface,
                (*star.color, 40),
                (halo_surface.get_width() // 2, halo_surface.get_height() // 2),
                halo_radius,
            )
            surface.blit(
                halo_surface,
                (screen_x - halo_surface.get_width() // 2, screen_y - halo_surface.get_height() // 2),
            )
            pygame.draw.circle(
                surface,
                (twinkle, min(255, twinkle + 10), 255),
                (int(screen_x), int(screen_y)),
                core_radius,
            )

            if star.owner == "Player":
                pygame.draw.circle(surface, (96, 214, 160), (int(screen_x), int(screen_y)), halo_radius + 3, 2)

            if self._selected_star is star:
                pygame.draw.circle(surface, (120, 180, 255), (int(screen_x), int(screen_y)), halo_radius + 6, 2)

            pirate_base = self._pirate_base_at_star(star_index)
            if pirate_base is not None:
                self._draw_pirate_base_marker(surface, pirate_base, screen_x, screen_y, halo_radius)

            if star.structure is not None:
                self._draw_structure_marker(surface, star.structure, screen_x, screen_y, halo_radius)

            if self._zoom >= 0.65:
                label = self._font.render(star.name, True, (190, 205, 255))
                surface.blit(label, (screen_x + 12, screen_y - 10))

        self._draw_ships(surface)
        self._draw_hud(surface)

    def move_camera(self, dx: float, dy: float) -> None:
        self._camera_x += dx
        self._camera_y += dy
        self._clamp_camera()

    def change_zoom(self, step: int, anchor_screen_pos: tuple[int, int] | None = None) -> None:
        if step == 0:
            return

        old_zoom = self._zoom
        self._zoom = min(2.5, max(0.45, self._zoom * (1.18 ** step)))
        if anchor_screen_pos is None or self._zoom == old_zoom:
            self._clamp_camera()
            return

        world_x, world_y = self.screen_to_world(anchor_screen_pos, zoom=old_zoom)
        width, height = self._viewport_size
        self._camera_x = world_x - (anchor_screen_pos[0] - width / 2) / self._zoom
        self._camera_y = world_y - (anchor_screen_pos[1] - height / 2) / self._zoom
        self._clamp_camera()

    def world_to_screen(self, point: tuple[float, float]) -> tuple[float, float]:
        width, height = self._viewport_size
        return (
            (point[0] - self._camera_x) * self._zoom + width / 2,
            (point[1] - self._camera_y) * self._zoom + height / 2,
        )

    def screen_to_world(self, point: tuple[int, int], zoom: float | None = None) -> tuple[float, float]:
        width, height = self._viewport_size
        active_zoom = zoom or self._zoom
        return (
            self._camera_x + (point[0] - width / 2) / active_zoom,
            self._camera_y + (point[1] - height / 2) / active_zoom,
        )

    def star_at_screen_pos(self, screen_pos: tuple[int, int]) -> StarSystem | None:
        world_x, world_y = self.screen_to_world(screen_pos)
        for star in sorted(self._stars, key=lambda item: item.radius, reverse=True):
            if hypot(star.x - world_x, star.y - world_y) <= star.radius + (14 / self._zoom):
                return star
        return None

    def select_star_at_screen_pos(self, screen_pos: tuple[int, int]) -> StarSystem | None:
        selected = self.star_at_screen_pos(screen_pos)
        self._selected_star = selected
        self._show_ship_details = False
        return selected

    def ship_at_screen_pos(self, screen_pos: tuple[int, int]) -> PlayerShip | None:
        for index in range(len(self._ships) - 1, -1, -1):
            ship = self._ships[index]
            ship_pos = self._ship_world_position(ship)
            if ship_pos is None:
                continue

            screen_x, screen_y = self.world_to_screen(ship_pos)
            offset_x, offset_y = self._ship_draw_offset(ship, index, self._ships)
            hit_radius = self._ship_click_radius(ship is self.selected_ship)
            if hypot(screen_x + offset_x - screen_pos[0], screen_y + offset_y - screen_pos[1]) <= hit_radius:
                return ship
        return None

    def select_ship_at_screen_pos(self, screen_pos: tuple[int, int]) -> PlayerShip | None:
        ship = self.ship_at_screen_pos(screen_pos)
        if ship is None:
            return None

        self._selected_ship_index = self._ships.index(ship)
        self._show_ship_details = True
        if ship.current_star_index >= 0 and not ship.is_traveling:
            self._selected_star = self._stars[ship.current_star_index]
        return ship

    def cycle_selected_ship(self) -> PlayerShip:
        self._selected_ship_index = (self._selected_ship_index + 1) % len(self._ships)
        self._show_ship_details = True
        return self.selected_ship

    def connected_stars_for(self, star: StarSystem) -> tuple[StarSystem, ...]:
        star_index = self._index_of_star(star)
        neighbors = []
        for a, b in self._lanes:
            if a == star_index:
                neighbors.append(self._stars[b])
            elif b == star_index:
                neighbors.append(self._stars[a])
        return tuple(neighbors)

    def path_to_star(self, target_star: StarSystem | None = None) -> tuple[StarSystem, ...]:
        ship = self.selected_ship
        if target_star is None or self.ship_star is None:
            return tuple()

        target_index = self._index_of_star(target_star)
        path_indices = self._find_path_indices(ship.current_star_index, target_index)
        return tuple(self._stars[index] for index in path_indices)

    def can_travel_to_star(self, target_star: StarSystem | None = None) -> bool:
        ship = self.selected_ship
        if target_star is None or self.ship_star is None or ship.is_traveling:
            return False

        path = self.path_to_star(target_star)
        return len(path) > 1

    def issue_travel_order(self, target_star: StarSystem | None = None) -> bool:
        ship = self.selected_ship
        target = target_star or self._selected_star
        if not self.can_travel_to_star(target):
            return False

        path_indices = list(self._find_path_indices(
            ship.current_star_index,
            self._index_of_star(target),
        ))
        ship.mining_star_index = None
        self._start_ship_route(ship, path_indices)
        self._selected_star = target
        return True

    def toggle_mining(self, target_star: StarSystem | None = None) -> bool:
        ship = self.selected_ship
        target = target_star or self._selected_star or self.ship_star
        if target is None or self.ship_star is None or ship.is_traveling or not ship.can_mine:
            return False

        target_index = self._index_of_star(target)
        if target_index != ship.current_star_index:
            return False

        if target.resource_stock <= 0:
            return False

        if ship.cargo_space_left <= 0:
            return False

        if ship.cargo_resource_type not in (None, target.resource_type):
            return False

        if ship.mining_star_index == target_index:
            ship.mining_star_index = None
            return False

        ship.mining_star_index = target_index
        self._selected_star = target
        return True

    def can_claim_star(self, target_star: StarSystem | None = None) -> bool:
        ship = self.selected_ship
        target = target_star or self._selected_star or self.ship_star
        if target is None or self.ship_star is None or ship.is_traveling:
            return False

        if ship.role != "Command":
            return False

        target_index = self._index_of_star(target)
        if ship.current_star_index != target_index or target.owner != "Neutral":
            return False

        if self._pirate_base_at_star(target_index) is not None:
            return False

        if not self._is_adjacent_to_owned_territory(target_index):
            return False

        return self._credits >= self._claim_cost(target)

    def claim_star(self, target_star: StarSystem | None = None) -> bool:
        target = target_star or self._selected_star or self.ship_star
        if target is None or not self.can_claim_star(target):
            return False

        self._credits -= self._claim_cost(target)
        target.owner = "Player"
        self._selected_star = target
        return True

    def can_build_structure(self, structure_name: str, target_star: StarSystem | None = None) -> bool:
        target = target_star or self._selected_star or self.ship_star
        if target is None or structure_name not in self._STRUCTURE_COSTS:
            return False

        if target.owner != "Player" or target.structure is not None:
            return False

        return self._credits >= self._structure_cost(structure_name)

    def build_structure(self, structure_name: str, target_star: StarSystem | None = None) -> bool:
        target = target_star or self._selected_star or self.ship_star
        if target is None or not self.can_build_structure(structure_name, target):
            return False

        self._credits -= self._structure_cost(structure_name)
        target.structure = structure_name
        self._selected_star = target
        return True

    def _handle_key_change(self, key: int | None, is_pressed: bool) -> None:
        pygame = require_pygame()
        bindings = {
            pygame.K_a: "left",
            pygame.K_LEFT: "left",
            pygame.K_d: "right",
            pygame.K_RIGHT: "right",
            pygame.K_w: "up",
            pygame.K_UP: "up",
            pygame.K_s: "down",
            pygame.K_DOWN: "down",
        }
        direction = bindings.get(key)
        if direction is not None:
            self._movement[direction] = is_pressed
            return

        if is_pressed and key == pygame.K_h:
            self._toggle_help_panel()
            return

        if is_pressed and key == pygame.K_ESCAPE and self._show_help_panel:
            self._show_help_panel = False
            return

        if is_pressed and key == pygame.K_TAB:
            self.cycle_selected_ship()
            return

        if is_pressed and key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_t):
            self.issue_travel_order()
            return

        if is_pressed and key == pygame.K_m:
            self.toggle_mining()
            return

        if is_pressed and key == pygame.K_c:
            self.claim_star()
            return

        if is_pressed and key == pygame.K_1:
            self.build_structure(STRUCTURE_SHIPYARD)
            return

        if is_pressed and key == pygame.K_2:
            self.build_structure(STRUCTURE_DEFENSE_STATION)
            return

        if is_pressed and key == pygame.K_3:
            self.build_structure(STRUCTURE_MINING_STATION)
            return

        if is_pressed and key in (pygame.K_EQUALS, pygame.K_PLUS, pygame.K_KP_PLUS):
            self.change_zoom(1)
        elif is_pressed and key in (pygame.K_MINUS, pygame.K_KP_MINUS):
            self.change_zoom(-1)

    def _toggle_help_panel(self) -> bool:
        self._show_help_panel = not self._show_help_panel
        return self._show_help_panel

    def _help_button_rect(self) -> object:
        pygame = require_pygame()
        return pygame.Rect(16, 16, 104, 32)

    def _help_panel_rect(self) -> object:
        pygame = require_pygame()
        panel_width = min(360, max(300, self._viewport_size[0] // 2 - 40))
        panel_x = min(132, max(16, self._viewport_size[0] - panel_width - 16))
        return pygame.Rect(panel_x, 16, panel_width, 208)

    def _clamp_camera(self) -> None:
        world_width, world_height = self._world_size
        half_width = self._viewport_size[0] / (2 * self._zoom)
        half_height = self._viewport_size[1] / (2 * self._zoom)

        if world_width <= half_width * 2:
            self._camera_x = world_width / 2
        else:
            self._camera_x = min(world_width - half_width, max(half_width, self._camera_x))

        if world_height <= half_height * 2:
            self._camera_y = world_height / 2
        else:
            self._camera_y = min(world_height - half_height, max(half_height, self._camera_y))

    def _draw_grid(self, surface: object) -> None:
        pygame = require_pygame()
        width, height = self._viewport_size
        left, top = self.screen_to_world((0, 0))
        right, bottom = self.screen_to_world((width, height))
        spacing = 240
        color = (16, 24, 40)

        start_x = int(left // spacing) * spacing
        for x in range(start_x, int(right) + spacing, spacing):
            screen_x, _ = self.world_to_screen((x, 0))
            pygame.draw.line(surface, color, (int(screen_x), 0), (int(screen_x), height))

        start_y = int(top // spacing) * spacing
        for y in range(start_y, int(bottom) + spacing, spacing):
            _, screen_y = self.world_to_screen((0, y))
            pygame.draw.line(surface, color, (0, int(screen_y)), (width, int(screen_y)))

    def _draw_lanes(self, surface: object) -> None:
        pygame = require_pygame()
        preview_pairs = self._selected_route_pairs()
        route_pairs = self._ship_route_pairs()
        active_lane = self._active_ship_lane()
        owned_pairs = self._owned_lane_pairs()

        for a, b in self._lanes:
            start = self._stars[a]
            end = self._stars[b]
            start_pos = self.world_to_screen((start.x, start.y))
            end_pos = self.world_to_screen((end.x, end.y))
            lane_key = tuple(sorted((a, b)))
            color = (38, 56, 92)
            width = 2

            if lane_key == active_lane:
                color = (90, 170, 255)
                width = 4
            elif lane_key in route_pairs:
                color = (88, 148, 232)
                width = 3
            elif lane_key in preview_pairs:
                color = (72, 126, 210)
                width = 3
            elif lane_key in owned_pairs:
                color = (82, 186, 126)
                width = 3

            pygame.draw.line(
                surface,
                color,
                (int(start_pos[0]), int(start_pos[1])),
                (int(end_pos[0]), int(end_pos[1])),
                width,
            )

    def _draw_ships(self, surface: object) -> None:
        pygame = require_pygame()
        active_ship = self.selected_ship
        for index, ship in enumerate(self._ships):
            ship_pos = self._ship_world_position(ship)
            if ship_pos is None:
                continue

            screen_x, screen_y = self.world_to_screen(ship_pos)
            offset_x, offset_y = self._ship_draw_offset(ship, index, self._ships)
            screen_x += offset_x
            screen_y += offset_y
            radius = self._ship_render_radius(ship is active_ship)
            halo_radius = radius + (8 if ship is active_ship else 5)
            halo_alpha = 65 if ship is active_ship else 35
            ship_color = (140, 255, 170) if ship.is_mining else ship.color
            halo_surface = pygame.Surface((halo_radius * 4, halo_radius * 4), pygame.SRCALPHA)
            pygame.draw.circle(
                halo_surface,
                (*ship.color, halo_alpha),
                (halo_surface.get_width() // 2, halo_surface.get_height() // 2),
                halo_radius,
            )
            surface.blit(
                halo_surface,
                (
                    screen_x - halo_surface.get_width() // 2,
                    screen_y - halo_surface.get_height() // 2,
                ),
            )
            icon_points = self._ship_icon_points(ship.role, (screen_x, screen_y), radius)
            pygame.draw.polygon(surface, ship_color, icon_points)
            pygame.draw.polygon(surface, (24, 30, 44), icon_points, 1)
            health_bar_rect = self._draw_ship_health_bar(surface, ship, screen_x, screen_y, radius)
            if ship is active_ship:
                pygame.draw.circle(
                    surface,
                    (245, 248, 255),
                    (int(screen_x), int(screen_y)),
                    radius + 3,
                    1,
                )

            if self._zoom >= 0.55:
                label_text = ship.name if ship is active_ship else f"{ship.name} ({ship.role})"
                label_color = (245, 248, 255) if ship is active_ship else (205, 220, 245)
                label = self._font.render(label_text, True, label_color)
                label_bg = pygame.Surface((label.get_width() + 8, label.get_height() + 4), pygame.SRCALPHA)
                label_bg.fill((8, 12, 22, 170 if ship is active_ship else 140))
                label_x = int(screen_x - label_bg.get_width() / 2)
                label_y = int(health_bar_rect[1] - label_bg.get_height() - 4)
                surface.blit(label_bg, (label_x, label_y))
                surface.blit(label, (label_x + 4, label_y + 2))

        for index, ship in enumerate(self._enemy_ships, start=len(self._ships)):
            ship_pos = self._ship_world_position(ship)
            if ship_pos is None:
                continue

            screen_x, screen_y = self.world_to_screen(ship_pos)
            offset_x, offset_y = self._ship_draw_offset(ship, index, self._enemy_ships)
            screen_x += offset_x
            screen_y += offset_y
            radius = max(6, int(8 * self._zoom))
            halo_surface = pygame.Surface((radius * 8, radius * 8), pygame.SRCALPHA)
            pygame.draw.circle(
                halo_surface,
                (*ship.color, 45),
                (halo_surface.get_width() // 2, halo_surface.get_height() // 2),
                radius + 5,
            )
            surface.blit(
                halo_surface,
                (
                    screen_x - halo_surface.get_width() // 2,
                    screen_y - halo_surface.get_height() // 2,
                ),
            )
            icon_points = self._ship_icon_points(ship.role, (screen_x, screen_y), radius)
            pygame.draw.polygon(surface, ship.color, icon_points)
            pygame.draw.polygon(surface, (54, 12, 12), icon_points, 1)
            health_bar_rect = self._draw_ship_health_bar(surface, ship, screen_x, screen_y, radius)

            if self._zoom >= 0.55:
                label = self._font.render(ship.name, True, (255, 228, 228))
                label_bg = pygame.Surface((label.get_width() + 8, label.get_height() + 4), pygame.SRCALPHA)
                label_bg.fill((40, 10, 10, 150))
                label_x = int(screen_x - label_bg.get_width() / 2)
                label_y = int(health_bar_rect[1] - label_bg.get_height() - 4)
                surface.blit(label_bg, (label_x, label_y))
                surface.blit(label, (label_x + 4, label_y + 2))

        destination = self.ship_destination
        ship_pos = self.ship_world_position
        if destination is not None and ship_pos is not None:
            screen_x, screen_y = self.world_to_screen(ship_pos)
            offset_x, offset_y = self._ship_draw_offset(self.selected_ship, self._selected_ship_index, self._ships)
            destination_pos = self.world_to_screen((destination.x, destination.y))
            pygame.draw.line(
                surface,
                (150, 230, 255),
                (int(screen_x + offset_x), int(screen_y + offset_y)),
                (int(destination_pos[0]), int(destination_pos[1])),
                1,
            )

    def _draw_hud(self, surface: object) -> None:
        pygame = require_pygame()
        active_ship = self.selected_ship
        help_button_rect = self._help_button_rect()

        button_surface = pygame.Surface(help_button_rect.size, pygame.SRCALPHA)
        button_surface.fill((18, 30, 54, 235) if self._show_help_panel else (12, 18, 32, 220))
        pygame.draw.rect(
            button_surface,
            (110, 180, 245, 255) if self._show_help_panel else (70, 110, 180, 255),
            button_surface.get_rect(),
            1,
            border_radius=8,
        )
        surface.blit(button_surface, help_button_rect.topleft)

        button_text = self._font.render("Hide Help" if self._show_help_panel else "? Help", True, (230, 238, 255))
        surface.blit(
            button_text,
            (
                help_button_rect.x + (help_button_rect.width - button_text.get_width()) / 2,
                help_button_rect.y + (help_button_rect.height - button_text.get_height()) / 2,
            ),
        )

        selected_star_index = self._selected_star_index()
        selected_contract = self._contract_for_star_index(selected_star_index)
        hostiles_at_selected = self._enemy_ships_at_star(selected_star_index)
        selected_base = self._pirate_base_at_star(selected_star_index)

        if self._selected_star is None:
            selected_name = "No star selected"
            selected_resource = "Click a system to inspect resources, routes, and claim options"
            route_text = None
            contract_text = None
            claim_text = None
            structure_text = None
            build_text = None
            build_cost_text = None
        else:
            selected_path = self.path_to_star(self._selected_star)
            if self.ship_star is self._selected_star and not self.ship_is_traveling:
                route_text = "Current location"
            elif len(selected_path) > 1:
                route_text = (
                    f"Route: {len(selected_path) - 1} hops | "
                    f"ETA {self._path_distance(self._indices_for_stars(selected_path)) / active_ship.speed:.1f}s"
                )
            else:
                route_text = "No route available"

            selected_name = (
                f"{self._selected_star.name} | Owner {self._selected_star.owner} | "
                f"Richness {self._selected_star.richness}/5"
            )
            current_production_rate = self._star_resource_production_rate(self._selected_star)
            selected_resource = (
                f"{self._selected_star.resource_type}: "
                f"{self._selected_star.resource_stock:.0f}/{self._selected_star.resource_capacity:.0f} "
                f"(+{current_production_rate:.1f}/s)"
            )
            contract_text = None
            if selected_contract is not None:
                contract_text = (
                    f"Contract: {selected_contract.resource_type} "
                    f"{selected_contract.remaining_amount:.0f} @ {selected_contract.reward_per_unit}c"
                )

            claim_cost = self._claim_cost(self._selected_star)
            if self._selected_star.owner == "Player":
                income_rate = self._territory_income_rate(self._selected_star)
                if income_rate > 0:
                    claim_text = f"Territory: already under your control | +{income_rate:.1f} c/s"
                else:
                    claim_text = "Territory: already under your control"
            elif selected_base is not None:
                claim_text = "Territory: destroy the pirate base before claiming this system"
            elif active_ship.role != "Command":
                claim_text = "Territory: flagship required to claim systems"
            elif self.ship_is_traveling or self.ship_star is not self._selected_star:
                claim_text = f"Territory: move flagship here to claim for {claim_cost} c"
            elif selected_star_index is not None and not self._is_adjacent_to_owned_territory(selected_star_index):
                claim_text = "Territory: target must border owned territory"
            elif self._credits < claim_cost:
                claim_text = f"Territory: need {claim_cost} c to claim ({self._credits:.0f} available)"
            else:
                claim_text = f"Territory: press C to claim for {claim_cost} c"

            if self._selected_star.owner == "Player":
                if self._selected_star.structure is None:
                    structure_text = "Structure: none"
                    build_text = "Build: 1 Shipyard | 2 Defense | 3 Mining"
                    build_cost_text = (
                        f"Costs: {self._structure_cost(STRUCTURE_SHIPYARD)}c / "
                        f"{self._structure_cost(STRUCTURE_DEFENSE_STATION)}c / "
                        f"{self._structure_cost(STRUCTURE_MINING_STATION)}c"
                    )
                else:
                    structure_text = f"Structure: {self._selected_star.structure}"
                    build_text = self._structure_description(self._selected_star.structure)
                    build_cost_text = None
            else:
                structure_text = None
                build_text = None
                build_cost_text = None

        hostile_text = None
        if hostiles_at_selected and selected_base is not None:
            hostile_text = (
                f"Hostiles: {len(hostiles_at_selected)} pirate ship(s) | "
                f"Base hull {selected_base.hull:.0f}/{selected_base.max_hull:.0f}"
            )
        elif hostiles_at_selected:
            hostile_text = (
                f"Hostiles: {len(hostiles_at_selected)} pirate ship(s) in system | "
                f"Hull {hostiles_at_selected[0].hull:.0f}/{hostiles_at_selected[0].max_hull:.0f}"
            )
        elif selected_base is not None:
            hostile_text = (
                f"Pirate base present | Hull {selected_base.hull:.0f}/{selected_base.max_hull:.0f} | "
                f"Bounty {selected_base.reward_credits} c"
            )

        left_lines = [
            "System",
            selected_name,
            selected_resource,
        ]

        if contract_text is not None:
            left_lines.append(contract_text)
        if route_text is not None:
            left_lines.append(route_text)
        if claim_text is not None:
            left_lines.append(claim_text)
        if structure_text is not None:
            left_lines.append(structure_text)
        if build_text is not None:
            left_lines.append(build_text)
        if build_cost_text is not None:
            left_lines.append(build_cost_text)
        if hostile_text is not None:
            left_lines.append(hostile_text)

        left_panel_width = min(500, max(340, surface.get_width() - 420))
        left_panel_height = 18 + len(left_lines) * 22 + 12
        panel = pygame.Surface((left_panel_width, left_panel_height), pygame.SRCALPHA)
        panel.fill((8, 12, 22, 220))
        pygame.draw.rect(panel, (50, 88, 150, 255), panel.get_rect(), 1, border_radius=10)
        surface.blit(panel, (16, 58))

        for index, text in enumerate(left_lines):
            color = (225, 235, 255) if index == 0 else (180, 198, 242)
            label = self._font.render(text, True, color)
            surface.blit(label, (28, 70 + index * 22))

        if self._show_ship_details:
            if (
                self.ship_is_traveling
                and self.ship_destination is not None
                and self.ship_final_destination is not None
                and self.ship_star is not None
            ):
                ship_status = (
                    f"Route: {self.ship_star.name} -> {self.ship_final_destination.name} | "
                    f"{len(self.ship_route)} hops left"
                )
                ship_detail = (
                    f"Current leg: {self.ship_destination.name} | "
                    f"{active_ship.travel_progress:.0%} complete"
                )
            elif self.ship_star is None:
                ship_status = "Status: awaiting deployment"
                ship_detail = "Mining: unavailable"
            else:
                ship_status = f"Status: docked at {self.ship_star.name}"
                if self.ship_is_mining and self.mining_star is not None:
                    ship_detail = (
                        f"Mining: {self.mining_star.resource_type} at {self.mining_star.name} | "
                        f"{active_ship.mining_rate:.1f}/s"
                    )
                elif active_ship.can_mine:
                    ship_detail = "Mining: idle"
                else:
                    ship_detail = "Mining: unavailable for command ships"

            if active_ship.cargo_resource_type is None or active_ship.cargo_amount <= 0:
                cargo_text = f"Cargo: empty (0/{active_ship.cargo_capacity:.0f})"
            else:
                cargo_text = (
                    f"Cargo: {active_ship.cargo_resource_type} "
                    f"{active_ship.cargo_amount:.0f}/{active_ship.cargo_capacity:.0f}"
                )

            ship_lines = [
                "Ship",
                f"{active_ship.name} ({active_ship.role}) | Hull {active_ship.hull:.0f}/{active_ship.max_hull:.0f}",
                ship_status,
                ship_detail,
                cargo_text,
            ]

            ship_panel_width = min(500, max(340, surface.get_width() - 420))
            ship_panel_height = 18 + len(ship_lines) * 22 + 12
            ship_panel_y = 58 + left_panel_height + 12
            ship_panel = pygame.Surface((ship_panel_width, ship_panel_height), pygame.SRCALPHA)
            ship_panel.fill((8, 12, 22, 220))
            pygame.draw.rect(ship_panel, (76, 132, 188, 255), ship_panel.get_rect(), 1, border_radius=10)
            surface.blit(ship_panel, (16, ship_panel_y))

            for index, text in enumerate(ship_lines):
                color = (235, 242, 255) if index == 0 else (192, 214, 244)
                label = self._font.render(text, True, color)
                surface.blit(label, (28, ship_panel_y + 12 + index * 22))

        contract_lines = []
        for contract in self._delivery_contracts[:4]:
            destination = self._stars[contract.destination_star_index]
            contract_lines.append(
                f"{destination.name}: {contract.resource_type} {contract.remaining_amount:.0f} @ {contract.reward_per_unit}c"
            )
        if not contract_lines:
            contract_lines.append("No active delivery contracts")

        right_panel_width = 320
        right_panel_height = 128 + len(contract_lines) * 22
        right_panel = pygame.Surface((right_panel_width, right_panel_height), pygame.SRCALPHA)
        right_panel.fill((8, 12, 22, 220))
        pygame.draw.rect(right_panel, (80, 150, 110, 255), right_panel.get_rect(), 1, border_radius=10)
        panel_x = surface.get_width() - right_panel_width - 16
        surface.blit(right_panel, (panel_x, 16))

        right_lines = [
            f"Credits: {self._credits:.0f} c",
            f"Territory: {len(self.owned_stars)}/{len(self._stars)} systems",
            f"Passive income: +{self.passive_income_rate:.1f} c/s",
            f"Hostiles: {len(self._enemy_ships)} patrols | Bases: {len(self._pirate_bases)}",
            "Active delivery contracts",
        ]
        right_lines.extend(contract_lines)
        for index, text in enumerate(right_lines):
            color = (245, 248, 255) if index == 0 else (180, 225, 195) if index in (1, 2, 3) else (200, 220, 235)
            label = self._font.render(text, True, color)
            surface.blit(label, (panel_x + 14, 28 + index * 22))

        if self._show_help_panel:
            help_panel_rect = self._help_panel_rect()
            help_panel = pygame.Surface(help_panel_rect.size, pygame.SRCALPHA)
            help_panel.fill((8, 12, 22, 235))
            pygame.draw.rect(help_panel, (90, 150, 220, 255), help_panel.get_rect(), 1, border_radius=10)
            surface.blit(help_panel, help_panel_rect.topleft)

            help_lines = [
                "Navigation & Controls",
                "WASD / Arrows: pan camera",
                "Mouse wheel / +/-: zoom",
                "Left click: inspect star or select ship",
                "Right click or T / Enter / Space: travel",
                "Tab: cycle ships | M: mine | C: claim",
                "Owned star: 1 Shipyard | 2 Defense | 3 Mining",
                "H or ? Help: toggle this panel | Esc: close",
            ]
            for index, text in enumerate(help_lines):
                color = (235, 242, 255) if index == 0 else (195, 212, 242)
                label = self._font.render(text, True, color)
                surface.blit(label, (help_panel_rect.x + 14, help_panel_rect.y + 14 + index * 22))

    def _update_star_resources(self, dt: float) -> None:
        for star in self._stars:
            star.resource_stock = min(
                star.resource_capacity,
                star.resource_stock + self._star_resource_production_rate(star) * dt,
            )

    def _update_passive_income(self, dt: float) -> None:
        if dt <= 0:
            return

        self._credits += self.passive_income_rate * dt

    def _update_pirate_bases(self, dt: float) -> None:
        if dt <= 0:
            return

        for base in self._pirate_bases:
            base.spawn_cooldown_remaining = max(0.0, base.spawn_cooldown_remaining - dt)
            if base.spawn_cooldown_remaining > 0:
                continue
            if self._spawn_pirate_from_base(base):
                base.spawn_cooldown_remaining = base.spawn_interval
            else:
                base.spawn_cooldown_remaining = 1.0

    def _update_mining(self, dt: float) -> None:
        for ship in self.miner_ships:
            if ship.mining_star_index is None or ship.is_traveling:
                continue

            if ship.current_star_index != ship.mining_star_index:
                ship.mining_star_index = None
                continue

            mining_star = self._stars[ship.mining_star_index]
            if mining_star.resource_stock <= 0:
                ship.mining_star_index = None
                continue

            if ship.cargo_space_left <= 0:
                ship.mining_star_index = None
                continue

            if ship.cargo_resource_type not in (None, mining_star.resource_type):
                ship.mining_star_index = None
                continue

            extracted = min(ship.mining_rate * dt, mining_star.resource_stock, ship.cargo_space_left)
            if extracted <= 0:
                ship.mining_star_index = None
                continue

            ship.cargo_resource_type = mining_star.resource_type
            ship.cargo_amount = min(ship.cargo_capacity, ship.cargo_amount + extracted)
            mining_star.resource_stock = max(0.0, mining_star.resource_stock - extracted)
            if mining_star.resource_stock <= 0 or ship.cargo_space_left <= 0:
                mining_star.resource_stock = 0.0
                ship.mining_star_index = None

    def _update_structures(self, dt: float) -> None:
        if dt <= 0:
            return

        self._update_shipyard_repairs(dt)
        self._update_defense_station_attacks(dt)

    def _update_shipyard_repairs(self, dt: float) -> None:
        for star_index, star in enumerate(self._stars):
            if star.owner != "Player" or star.structure != STRUCTURE_SHIPYARD:
                continue

            for ship in self._player_ships_at_star(star_index):
                ship.hull = min(ship.max_hull, ship.hull + self._SHIPYARD_REPAIR_RATE * dt)

    def _update_defense_station_attacks(self, dt: float) -> None:
        for star_index, star in enumerate(self._stars):
            if star.owner != "Player" or star.structure != STRUCTURE_DEFENSE_STATION:
                continue

            target = self._defense_station_target(star_index)
            if target is None:
                continue

            target.hull = max(0.0, target.hull - self._DEFENSE_STATION_DAMAGE_PER_SECOND * dt)
            if target.hull <= 0:
                self._reset_enemy_ship_after_defeat(target)

    def _defense_station_target(self, star_index: int) -> EnemyShip | None:
        protected_indices = {star_index}
        if self._DEFENSE_STATION_RANGE_HOPS > 0:
            protected_indices.update(self._neighbor_star_indices(star_index))

        candidates = [
            enemy
            for enemy in self._enemy_ships
            if not enemy.is_traveling and enemy.current_star_index in protected_indices
        ]
        if not candidates:
            return None

        return min(
            candidates,
            key=lambda enemy: (0 if enemy.current_star_index == star_index else 1, enemy.hull, enemy.name),
        )

    def _update_deliveries(self) -> None:
        for ship in self._ships:
            self._deliver_ship_cargo(ship)

    def _enemy_ships_at_star(self, star_index: int | None) -> tuple[EnemyShip, ...]:
        if star_index is None:
            return tuple()
        return tuple(
            ship
            for ship in self._enemy_ships
            if ship.current_star_index == star_index and not ship.is_traveling
        )

    def _player_ships_at_star(self, star_index: int) -> tuple[PlayerShip, ...]:
        return tuple(
            ship
            for ship in self._ships
            if ship.current_star_index == star_index and not ship.is_traveling
        )

    def _pirate_base_at_star(self, star_index: int | None) -> PirateBase | None:
        if star_index is None:
            return None
        for base in self._pirate_bases:
            if base.star_index == star_index:
                return base
        return None

    def _active_pirates_from_base(self, base: PirateBase) -> int:
        return sum(1 for ship in self._enemy_ships if ship.home_star_index == base.star_index and ship.spawned_from_base)

    def _spawn_pirate_from_base(self, base: PirateBase) -> bool:
        if self._active_pirates_from_base(base) >= base.max_active_pirates:
            return False

        patrol = self._pirate_patrol_indices(base.star_index)
        self._enemy_ships.append(
            EnemyShip(
                name=f"Base-Raider-{len(self._enemy_ships) + 1}",
                current_star_index=base.star_index,
                home_star_index=base.star_index,
                color=(214, 128, 110),
                hull=82.0,
                max_hull=82.0,
                attack_damage=14.0,
                attack_cooldown=1.1,
                patrol_star_indices=patrol,
                detection_range=2,
                spawned_from_base=True,
            )
        )
        return True

    def _pirate_patrol_indices(self, star_index: int) -> tuple[int, ...]:
        neighbors = list(self._neighbor_star_indices(star_index))
        neighbors.sort(key=lambda index: self._distance_between_stars(star_index, index), reverse=True)
        return tuple([star_index, *neighbors[:2]])

    def _deliver_ship_cargo(self, ship: PlayerShip) -> None:
        if ship.current_star_index < 0 or ship.cargo_resource_type is None or ship.cargo_amount <= 0:
            if ship.cargo_amount <= 0:
                ship.cargo_amount = 0.0
                ship.cargo_resource_type = None
            return

        contract = self._contract_for_star_index(ship.current_star_index)
        if contract is None or contract.resource_type != ship.cargo_resource_type:
            return

        delivered = min(ship.cargo_amount, contract.remaining_amount)
        if delivered <= 0:
            return

        ship.cargo_amount = max(0.0, ship.cargo_amount - delivered)
        contract.remaining_amount = max(0.0, contract.remaining_amount - delivered)
        self._credits += delivered * contract.reward_per_unit
        self._empire_resources[contract.resource_type] = (
            self._empire_resources.get(contract.resource_type, 0.0) + delivered
        )
        if ship.cargo_amount <= 0:
            ship.cargo_amount = 0.0
            ship.cargo_resource_type = None
        if contract.remaining_amount <= 0:
            self._delivery_contracts.remove(contract)

    def _update_ships(self, dt: float) -> None:
        self._update_enemy_orders()
        for ship in self._ships:
            self._update_ship(ship, dt)

        for ship in self._enemy_ships:
            self._update_ship(ship, dt)

    def _update_enemy_orders(self) -> None:
        for enemy in self._enemy_ships:
            if enemy.current_star_index < 0 or enemy.is_traveling:
                continue

            target_ship = self._enemy_target_ship(enemy)
            if target_ship is not None:
                if target_ship.current_star_index != enemy.current_star_index:
                    path = self._find_enemy_path_indices(enemy, target_ship.current_star_index)
                    if path:
                        self._start_ship_route(enemy, list(path))
                continue

            self._advance_enemy_patrol(enemy)

    def _enemy_target_ship(self, enemy: EnemyShip) -> PlayerShip | None:
        best_choice: tuple[int, int, float, int] | None = None
        best_ship: PlayerShip | None = None
        for index, ship in enumerate(self._ships):
            if ship.current_star_index < 0:
                continue

            path = self._find_enemy_path_indices(enemy, ship.current_star_index)
            if not path:
                continue

            hops = len(path) - 1
            if hops > enemy.detection_range:
                continue

            choice = (hops, 0 if ship.can_mine else 1, -ship.cargo_amount, index)
            if best_choice is None or choice < best_choice:
                best_choice = choice
                best_ship = ship

        return best_ship

    def _advance_enemy_patrol(self, enemy: EnemyShip) -> None:
        patrol = enemy.patrol_star_indices or (enemy.home_star_index,)
        if len(patrol) < 2:
            return

        patrol_step = enemy.patrol_step % len(patrol)
        target_index = patrol[patrol_step]
        if target_index == enemy.current_star_index:
            patrol_step = (patrol_step + 1) % len(patrol)
            enemy.patrol_step = patrol_step
            target_index = patrol[patrol_step]

        path = self._find_enemy_path_indices(enemy, target_index)
        if path:
            self._start_ship_route(enemy, list(path))

    def _update_combat(self, dt: float) -> None:
        if dt <= 0:
            return

        for enemy in self._enemy_ships:
            if enemy.current_star_index < 0 or enemy.is_traveling:
                continue

            targets = self._player_ships_at_star(enemy.current_star_index)
            if not targets:
                continue

            target = min(targets, key=lambda ship: (0 if ship.can_mine else 1, ship.hull))
            self._resolve_attack(enemy, target, dt, self._reset_player_ship_after_defeat)

        for ship in self._ships:
            if ship.current_star_index < 0 or ship.is_traveling:
                continue

            targets = self._enemy_ships_at_star(ship.current_star_index)
            if not targets:
                pirate_base = self._pirate_base_at_star(ship.current_star_index)
                if pirate_base is not None:
                    self._resolve_pirate_base_attack(ship, pirate_base, dt)
                continue

            target = min(targets, key=lambda enemy: enemy.hull)
            self._resolve_attack(ship, target, dt, self._reset_enemy_ship_after_defeat)

        self._update_structures(dt)

    def _resolve_attack(
        self,
        attacker: PlayerShip | EnemyShip,
        defender: PlayerShip | EnemyShip,
        dt: float,
        on_defeat: Callable[[PlayerShip | EnemyShip], None],
    ) -> None:
        if attacker.hull <= 0 or defender.hull <= 0:
            return

        attacks = self._attack_cycles(attacker, dt)
        if attacks <= 0:
            return

        defender.hull = max(0.0, defender.hull - attacker.attack_damage * attacks)
        if defender.hull <= 0:
            on_defeat(defender)

    def _attack_cycles(self, ship: PlayerShip | EnemyShip, dt: float) -> int:
        if ship.attack_cooldown <= 0:
            return 0

        ship.attack_cooldown_remaining -= dt
        attacks = 0
        while ship.attack_cooldown_remaining <= 0:
            attacks += 1
            ship.attack_cooldown_remaining += ship.attack_cooldown
        return attacks

    def _reset_player_ship_after_defeat(self, ship: PlayerShip | EnemyShip) -> None:
        if not isinstance(ship, PlayerShip):
            return

        home_star_index = self._home_star_index()
        ship.current_star_index = home_star_index
        ship.origin_star_index = None
        ship.destination_star_index = None
        ship.travel_progress = 0.0
        ship.route_star_indices.clear()
        ship.mining_star_index = None
        ship.cargo_resource_type = None
        ship.cargo_amount = 0.0
        ship.hull = ship.max_hull
        ship.attack_cooldown_remaining = 0.0

        if ship is self.selected_ship and home_star_index >= 0:
            self._selected_star = self._stars[home_star_index]

    def _reset_enemy_ship_after_defeat(self, ship: PlayerShip | EnemyShip) -> None:
        if not isinstance(ship, EnemyShip):
            return

        if ship.spawned_from_base and self._pirate_base_at_star(ship.home_star_index) is None:
            if ship in self._enemy_ships:
                self._enemy_ships.remove(ship)
            return

        ship.current_star_index = ship.home_star_index
        ship.origin_star_index = None
        ship.destination_star_index = None
        ship.travel_progress = 0.0
        ship.route_star_indices.clear()
        ship.hull = ship.max_hull
        ship.attack_cooldown_remaining = 0.0
        ship.patrol_step = 0

    def _update_ship(self, ship: PlayerShip | EnemyShip, dt: float) -> None:
        if not ship.is_traveling:
            return

        destination_index = ship.destination_star_index
        origin_index = ship.origin_star_index
        if destination_index is None or origin_index is None:
            return

        travel_distance = self._distance_between_stars(origin_index, destination_index)
        if travel_distance <= 0:
            self._finish_ship_travel(ship, destination_index)
            return

        ship.travel_progress = min(
            1.0,
            ship.travel_progress + (dt * ship.speed / travel_distance),
        )
        if ship.travel_progress >= 1.0:
            self._finish_ship_travel(ship, destination_index)

    def _finish_ship_travel(self, ship: PlayerShip | EnemyShip, destination_index: int) -> None:
        ship.current_star_index = destination_index
        ship.travel_progress = 0.0
        ship.origin_star_index = None

        if ship.route_star_indices:
            next_destination = ship.route_star_indices.pop(0)
            ship.origin_star_index = destination_index
            ship.destination_star_index = next_destination
            return

        ship.destination_star_index = None

    def _start_ship_route(self, ship: PlayerShip | EnemyShip, path_indices: list[int]) -> None:
        if len(path_indices) < 2:
            return

        ship.origin_star_index = path_indices[0]
        ship.destination_star_index = path_indices[1]
        ship.route_star_indices = path_indices[2:]
        ship.travel_progress = 0.0

    def _generate_stars(
        self,
        rng: Random,
        star_count: int,
        resource_types: tuple[str, ...],
        star_names: list[str],
    ) -> tuple[list[StarSystem], tuple[int, ...]]:
        if star_count <= 0:
            return [], tuple()

        region_count = self._region_count_for_star_total(star_count)
        region_sizes = self._region_sizes(star_count, region_count)
        region_centers = self._region_centers(region_count)
        stars: list[StarSystem] = []
        star_regions: list[int] = []

        for region_index, region_size in enumerate(region_sizes):
            center_x, center_y = region_centers[region_index]
            for local_index in range(region_size):
                star_index = len(stars)
                x, y = self._star_position_for_region(rng, stars, center_x, center_y, region_index == 0 and local_index == 0)
                richness = rng.randint(1, 5)
                capacity = float(80 + richness * 45)
                stars.append(
                    StarSystem(
                        name=star_names[star_index % len(star_names)],
                        x=x,
                        y=y,
                        radius=rng.randint(9, 18),
                        phase=rng.random() * 6.283,
                        richness=richness,
                        color=(rng.randint(180, 255), rng.randint(180, 255), 255),
                        resource_type=resource_types[star_index % len(resource_types)],
                        resource_stock=rng.uniform(capacity * 0.35, capacity * 0.8),
                        resource_capacity=capacity,
                        production_rate=1.4 + richness * 0.9,
                    )
                )
                star_regions.append(region_index)

        return stars, tuple(star_regions)

    def _region_count_for_star_total(self, star_count: int) -> int:
        if star_count <= 1:
            return star_count
        if star_count < 6:
            return 2
        return min(5, max(3, star_count // 6))

    def _region_sizes(self, star_count: int, region_count: int) -> list[int]:
        region_sizes = [2 if region_index == 0 and star_count > 1 else 1 for region_index in range(region_count)]
        remaining = max(0, star_count - sum(region_sizes))
        cursor = 0
        while remaining > 0:
            region_sizes[cursor % region_count] += 1
            cursor += 1
            remaining -= 1
        return region_sizes

    def _region_centers(self, region_count: int) -> tuple[tuple[float, float], ...]:
        templates: dict[int, tuple[tuple[float, float], ...]] = {
            1: ((0.24, 0.52),),
            2: ((0.24, 0.52), (0.72, 0.52)),
            3: ((0.22, 0.52), (0.48, 0.30), (0.76, 0.66)),
            4: ((0.22, 0.52), (0.48, 0.30), (0.48, 0.74), (0.78, 0.52)),
            5: ((0.22, 0.52), (0.42, 0.30), (0.42, 0.74), (0.74, 0.34), (0.74, 0.70)),
        }
        normalized_centers = templates[region_count]
        min_x = 180.0
        max_x = float(self._world_size[0] - 180)
        min_y = 180.0
        max_y = float(self._world_size[1] - 180)
        span_x = max_x - min_x
        span_y = max_y - min_y
        return tuple((min_x + norm_x * span_x, min_y + norm_y * span_y) for norm_x, norm_y in normalized_centers)

    def _star_position_for_region(
        self,
        rng: Random,
        existing_stars: list[StarSystem],
        center_x: float,
        center_y: float,
        is_home_star: bool,
    ) -> tuple[float, float]:
        if is_home_star:
            return (center_x, center_y)

        min_x = 180.0
        max_x = float(self._world_size[0] - 180)
        min_y = 180.0
        max_y = float(self._world_size[1] - 180)
        spread_x = max(85.0, self._world_size[0] * 0.055)
        spread_y = max(70.0, self._world_size[1] * 0.075)
        minimum_spacing = max(72.0, min(self._world_size) * 0.065)

        for attempt in range(36):
            falloff = 1.0 + attempt * 0.06
            candidate_x = max(min_x, min(max_x, center_x + rng.uniform(-spread_x, spread_x) * falloff))
            candidate_y = max(min_y, min(max_y, center_y + rng.uniform(-spread_y, spread_y) * falloff))
            if all(hypot(candidate_x - star.x, candidate_y - star.y) >= minimum_spacing for star in existing_stars):
                return (candidate_x, candidate_y)

        return (
            max(min_x, min(max_x, center_x + rng.uniform(-spread_x, spread_x))),
            max(min_y, min(max_y, center_y + rng.uniform(-spread_y, spread_y))),
        )

    def _generate_lanes(self) -> tuple[tuple[int, int], ...]:
        if len(self._stars) < 2:
            return tuple()

        if len(self._star_regions) != len(self._stars):
            return self._generate_distance_lanes()

        lane_set: set[tuple[int, int]] = set()
        region_to_star_indices: dict[int, list[int]] = {}
        for star_index, region_index in enumerate(self._star_regions):
            region_to_star_indices.setdefault(region_index, []).append(star_index)

        for star_indices in region_to_star_indices.values():
            lane_set.update(self._cluster_lanes(star_indices))

        region_bridge_candidates: list[tuple[float, int, int, tuple[int, int]]] = []
        sorted_regions = sorted(region_to_star_indices)
        for offset, start_region in enumerate(sorted_regions):
            for end_region in sorted_regions[offset + 1 :]:
                distance, star_pair = self._closest_star_pair(
                    region_to_star_indices[start_region],
                    region_to_star_indices[end_region],
                )
                region_bridge_candidates.append((distance, start_region, end_region, star_pair))

        lane_set.update(self._region_bridge_lanes(region_bridge_candidates, len(sorted_regions)))
        return tuple(sorted(lane_set))

    def _generate_distance_lanes(self) -> tuple[tuple[int, int], ...]:
        lane_set: set[tuple[int, int]] = set()
        connected = {0}
        remaining = set(range(1, len(self._stars)))

        while remaining:
            best_pair: tuple[int, int] | None = None
            best_distance = float("inf")
            for start in connected:
                for end in remaining:
                    distance = self._distance_between_stars(start, end)
                    if distance < best_distance:
                        best_distance = distance
                        best_pair = (start, end)

            assert best_pair is not None
            lane_set.add(tuple(sorted(best_pair)))
            connected.add(best_pair[1])
            remaining.remove(best_pair[1])

        max_extra_length = min(self._world_size) * 0.42
        for index in range(len(self._stars)):
            distances = sorted(
                (
                    (self._distance_between_stars(index, other_index), other_index)
                    for other_index in range(len(self._stars))
                    if other_index != index
                ),
                key=lambda item: item[0],
            )
            for distance, other_index in distances[:2]:
                if distance <= max_extra_length:
                    lane_set.add(tuple(sorted((index, other_index))))

        return tuple(sorted(lane_set))

    def _cluster_lanes(self, star_indices: list[int]) -> set[tuple[int, int]]:
        if len(star_indices) < 2:
            return set()

        lane_set: set[tuple[int, int]] = set()
        connected = {star_indices[0]}
        remaining = set(star_indices[1:])

        while remaining:
            best_pair: tuple[int, int] | None = None
            best_distance = float("inf")
            for start in connected:
                for end in remaining:
                    distance = self._distance_between_stars(start, end)
                    if distance < best_distance:
                        best_distance = distance
                        best_pair = (start, end)

            assert best_pair is not None
            lane_set.add(tuple(sorted(best_pair)))
            connected.add(best_pair[1])
            remaining.remove(best_pair[1])

        max_extra_length = min(self._world_size) * 0.24
        nearest_neighbor_count = min(2, len(star_indices) - 1)
        for star_index in star_indices:
            distances = sorted(
                (
                    (self._distance_between_stars(star_index, other_index), other_index)
                    for other_index in star_indices
                    if other_index != star_index
                ),
                key=lambda item: item[0],
            )
            for distance, other_index in distances[:nearest_neighbor_count]:
                if distance <= max_extra_length:
                    lane_set.add(tuple(sorted((star_index, other_index))))

        return lane_set

    def _closest_star_pair(self, start_indices: list[int], end_indices: list[int]) -> tuple[float, tuple[int, int]]:
        best_distance = float("inf")
        best_pair = (start_indices[0], end_indices[0])
        for start_index in start_indices:
            for end_index in end_indices:
                distance = self._distance_between_stars(start_index, end_index)
                if distance < best_distance:
                    best_distance = distance
                    best_pair = (start_index, end_index)
        return best_distance, tuple(sorted(best_pair))

    def _region_bridge_lanes(
        self,
        bridge_candidates: list[tuple[float, int, int, tuple[int, int]]],
        region_count: int,
    ) -> set[tuple[int, int]]:
        if region_count <= 1:
            return set()

        lane_set: set[tuple[int, int]] = set()
        parent = {region_index: region_index for region_index in range(region_count)}
        bridge_counts = {region_index: 0 for region_index in range(region_count)}

        def find(region_index: int) -> int:
            while parent[region_index] != region_index:
                parent[region_index] = parent[parent[region_index]]
                region_index = parent[region_index]
            return region_index

        def union(start_region: int, end_region: int) -> None:
            parent[find(end_region)] = find(start_region)

        deferred_candidates: list[tuple[float, int, int, tuple[int, int]]] = []
        for distance, start_region, end_region, star_pair in sorted(bridge_candidates, key=lambda item: item[0]):
            if find(start_region) == find(end_region):
                deferred_candidates.append((distance, start_region, end_region, star_pair))
                continue
            union(start_region, end_region)
            lane_set.add(star_pair)
            bridge_counts[start_region] += 1
            bridge_counts[end_region] += 1

        if region_count < 4:
            return lane_set

        extra_bridge_budget = 1 if region_count < 5 else 2
        max_bridge_length = min(self._world_size) * 0.5
        for distance, start_region, end_region, star_pair in deferred_candidates:
            if extra_bridge_budget <= 0:
                break
            if distance > max_bridge_length:
                continue
            if star_pair in lane_set:
                continue
            if bridge_counts[start_region] >= 3 or bridge_counts[end_region] >= 3:
                continue
            lane_set.add(star_pair)
            bridge_counts[start_region] += 1
            bridge_counts[end_region] += 1
            extra_bridge_budget -= 1

        return lane_set

    def _bridge_lane_pairs(self) -> set[tuple[int, int]]:
        if len(self._star_regions) != len(self._stars):
            return set()
        return {
            tuple(sorted((a, b)))
            for a, b in self._lanes
            if self._star_regions[a] != self._star_regions[b]
        }

    def _generate_delivery_contracts(
        self,
        resource_types: tuple[str, ...],
        home_star_index: int,
    ) -> list[DeliveryContract]:
        if len(self._stars) < 2:
            return []

        contracts = []
        max_contracts = min(3, max(0, len(self._stars) - 1))
        for index, star in enumerate(self._stars):
            if index == home_star_index:
                continue

            resource_index = resource_types.index(star.resource_type)
            requested_resource = resource_types[(resource_index + 1) % len(resource_types)]
            contracts.append(
                DeliveryContract(
                    destination_star_index=index,
                    resource_type=requested_resource,
                    remaining_amount=float(10 + star.richness * 4),
                    reward_per_unit=4 + star.richness,
                )
            )
            if len(contracts) >= max_contracts:
                break

        return contracts

    def _generate_enemy_ships(self, enemy_count: int, home_star_index: int) -> list[EnemyShip]:
        if enemy_count <= 0 or home_star_index < 0 or not self._stars:
            return []

        pirate_base_indices = {base.star_index for base in self._pirate_bases}
        candidates = [
            index
            for index in range(len(self._stars))
            if index != home_star_index and index not in pirate_base_indices
        ]
        candidates.sort(key=lambda index: self._distance_between_stars(home_star_index, index), reverse=True)
        enemies: list[EnemyShip] = []

        for enemy_index, star_index in enumerate(candidates[:enemy_count]):
            patrol_neighbors = [star_index]
            for a, b in self._lanes:
                if a == star_index:
                    patrol_neighbors.append(b)
                elif b == star_index:
                    patrol_neighbors.append(a)

            patrol = tuple(dict.fromkeys(patrol_neighbors[:3]))
            enemies.append(
                EnemyShip(
                    name=f"Pirate-{enemy_index + 1}",
                    current_star_index=star_index,
                    home_star_index=star_index,
                    patrol_star_indices=patrol,
                )
            )

        return enemies

    def _generate_pirate_bases(self, home_star_index: int, pirate_base_count: int) -> list[PirateBase]:
        if pirate_base_count <= 0 or home_star_index < 0 or len(self._stars) < 3:
            return []

        candidates: list[tuple[int, float, int]] = []
        for star_index in range(len(self._stars)):
            if star_index == home_star_index or self._stars[star_index].owner == "Player":
                continue
            path = self._find_path_indices(home_star_index, star_index)
            if len(path) < 2:
                continue
            candidates.append((len(path) - 1, self._distance_between_stars(home_star_index, star_index), star_index))

        candidates.sort(key=lambda item: (-item[0], -item[1], item[2]))
        selected_indices: list[int] = []
        blocked_indices: set[int] = set()

        for _, _, star_index in candidates:
            if len(selected_indices) >= pirate_base_count:
                break
            if star_index in blocked_indices:
                continue
            selected_indices.append(star_index)
            blocked_indices.add(star_index)
            blocked_indices.update(self._neighbor_star_indices(star_index))

        for _, _, star_index in candidates:
            if len(selected_indices) >= pirate_base_count:
                break
            if star_index not in selected_indices:
                selected_indices.append(star_index)

        return [
            PirateBase(star_index=star_index, spawn_cooldown_remaining=6.0 + index * 2.5)
            for index, star_index in enumerate(selected_indices)
        ]

    def _distance_between_stars(self, start_index: int, end_index: int) -> float:
        start = self._stars[start_index]
        end = self._stars[end_index]
        return hypot(end.x - start.x, end.y - start.y)

    def _find_path_indices(
        self,
        start_index: int,
        end_index: int,
        blocked_indices: set[int] | None = None,
    ) -> tuple[int, ...]:
        if start_index == end_index:
            return (start_index,)

        blocked = set(blocked_indices or ())
        blocked.discard(start_index)
        if end_index in blocked:
            return tuple()

        adjacency = {index: [] for index in range(len(self._stars))}
        for a, b in self._lanes:
            if a in blocked or b in blocked:
                continue
            distance = self._distance_between_stars(a, b)
            adjacency[a].append((b, distance))
            adjacency[b].append((a, distance))

        queue = [(0.0, start_index)]
        distances = {start_index: 0.0}
        previous: dict[int, int] = {}

        while queue:
            current_distance, current = heappop(queue)
            if current == end_index:
                break
            if current_distance > distances.get(current, float("inf")):
                continue

            for neighbor, segment_distance in adjacency[current]:
                new_distance = current_distance + segment_distance
                if new_distance < distances.get(neighbor, float("inf")):
                    distances[neighbor] = new_distance
                    previous[neighbor] = current
                    heappush(queue, (new_distance, neighbor))

        if end_index not in distances:
            return tuple()

        path = [end_index]
        while path[-1] != start_index:
            path.append(previous[path[-1]])
        path.reverse()
        return tuple(path)

    def _find_enemy_path_indices(self, enemy: EnemyShip, end_index: int) -> tuple[int, ...]:
        return self._find_path_indices(enemy.current_star_index, end_index)

    def _neighbor_star_indices(self, star_index: int) -> tuple[int, ...]:
        neighbors = []
        for a, b in self._lanes:
            if a == star_index:
                neighbors.append(b)
            elif b == star_index:
                neighbors.append(a)
        return tuple(dict.fromkeys(neighbors))

    def _path_distance(self, path_indices: tuple[int, ...]) -> float:
        if len(path_indices) < 2:
            return 0.0
        return sum(
            self._distance_between_stars(path_indices[index], path_indices[index + 1])
            for index in range(len(path_indices) - 1)
        )

    def _indices_for_stars(self, stars: tuple[StarSystem, ...]) -> tuple[int, ...]:
        return tuple(self._index_of_star(star) for star in stars)

    def _ship_world_position(self, ship: PlayerShip | EnemyShip) -> tuple[float, float] | None:
        if ship.current_star_index < 0:
            return None

        current_star = self._stars[ship.current_star_index]
        destination_index = ship.destination_star_index
        origin_index = ship.origin_star_index
        if destination_index is None or origin_index is None:
            return (current_star.x, current_star.y)

        origin = self._stars[origin_index]
        destination = self._stars[destination_index]
        progress = ship.travel_progress
        return (
            origin.x + (destination.x - origin.x) * progress,
            origin.y + (destination.y - origin.y) * progress,
        )

    def _ship_draw_offset(
        self,
        ship: PlayerShip | EnemyShip,
        ship_index: int,
        fleet: list[PlayerShip] | list[EnemyShip],
    ) -> tuple[int, int]:
        if ship.is_traveling or ship.current_star_index < 0:
            return (0, 0)

        docked_group = [
            candidate
            for candidate in fleet
            if not candidate.is_traveling and candidate.current_star_index == ship.current_star_index
        ]
        if len(docked_group) <= 1:
            return (0, 0)

        local_index = docked_group.index(ship)
        if len(docked_group) == 2:
            offsets = ((-18, -14), (18, 14))
        elif len(docked_group) == 3:
            offsets = ((0, 0), (-24, -18), (24, 18))
        else:
            offsets = ((0, 0), (-24, -18), (24, 18), (-30, 24), (30, -24))

        return offsets[local_index % len(offsets)]

    def _ship_render_radius(self, is_selected: bool) -> int:
        return max(6, int((10 if is_selected else 8) * self._zoom))

    def _ship_health_ratio(self, ship: PlayerShip | EnemyShip) -> float:
        if ship.max_hull <= 0:
            return 0.0
        return max(0.0, min(1.0, ship.hull / ship.max_hull))

    def _ship_health_bar_geometry(
        self,
        center_x: float,
        center_y: float,
        radius: int,
        ship: PlayerShip | EnemyShip,
    ) -> tuple[tuple[int, int, int, int], tuple[int, int, int, int]]:
        bar_width = max(18, radius * 2 + 8)
        bar_height = max(4, int(radius * 0.45))
        bar_left = int(center_x - bar_width / 2)
        bar_top = int(center_y - radius - bar_height - 5)
        inner_width = max(1, bar_width - 2)
        fill_ratio = self._ship_health_ratio(ship)
        fill_width = 0 if fill_ratio <= 0 else max(1, min(inner_width, int(inner_width * fill_ratio)))
        background_rect = (bar_left, bar_top, bar_width, bar_height)
        fill_rect = (bar_left + 1, bar_top + 1, fill_width, max(1, bar_height - 2))
        return background_rect, fill_rect

    def _ship_health_bar_color(self, ship: PlayerShip | EnemyShip) -> tuple[int, int, int]:
        health_ratio = self._ship_health_ratio(ship)
        if health_ratio <= 0.33:
            return (255, 96, 96)
        if health_ratio <= 0.66:
            return (255, 206, 110)
        return (112, 232, 150)

    def _draw_ship_health_bar(
        self,
        surface: object,
        ship: PlayerShip | EnemyShip,
        center_x: float,
        center_y: float,
        radius: int,
    ) -> tuple[int, int, int, int]:
        pygame = require_pygame()
        background_rect, fill_rect = self._ship_health_bar_geometry(center_x, center_y, radius, ship)
        outline_color = (230, 238, 255) if isinstance(ship, PlayerShip) else (255, 220, 220)
        pygame.draw.rect(surface, (8, 12, 22), background_rect, border_radius=3)
        if fill_rect[2] > 0:
            pygame.draw.rect(surface, self._ship_health_bar_color(ship), fill_rect, border_radius=2)
        pygame.draw.rect(surface, outline_color, background_rect, 1, border_radius=3)
        return background_rect

    def _ship_click_radius(self, is_selected: bool) -> float:
        return max(18.0, self._ship_render_radius(is_selected) + 10.0)

    def _structure_marker_style(self, structure_name: str) -> tuple[str, tuple[int, int, int]]:
        return self._STRUCTURE_MARKER_STYLES[structure_name]

    def _draw_structure_marker(
        self,
        surface: object,
        structure_name: str,
        center_x: float,
        center_y: float,
        halo_radius: int,
    ) -> None:
        pygame = require_pygame()
        shape, color = self._structure_marker_style(structure_name)
        marker_radius = max(4, int(4 * self._zoom))
        marker_center = (int(center_x), int(center_y))
        if shape == "plus":
            pygame.draw.line(
                surface,
                (12, 18, 30),
                (marker_center[0] - marker_radius, marker_center[1]),
                (marker_center[0] + marker_radius, marker_center[1]),
                5,
            )
            pygame.draw.line(
                surface,
                color,
                (marker_center[0] - marker_radius, marker_center[1]),
                (marker_center[0] + marker_radius, marker_center[1]),
                3,
            )
            pygame.draw.line(
                surface,
                (12, 18, 30),
                (marker_center[0], marker_center[1] - marker_radius),
                (marker_center[0], marker_center[1] + marker_radius),
                5,
            )
            pygame.draw.line(
                surface,
                color,
                (marker_center[0], marker_center[1] - marker_radius),
                (marker_center[0], marker_center[1] + marker_radius),
                3,
            )
            return
        if shape == "triangle":
            pygame.draw.polygon(
                surface,
                color,
                (
                    (marker_center[0], marker_center[1] - marker_radius - 1),
                    (marker_center[0] + marker_radius, marker_center[1] + marker_radius),
                    (marker_center[0] - marker_radius, marker_center[1] + marker_radius),
                ),
            )
            pygame.draw.polygon(
                surface,
                (12, 18, 30),
                (
                    (marker_center[0], marker_center[1] - marker_radius - 1),
                    (marker_center[0] + marker_radius, marker_center[1] + marker_radius),
                    (marker_center[0] - marker_radius, marker_center[1] + marker_radius),
                ),
                1,
            )
            return
        marker_rect = pygame.Rect(0, 0, marker_radius * 2, marker_radius * 2)
        marker_rect.center = marker_center
        pygame.draw.rect(surface, color, marker_rect)
        pygame.draw.rect(surface, (12, 18, 30), marker_rect, 1)

    def _draw_pirate_base_marker(
        self,
        surface: object,
        base: PirateBase,
        center_x: float,
        center_y: float,
        halo_radius: int,
    ) -> None:
        pygame = require_pygame()
        base_radius = max(10, halo_radius + 2)
        points = (
            (int(center_x), int(center_y - base_radius - 2)),
            (int(center_x + base_radius + 2), int(center_y)),
            (int(center_x), int(center_y + base_radius + 2)),
            (int(center_x - base_radius - 2), int(center_y)),
        )
        pygame.draw.polygon(surface, (*self._PIRATE_BASE_FILL, 0), points)
        pygame.draw.polygon(surface, self._PIRATE_BASE_FILL, points, 3)
        pygame.draw.circle(surface, self._PIRATE_BASE_ACCENT, (int(center_x), int(center_y)), max(4, int(4 * self._zoom)))
        if self._zoom >= 0.85:
            marker_rect = pygame.Rect(0, 0, max(8, int(12 * self._zoom)), max(8, int(12 * self._zoom)))
            marker_rect.center = (int(center_x), int(center_y + base_radius + 10))
            pygame.draw.rect(surface, self._PIRATE_BASE_FILL, marker_rect, border_radius=2)
            pygame.draw.rect(surface, self._PIRATE_BASE_ACCENT, marker_rect, 1, border_radius=2)

    def _ship_icon_points(
        self,
        role: str,
        center: tuple[float, float],
        radius: int,
    ) -> tuple[tuple[int, int], ...]:
        x, y = center
        if role == "Command":
            return (
                (int(x), int(y - radius - 1)),
                (int(x + radius * 0.9), int(y)),
                (int(x), int(y + radius * 0.9)),
                (int(x - radius * 0.9), int(y)),
            )

        return (
            (int(x - radius), int(y - radius * 0.45)),
            (int(x - radius * 0.2), int(y - radius * 0.9)),
            (int(x + radius * 0.7), int(y - radius * 0.45)),
            (int(x + radius), int(y + radius * 0.2)),
            (int(x + radius * 0.15), int(y + radius)),
            (int(x - radius * 0.85), int(y + radius * 0.4)),
        )

    def _index_of_star(self, star: StarSystem) -> int:
        for index, candidate in enumerate(self._stars):
            if candidate is star:
                return index
        raise ValueError("Star does not belong to this scene")

    def _home_star_index(self) -> int:
        return 0 if self._stars else -1

    def _claim_cost(self, star: StarSystem) -> int:
        return 30 + star.richness * 15

    def _territory_income_rate(self, star: StarSystem) -> float:
        if self._stars and star is self._stars[0]:
            return 0.0
        return 0.8 + star.richness * 0.4

    def _structure_cost(self, structure_name: str) -> int:
        return self._STRUCTURE_COSTS[structure_name]

    def _structure_description(self, structure_name: str) -> str:
        if structure_name == STRUCTURE_SHIPYARD:
            return f"Repairs docked ships at +{self._SHIPYARD_REPAIR_RATE:.0f} hull/s"
        if structure_name == STRUCTURE_DEFENSE_STATION:
            return (
                "Auto-attacks pirate ships within "
                f"{self._DEFENSE_STATION_RANGE_HOPS} jump at +{self._DEFENSE_STATION_DAMAGE_PER_SECOND:.0f} damage/s"
            )
        if structure_name == STRUCTURE_MINING_STATION:
            bonus = (self._MINING_STATION_MULTIPLIER - 1.0) * 100
            return f"Boosts local resource growth by +{bonus:.0f}%"
        return "Structure online"

    def _star_resource_production_rate(self, star: StarSystem) -> float:
        if star.structure == STRUCTURE_MINING_STATION:
            return star.production_rate * self._MINING_STATION_MULTIPLIER
        return star.production_rate

    def _resolve_pirate_base_attack(self, attacker: PlayerShip, base: PirateBase, dt: float) -> None:
        if attacker.hull <= 0 or base.hull <= 0:
            return

        attacks = self._attack_cycles(attacker, dt)
        if attacks <= 0:
            return

        base.hull = max(0.0, base.hull - attacker.attack_damage * attacks)
        if base.hull <= 0:
            self._credits += base.reward_credits
            self._pirate_bases.remove(base)
            return

        if self._spawn_pirate_from_base(base):
            base.spawn_cooldown_remaining = base.spawn_interval
        else:
            base.spawn_cooldown_remaining = min(base.spawn_cooldown_remaining, base.spawn_interval * 0.35)

    def _is_adjacent_to_owned_territory(self, star_index: int) -> bool:
        star = self._stars[star_index]
        return any(neighbor.owner == "Player" for neighbor in self.connected_stars_for(star))

    def _selected_star_index(self) -> int | None:
        if self._selected_star is None:
            return None
        return self._index_of_star(self._selected_star)

    def _contract_for_star_index(self, star_index: int | None) -> DeliveryContract | None:
        if star_index is None:
            return None
        for contract in self._delivery_contracts:
            if contract.destination_star_index == star_index:
                return contract
        return None

    def _route_pairs(self, path_indices: tuple[int, ...]) -> set[tuple[int, int]]:
        return {
            tuple(sorted((path_indices[index], path_indices[index + 1])))
            for index in range(len(path_indices) - 1)
        }

    def _owned_lane_pairs(self) -> set[tuple[int, int]]:
        return {
            tuple(sorted((a, b)))
            for a, b in self._lanes
            if self._stars[a].owner == "Player" and self._stars[b].owner == "Player"
        }

    def _ship_route_pairs(self) -> set[tuple[int, int]]:
        ship = self.selected_ship
        if ship.destination_star_index is None:
            return set()

        active_path = (
            ship.current_star_index,
            ship.destination_star_index,
            *ship.route_star_indices,
        )
        return self._route_pairs(active_path)

    def _selected_route_pairs(self) -> set[tuple[int, int]]:
        ship = self.selected_ship
        if self._selected_star is None or self.ship_star is None or self.ship_is_traveling:
            return set()

        path_indices = self._find_path_indices(
            ship.current_star_index,
            self._index_of_star(self._selected_star),
        )
        if len(path_indices) < 2:
            return set()
        return self._route_pairs(path_indices)

    def _active_ship_lane(self) -> tuple[int, int] | None:
        ship = self.selected_ship
        if not ship.is_traveling or ship.origin_star_index is None:
            return None
        return tuple(
            sorted(
                (
                    ship.origin_star_index,
                    ship.destination_star_index,
                )
            )
        )
