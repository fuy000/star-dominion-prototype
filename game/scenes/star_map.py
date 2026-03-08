from dataclasses import dataclass
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
        star_names = [
            "Aster", "Helios", "Kepler", "Orion", "Vela", "Draco", "Nova", "Seris",
            "Cygnus", "Aquila", "Lumen", "Talos", "Persei", "Altair", "Erebus", "Lyra",
            "Janus", "Aquilae", "Icarus", "Nysa", "Theron", "Vesper", "Eos", "Solara",
        ]
        self._stars = [
            StarSystem(
                name=star_names[index % len(star_names)],
                x=rng.randint(180, world_width - 180),
                y=rng.randint(180, world_height - 180),
                radius=rng.randint(9, 18),
                phase=rng.random() * 6.283,
                richness=rng.randint(1, 5),
                color=(rng.randint(180, 255), rng.randint(180, 255), 255),
            )
            for index in range(star_count)
        ]

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
                self.select_star_at_screen_pos(getattr(event, "pos", (0, 0)))
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

    def render(self, surface: object) -> None:
        pygame = require_pygame()
        self._viewport_size = surface.get_size()
        width, height = self._viewport_size
        if self._font is None:
            self._font = pygame.font.SysFont("arial", 18)

        self._draw_grid(surface)

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
            surface.blit(halo_surface, (screen_x - halo_surface.get_width() // 2, screen_y - halo_surface.get_height() // 2))
            pygame.draw.circle(surface, (twinkle, min(255, twinkle + 10), 255), (int(screen_x), int(screen_y)), core_radius)

            if self._selected_star is star:
                pygame.draw.circle(surface, (120, 180, 255), (int(screen_x), int(screen_y)), halo_radius + 6, 2)

            if self._zoom >= 0.65:
                label = self._font.render(star.name, True, (190, 205, 255))
                surface.blit(label, (screen_x + 12, screen_y - 10))

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

    def select_star_at_screen_pos(self, screen_pos: tuple[int, int]) -> StarSystem | None:
        world_x, world_y = self.screen_to_world(screen_pos)
        for star in sorted(self._stars, key=lambda item: item.radius, reverse=True):
            if hypot(star.x - world_x, star.y - world_y) <= star.radius + (14 / self._zoom):
                self._selected_star = star
                return star

        self._selected_star = None
        return None

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

    def _draw_hud(self, surface: object) -> None:
        pygame = require_pygame()
        panel = pygame.Surface((330, 160), pygame.SRCALPHA)
        panel.fill((8, 12, 22, 220))
        pygame.draw.rect(panel, (50, 88, 150, 255), panel.get_rect(), 1, border_radius=10)
        surface.blit(panel, (16, 16))

        if self._selected_star is None:
            details = "No system selected"
        else:
            details = (
                f"Selected: {self._selected_star.name} | "
                f"Richness {self._selected_star.richness}/5"
            )

        lines = [
            "Star Map Controls",
            "WASD / Arrows: pan camera",
            "Mouse wheel / +/-: zoom",
            "Left click: inspect star system",
            f"Zoom: {self._zoom:.2f}x",
            details,
        ]
        for index, text in enumerate(lines):
            color = (225, 235, 255) if index == 0 else (180, 198, 242)
            label = self._font.render(text, True, color)
            surface.blit(label, (28, 28 + index * 22))
