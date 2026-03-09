from dataclasses import dataclass, field
from heapq import heappop, heappush
from math import hypot, sin
from random import Random

from game.core.scene import Scene
from game.runtime import require_pygame


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
class DeliveryContract:
    destination_star_index: int
    resource_type: str
    remaining_amount: float
    reward_per_unit: int


class StarMapScene(Scene):
    def __init__(
        self,
        world_width: int,
        world_height: int,
        viewport_width: int,
        viewport_height: int,
        star_count: int = 24,
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
        self._stars = []
        for index in range(star_count):
            richness = rng.randint(1, 5)
            capacity = float(80 + richness * 45)
            self._stars.append(
                StarSystem(
                    name=star_names[index % len(star_names)],
                    x=rng.randint(180, world_width - 180),
                    y=rng.randint(180, world_height - 180),
                    radius=rng.randint(9, 18),
                    phase=rng.random() * 6.283,
                    richness=richness,
                    color=(rng.randint(180, 255), rng.randint(180, 255), 255),
                    resource_type=resource_types[index % len(resource_types)],
                    resource_stock=rng.uniform(capacity * 0.35, capacity * 0.8),
                    resource_capacity=capacity,
                    production_rate=1.4 + richness * 0.9,
                )
            )
        self._lanes = self._generate_lanes()
        home_star_index = 0 if self._stars else -1
        self._ships = [
            PlayerShip(
                name="Flagship",
                role="Command",
                current_star_index=home_star_index,
                speed=360.0,
                color=(170, 245, 255),
            ),
            PlayerShip(
                name="Miner-1",
                role="Miner",
                current_star_index=home_star_index,
                speed=300.0,
                color=(255, 216, 150),
                can_mine=True,
                mining_rate=14.0,
            ),
            PlayerShip(
                name="Miner-2",
                role="Miner",
                current_star_index=home_star_index,
                speed=300.0,
                color=(140, 255, 170),
                can_mine=True,
                mining_rate=14.0,
            ),
        ]
        self._selected_ship_index = 0
        self._empire_resources = {resource: 0.0 for resource in resource_types}
        self._credits = 0.0
        self._delivery_contracts = self._generate_delivery_contracts(resource_types, home_star_index)

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
    def delivery_contracts(self) -> tuple[DeliveryContract, ...]:
        return tuple(self._delivery_contracts)

    @property
    def ship_world_position(self) -> tuple[float, float] | None:
        return self._ship_world_position(self.selected_ship)

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
                if self.select_ship_at_screen_pos(screen_pos) is None:
                    self.select_star_at_screen_pos(screen_pos)
            elif button == 3:
                star = self.star_at_screen_pos(getattr(event, "pos", (0, 0)))
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
        self._update_ships(dt)
        self._update_mining(dt)
        self._update_deliveries()
        self._update_star_resources(dt)

    def render(self, surface: object) -> None:
        pygame = require_pygame()
        self._viewport_size = surface.get_size()
        width, height = self._viewport_size
        if self._font is None:
            self._font = pygame.font.SysFont("arial", 18)

        self._draw_grid(surface)
        self._draw_lanes(surface)

        for star in self._stars:
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

            if self._selected_star is star:
                pygame.draw.circle(surface, (120, 180, 255), (int(screen_x), int(screen_y)), halo_radius + 6, 2)

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
        return selected

    def ship_at_screen_pos(self, screen_pos: tuple[int, int]) -> PlayerShip | None:
        for index in range(len(self._ships) - 1, -1, -1):
            ship = self._ships[index]
            ship_pos = self._ship_world_position(ship)
            if ship_pos is None:
                continue

            screen_x, screen_y = self.world_to_screen(ship_pos)
            offset_x, offset_y = self._ship_draw_offset(index)
            hit_radius = self._ship_click_radius(ship is self.selected_ship)
            if hypot(screen_x + offset_x - screen_pos[0], screen_y + offset_y - screen_pos[1]) <= hit_radius:
                return ship
        return None

    def select_ship_at_screen_pos(self, screen_pos: tuple[int, int]) -> PlayerShip | None:
        ship = self.ship_at_screen_pos(screen_pos)
        if ship is None:
            return None

        self._selected_ship_index = self._ships.index(ship)
        if ship.current_star_index >= 0 and not ship.is_traveling:
            self._selected_star = self._stars[ship.current_star_index]
        return ship

    def cycle_selected_ship(self) -> PlayerShip:
        self._selected_ship_index = (self._selected_ship_index + 1) % len(self._ships)
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

        if is_pressed and key == pygame.K_TAB:
            self.cycle_selected_ship()
            return

        if is_pressed and key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_t):
            self.issue_travel_order()
            return

        if is_pressed and key == pygame.K_m:
            self.toggle_mining()
            return

        if is_pressed and key in (pygame.K_EQUALS, pygame.K_PLUS, pygame.K_KP_PLUS):
            self.change_zoom(1)
        elif is_pressed and key in (pygame.K_MINUS, pygame.K_KP_MINUS):
            self.change_zoom(-1)

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
            offset_x, offset_y = self._ship_draw_offset(index)
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
                label_y = int(screen_y - radius - label_bg.get_height() - 6)
                surface.blit(label_bg, (label_x, label_y))
                surface.blit(label, (label_x + 4, label_y + 2))

        destination = self.ship_destination
        ship_pos = self.ship_world_position
        if destination is not None and ship_pos is not None:
            screen_x, screen_y = self.world_to_screen(ship_pos)
            offset_x, offset_y = self._ship_draw_offset(self._selected_ship_index)
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
        panel = pygame.Surface((530, 326), pygame.SRCALPHA)
        panel.fill((8, 12, 22, 220))
        pygame.draw.rect(panel, (50, 88, 150, 255), panel.get_rect(), 1, border_radius=10)
        surface.blit(panel, (16, 16))

        selected_contract = self._contract_for_star_index(self._selected_star_index())

        if self._selected_star is None:
            selected_name = "Selected: none"
            selected_resource = "Inspect a star to see mining details"
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
                f"Selected: {self._selected_star.name} | "
                f"Richness {self._selected_star.richness}/5"
            )
            selected_resource = (
                f"{self._selected_star.resource_type}: "
                f"{self._selected_star.resource_stock:.0f}/{self._selected_star.resource_capacity:.0f} "
                f"(+{self._selected_star.production_rate:.1f}/s) | {route_text}"
            )
            if selected_contract is not None:
                selected_resource += (
                    f" | Contract: {selected_contract.resource_type} "
                    f"{selected_contract.remaining_amount:.0f} @ {selected_contract.reward_per_unit}c"
                )

        if (
            self.ship_is_traveling
            and self.ship_destination is not None
            and self.ship_final_destination is not None
        ):
            ship_status = (
                f"Ship: {active_ship.name} | {self.ship_star.name} -> {self.ship_final_destination.name} | "
                f"{len(self.ship_route)} hops left"
            )
            ship_detail = (
                f"Role: {active_ship.role} | Current leg: {self.ship_destination.name} | "
                f"{active_ship.travel_progress:.0%} complete"
            )
        elif self.ship_star is None:
            ship_status = "Ship: awaiting deployment"
            ship_detail = "Mining: unavailable"
        else:
            ship_status = f"Ship: {active_ship.name} ({active_ship.role}) docked at {self.ship_star.name}"

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

        stockpile = self.empire_resources
        stockpile_text = (
            f"Delivered | H {stockpile.get('Hydrogen', 0.0):.0f}  "
            f"C {stockpile.get('Crystal', 0.0):.0f}  "
            f"M {stockpile.get('Metal', 0.0):.0f}"
        )
        active_miners = sum(ship.is_mining for ship in self.miner_ships)
        fleet_text = (
            f"Fleet: {len(self._ships)} ships | {active_miners}/{len(self.miner_ships)} miners active | "
            f"Selected: {active_ship.name}"
        )

        lines = [
            "Star Map Controls",
            "WASD / Arrows: pan camera",
            "Mouse wheel / +/-: zoom",
            "Left click: inspect star system or select ship",
            "Right click / T / Enter: travel route",
            "Tab: cycle ships | M: toggle mining for miner ships",
            f"Zoom: {self._zoom:.2f}x",
            fleet_text,
            ship_status,
            ship_detail,
            cargo_text,
            stockpile_text,
            selected_name,
            selected_resource,
        ]
        for index, text in enumerate(lines):
            color = (225, 235, 255) if index == 0 else (180, 198, 242)
            label = self._font.render(text, True, color)
            surface.blit(label, (28, 28 + index * 22))

        contract_lines = []
        for contract in self._delivery_contracts[:4]:
            destination = self._stars[contract.destination_star_index]
            contract_lines.append(
                f"{destination.name}: {contract.resource_type} {contract.remaining_amount:.0f} @ {contract.reward_per_unit}c"
            )
        if not contract_lines:
            contract_lines.append("No active delivery contracts")

        right_panel_width = 320
        right_panel_height = 84 + len(contract_lines) * 22
        right_panel = pygame.Surface((right_panel_width, right_panel_height), pygame.SRCALPHA)
        right_panel.fill((8, 12, 22, 220))
        pygame.draw.rect(right_panel, (80, 150, 110, 255), right_panel.get_rect(), 1, border_radius=10)
        panel_x = surface.get_width() - right_panel_width - 16
        surface.blit(right_panel, (panel_x, 16))

        right_lines = [f"Credits: {self._credits:.0f} c", "Active delivery contracts"]
        right_lines.extend(contract_lines)
        for index, text in enumerate(right_lines):
            color = (245, 248, 255) if index == 0 else (180, 225, 195) if index == 1 else (200, 220, 235)
            label = self._font.render(text, True, color)
            surface.blit(label, (panel_x + 14, 28 + index * 22))

    def _update_star_resources(self, dt: float) -> None:
        for star in self._stars:
            star.resource_stock = min(
                star.resource_capacity,
                star.resource_stock + star.production_rate * dt,
            )

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

    def _update_deliveries(self) -> None:
        for ship in self._ships:
            self._deliver_ship_cargo(ship)

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
        for ship in self._ships:
            self._update_ship(ship, dt)

    def _update_ship(self, ship: PlayerShip, dt: float) -> None:
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

    def _finish_ship_travel(self, ship: PlayerShip, destination_index: int) -> None:
        ship.current_star_index = destination_index
        ship.travel_progress = 0.0
        ship.origin_star_index = None

        if ship.route_star_indices:
            next_destination = ship.route_star_indices.pop(0)
            ship.origin_star_index = destination_index
            ship.destination_star_index = next_destination
            return

        ship.destination_star_index = None

    def _start_ship_route(self, ship: PlayerShip, path_indices: list[int]) -> None:
        if len(path_indices) < 2:
            return

        ship.origin_star_index = path_indices[0]
        ship.destination_star_index = path_indices[1]
        ship.route_star_indices = path_indices[2:]
        ship.travel_progress = 0.0

    def _generate_lanes(self) -> tuple[tuple[int, int], ...]:
        if len(self._stars) < 2:
            return tuple()

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

    def _distance_between_stars(self, start_index: int, end_index: int) -> float:
        start = self._stars[start_index]
        end = self._stars[end_index]
        return hypot(end.x - start.x, end.y - start.y)

    def _find_path_indices(self, start_index: int, end_index: int) -> tuple[int, ...]:
        if start_index == end_index:
            return (start_index,)

        adjacency = {index: [] for index in range(len(self._stars))}
        for a, b in self._lanes:
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

    def _path_distance(self, path_indices: tuple[int, ...]) -> float:
        if len(path_indices) < 2:
            return 0.0
        return sum(
            self._distance_between_stars(path_indices[index], path_indices[index + 1])
            for index in range(len(path_indices) - 1)
        )

    def _indices_for_stars(self, stars: tuple[StarSystem, ...]) -> tuple[int, ...]:
        return tuple(self._index_of_star(star) for star in stars)

    def _ship_world_position(self, ship: PlayerShip) -> tuple[float, float] | None:
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

    def _ship_draw_offset(self, ship_index: int) -> tuple[int, int]:
        offsets = ((0, 0), (-10, -8), (10, 8), (-12, 10), (12, -10))
        return offsets[ship_index % len(offsets)]

    def _ship_render_radius(self, is_selected: bool) -> int:
        return max(6, int((10 if is_selected else 8) * self._zoom))

    def _ship_click_radius(self, is_selected: bool) -> float:
        return max(18.0, self._ship_render_radius(is_selected) + 10.0)

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
