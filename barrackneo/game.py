"""Window, input, and juice. Rules live in world.py."""

import math
import random
from dataclasses import dataclass
from pathlib import Path

import pygame

from barrackneo.audio import Audio
from barrackneo.render import Renderer
from barrackneo.settings import CELL, FIELD_H, FIELD_W, FIELD_X, FIELD_Y, PICKUPS, WIN_H, WIN_W
from barrackneo.world import World

SCORE_PATH = Path(__file__).resolve().parent.parent / "highscore.txt"

KEYMAP = {
    pygame.K_RIGHT: (1, 0),
    pygame.K_d: (1, 0),
    pygame.K_LEFT: (-1, 0),
    pygame.K_a: (-1, 0),
    pygame.K_DOWN: (0, 1),
    pygame.K_s: (0, 1),
    pygame.K_UP: (0, -1),
    pygame.K_w: (0, -1),
}


@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    life: float
    max_life: float
    color: tuple
    radius: float


@dataclass
class Floater:
    x: float
    y: float
    text: str
    life: float
    color: tuple


def _flee_vector(world: World) -> tuple[float, float]:
    nearest = None
    nearest_d = 1e9
    for ball in world.balls:
        if ball.phased:
            continue
        dist = math.hypot(ball.x - world.px, ball.y - world.py)
        if dist < nearest_d:
            nearest_d = dist
            nearest = ball
    if nearest is None:
        return (0.0, 0.0)
    dx = world.px - nearest.x
    dy = world.py - nearest.y
    if abs(dx) >= abs(dy):
        return (1.0 if dx > 0 else -1.0, 0.0)
    return (0.0, 1.0 if dy > 0 else -1.0)


def _load_best() -> int:
    try:
        return max(0, int(SCORE_PATH.read_text().strip()))
    except (OSError, ValueError):
        return 0


class Game:
    def __init__(self) -> None:
        if not pygame.get_init():
            pygame.mixer.pre_init(22050, -16, 1, 512)
            pygame.init()
        pygame.display.set_caption("BarrackNeo")
        self.screen = pygame.display.set_mode((WIN_W, WIN_H))
        self.clock = pygame.time.Clock()
        self.renderer = Renderer(self.screen)
        self.audio = Audio()
        self.rng = random.Random()
        self.best = _load_best()
        self.state = "title"
        self.world: World | None = None
        self.demo = World(level=3, god=True, rng=self.rng)
        self.demo.warmup = 0.0
        self.demo_age = 0.0
        self.particles: list[Particle] = []
        self.floaters: list[Floater] = []
        self.shake = 0.0
        self.banner = 0.0
        self.time = 0.0
        self.last_dir = None
        self.mouse_aim: tuple[float, float] | None = None
        self.demo_dir = (1.0, 0.0)
        self.demo_hold = 0.0
        self.autoplay = False
        self.running = True
        self.checkpoint = (1, 0, 3, 40000)

    def run(self) -> None:
        try:
            while self.pump():
                pass
        finally:
            pygame.quit()

    def pump(self, dt: float | None = None) -> bool:
        if dt is None:
            dt = self.clock.tick(60) / 1000.0
        dt = min(0.033, max(0.0, dt))
        self.time += dt
        self._events()
        if not self.running:
            return False
        self._simulate(dt)
        self._draw()
        pygame.display.flip()
        return self.running

    def start(self, level: int, carry: World | None = None) -> None:
        world = World(level=level)
        if carry is not None:
            world.score = carry.score
            world.lives = carry.lives
            world.next_life = carry.next_life
        self.world = world
        self.state = "play"
        self.mouse_aim = None
        self.banner = 1.7
        self.shake = 0.0
        self.floaters.clear()
        self.particles.clear()
        self.checkpoint = (level, world.score, world.lives, world.next_life)

    def restart_sector(self) -> None:
        level, score, lives, next_life = self.checkpoint
        world = World(level=level)
        world.score = score
        world.lives = lives
        world.next_life = next_life
        self.world = world
        self.state = "play"
        self.mouse_aim = None
        self.banner = 1.2
        self.floaters.clear()
        self.particles.clear()

    def _events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                self._keydown(event.key)
            elif event.type == pygame.KEYUP:
                direction = KEYMAP.get(event.key)
                if direction is not None and direction == self.last_dir:
                    self.last_dir = None
            elif event.type == pygame.MOUSEBUTTONDOWN:
                self._mouse_down(event.button)
            elif event.type == pygame.MOUSEMOTION and self.state == "play":
                self._note_mouse(event.pos)
            elif event.type == pygame.MOUSEWHEEL and self.state == "play":
                self._request_rotate()

    def _keydown(self, key: int) -> None:
        direction = KEYMAP.get(key)
        if direction is not None:
            self.last_dir = direction
            return
        if key == pygame.K_ESCAPE:
            self._escape()
        elif key == pygame.K_RETURN:
            self._confirm()
        elif key == pygame.K_SPACE:
            if self.state == "play":
                self._request_fire()
            else:
                self._confirm()
        elif key == pygame.K_r and self.state == "pause":
            self.restart_sector()
        elif key == pygame.K_q and self.state in ("pause", "title"):
            self.running = False
        elif key in (pygame.K_q, pygame.K_f) and self.state == "play":
            self._request_rotate()

    def _mouse_down(self, button: int) -> None:
        if self.state == "title":
            if button == 1:
                self.start(1)
            return
        if self.state == "play":
            if button == 1:
                self._request_fire()
            elif button == 3:
                self._request_rotate()
            return
        if button == 1:
            self._confirm()

    def _request_fire(self) -> None:
        if self.world is not None and self.state == "play":
            self.world.want_fire = True

    def _request_rotate(self) -> None:
        if self.world is not None and self.state == "play":
            self.world.want_rotate = True

    def _escape(self) -> None:
        if self.state == "title":
            self.running = False
        elif self.state == "play":
            self.state = "pause"
        elif self.state == "pause":
            self.state = "play"
        elif self.state == "clear":
            self._advance()
        elif self.state == "over":
            self.state = "title"
            self._reset_demo()

    def _confirm(self) -> None:
        if self.state == "title":
            self.start(1)
        elif self.state == "pause":
            self.state = "play"
        elif self.state == "clear":
            self._advance()
        elif self.state == "over":
            self.start(1)

    def _advance(self) -> None:
        if self.world is None:
            self.start(1)
            return
        self.start(self.world.level + 1, self.world)

    def _simulate(self, dt: float) -> None:
        if self.state == "title":
            self.demo_age += dt
            self._demo_ai(self.demo, dt)
            self.demo.update(dt)
            self._consume(self.demo, audible=False)
            if self.demo.phase != "play" or self.demo_age > 46:
                self._reset_demo()
        elif self.state == "play" and self.world is not None:
            self.banner = max(0.0, self.banner - dt)
            if self.autoplay:
                self._demo_ai(self.world, dt)
            else:
                self._steer(self.world)
            self.world.update(dt)
            self._consume(self.world, audible=True)
            if self.world.phase == "cleared":
                self.state = "clear"
            elif self.world.phase == "dead":
                self.state = "over"
        self._tick_fx(dt)
        self.shake = max(0.0, self.shake - dt * 26)

    def _demo_ai(self, world: World, dt: float) -> None:
        world.pointer = None
        self.demo_hold -= dt
        if world.building:
            world.move = (0.0, 0.0)
            return
        threat = world.nearest_threat()
        if threat < 80:
            world.move = _flee_vector(world)
            return
        if self.demo_hold <= 0:
            self.demo_dir = self.rng.choice(((1.0, 0.0), (-1.0, 0.0), (0.0, 1.0), (0.0, -1.0)))
            self.demo_hold = self.rng.uniform(0.4, 1.2)
            if self.rng.random() < 0.35:
                world.want_rotate = True
        world.move = self.demo_dir
        if threat > 110 and self.rng.random() < 0.018:
            world.want_fire = True

    def _steer(self, world: World) -> None:
        direction = self._keys_dir()
        if direction != (0, 0):
            world.move = (float(direction[0]), float(direction[1]))
            world.pointer = None
            self.mouse_aim = None
            return
        world.move = (0.0, 0.0)
        world.pointer = self.mouse_aim
        self.mouse_aim = None

    def _note_mouse(self, pos: tuple[int, int]) -> None:
        mx, my = pos
        if FIELD_X <= mx < FIELD_X + FIELD_W and FIELD_Y <= my < FIELD_Y + FIELD_H:
            self.mouse_aim = (float(mx - FIELD_X), float(my - FIELD_Y))

    def _keys_dir(self):
        keys = pygame.key.get_pressed()
        if self.last_dir is not None:
            for key, direction in KEYMAP.items():
                if direction == self.last_dir and keys[key]:
                    return self.last_dir
        for key, direction in KEYMAP.items():
            if keys[key]:
                return direction
        return (0, 0)

    def _consume(self, world: World, audible: bool) -> None:
        accent = self.renderer.accent
        for event in world.events:
            kind = event[0]
            px, py = world.render_pixel()
            if kind == "fire" and audible:
                self.audio.play("dive")
            elif kind == "rotate" and audible:
                self.audio.play("rotate")
            elif kind == "dodge" and audible:
                self.audio.play("cancel")
            elif kind == "capture":
                _region, gain, samples = event[1], event[2], event[3]
                if audible:
                    self.audio.play("capture_big" if _region > 220 else "capture")
                    self.floaters.append(Floater(px - 10, py - 28, f"+{gain:,}", 0.95, (255, 228, 150)))
                color = (255, 210, 120) if _region > 220 else accent
                for x, y in samples:
                    self._burst((x + 0.5) * CELL, (y + 0.5) * CELL, color, 2, 70)
                self.shake = min(12.0, self.shake + 2.5 + min(8.0, _region / 90))
                self._note_score(world.score)
            elif kind == "hurt" and audible:
                self.audio.play("hurt")
                self.shake = 11
                self._burst(px, py, (255, 80, 90), 28, 160)
            elif kind == "shield" and audible:
                self.audio.play("shield")
                self.shake = 6
                self._burst(px, py, (120, 235, 255), 18, 120)
            elif kind == "power":
                if audible:
                    self.audio.play("power")
                label, color, _hint = PICKUPS.get(event[1], ("", accent, ""))
                self._burst(px, py, color, 16, 110)
                if audible:
                    self.floaters.append(Floater(px, py - 20, label, 0.9, color))
                self._note_score(world.score)
            elif kind == "split" and audible:
                self.audio.play("split")
            elif kind == "life" and audible:
                self.audio.play("life")
                self.floaters.append(Floater(FIELD_W * 0.5, 80, "EXTRA LIFE", 1.1, (120, 240, 255)))
            elif kind == "cleared":
                if audible:
                    self.audio.play("clear")
                    self.floaters.append(Floater(FIELD_W * 0.38, FIELD_H * 0.42, f"BONUS +{event[1]:,}", 1.4, (255, 220, 120)))
                self.shake = 8
                self._note_score(world.score)

    def _burst(self, x: float, y: float, color, count: int, speed: float) -> None:
        for _ in range(count):
            angle = self.rng.random() * math.tau
            vel = self.rng.uniform(speed * 0.25, speed)
            life = self.rng.uniform(0.28, 0.7)
            self.particles.append(
                Particle(
                    x=x,
                    y=y,
                    vx=math.cos(angle) * vel,
                    vy=math.sin(angle) * vel,
                    life=life,
                    max_life=life,
                    color=color,
                    radius=self.rng.uniform(1.5, 3.4),
                )
            )
        if len(self.particles) > 420:
            self.particles = self.particles[-420:]

    def _tick_fx(self, dt: float) -> None:
        alive = []
        for bit in self.particles:
            bit.life -= dt
            if bit.life <= 0:
                continue
            bit.x += bit.vx * dt
            bit.y += bit.vy * dt
            bit.vy += 40 * dt
            alive.append(bit)
        self.particles = alive
        texts = []
        for floater in self.floaters:
            floater.life -= dt
            if floater.life <= 0:
                continue
            floater.y -= 26 * dt
            texts.append(floater)
        self.floaters = texts

    def _note_score(self, score: int) -> None:
        if score <= self.best:
            return
        self.best = score
        try:
            SCORE_PATH.write_text(str(self.best))
        except OSError:
            pass

    def _reset_demo(self) -> None:
        self.demo = World(level=3, god=True, rng=self.rng)
        self.demo.warmup = 0.0
        self.demo_age = 0.0
        self.demo_hold = 0.0

    def _draw(self) -> None:
        shown = self.demo if self.state == "title" or self.world is None else self.world
        mag = self.shake if self.state == "play" else 0.0
        ox = int(math.sin(self.time * 58) * mag)
        oy = int(math.cos(self.time * 49) * mag)
        self.renderer.begin(shown.level, self.time, ox, oy)
        self.renderer.draw(shown, self.state, self.best, self.banner, self.particles, self.floaters)


def main() -> None:
    Game().run()
