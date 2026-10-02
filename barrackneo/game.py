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


def auto_dir(world: World, rng: random.Random):
    legal = world.legal_moves()
    if not legal:
        return (0, 0)
    px, py = world.player_x, world.player_y

    def kind(direction):
        return world.classify(px + direction[0], py + direction[1])

    if world.drawing:
        if world.nearest_threat() < 42:
            backs = [d for d in legal if kind(d) in ("back", "cancel")]
            if backs:
                return backs[0]
        closes = [d for d in legal if kind(d) == "close"]
        long_enough = len(world.trail) > 12
        if closes and long_enough and (world.nearest_threat() < 96 or rng.random() < 0.22):
            return rng.choice(closes)
        if world.facing in legal and kind(world.facing) == "draw" and rng.random() < 0.9:
            return world.facing
        draws = [d for d in legal if kind(d) == "draw"]
        if draws:
            return rng.choice(draws)
        return rng.choice(legal)

    if rng.random() < 0.018:
        dives = [d for d in legal if kind(d) == "dive"]
        if dives:
            return rng.choice(dives)
    if world.facing in legal and rng.random() < 0.93:
        return world.facing
    return rng.choice(legal)


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

    def _keydown(self, key: int) -> None:
        direction = KEYMAP.get(key)
        if direction is not None:
            self.last_dir = direction
            return
        if key == pygame.K_ESCAPE:
            self._escape()
        elif key in (pygame.K_RETURN, pygame.K_SPACE):
            self._confirm()
        elif key == pygame.K_r and self.state == "pause":
            self.restart_sector()
        elif key == pygame.K_q and self.state in ("pause", "title"):
            self.running = False

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
            self.demo.desired = auto_dir(self.demo, self.rng)
            self.demo.update(dt)
            self._consume(self.demo, audible=False)
            if self.demo.phase != "play" or self.demo_age > 46:
                self._reset_demo()
        elif self.state == "play" and self.world is not None:
            self.banner = max(0.0, self.banner - dt)
            self.world.desired = self._aim(self.world)
            self.world.update(dt)
            self._consume(self.world, audible=True)
            if self.world.phase == "cleared":
                self.state = "clear"
            elif self.world.phase == "dead":
                self.state = "over"
        self._tick_fx(dt)
        self.shake = max(0.0, self.shake - dt * 26)

    def _aim(self, world: World):
        if self.autoplay:
            return auto_dir(world, self.rng)
        direction = self._keys_dir()
        if direction == (0, 0):
            direction = self._mouse_dir(world)
        return direction

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

    def _mouse_dir(self, world: World):
        if not pygame.mouse.get_pressed()[0]:
            return (0, 0)
        mx, my = pygame.mouse.get_pos()
        cx, cy = world.render_cell()
        sx = FIELD_X + (cx + 0.5) * CELL
        sy = FIELD_Y + (cy + 0.5) * CELL
        dx, dy = mx - sx, my - sy
        if mx > FIELD_X + FIELD_W or abs(dx) < 8 and abs(dy) < 8:
            return (0, 0)
        if abs(dx) > abs(dy):
            return (1 if dx > 0 else -1, 0)
        return (0, 1 if dy > 0 else -1)

    def _consume(self, world: World, audible: bool) -> None:
        accent = self.renderer.accent
        for event in world.events:
            kind = event[0]
            if kind == "dive" and audible:
                self.audio.play("dive")
            elif kind == "cancel" and audible:
                self.audio.play("cancel")
            elif kind == "capture":
                _region, gain, samples = event[1], event[2], event[3]
                if audible:
                    self.audio.play("capture_big" if _region > 220 else "capture")
                    cx, cy = world.render_cell()
                    self.floaters.append(
                        Floater((cx + 0.5) * CELL - 10, (cy + 0.5) * CELL - 28, f"+{gain:,}", 0.95, (255, 228, 150))
                    )
                color = (255, 210, 120) if _region > 220 else accent
                for x, y in samples:
                    self._burst((x + 0.5) * CELL, (y + 0.5) * CELL, color, 2, 70)
                self.shake = min(12.0, self.shake + 2.5 + min(8.0, _region / 90))
                self._note_score(world.score)
            elif kind == "hurt" and audible:
                self.audio.play("hurt")
                self.shake = 11
                cx, cy = world.render_cell()
                self._burst((cx + 0.5) * CELL, (cy + 0.5) * CELL, (255, 80, 90), 28, 160)
            elif kind == "shield" and audible:
                self.audio.play("shield")
                self.shake = 6
            elif kind == "power":
                if audible:
                    self.audio.play("power")
                label, color, _hint = PICKUPS.get(event[1], ("", accent, ""))
                cx, cy = world.render_cell()
                self._burst((cx + 0.5) * CELL, (cy + 0.5) * CELL, color, 16, 110)
                if audible:
                    self.floaters.append(Floater((cx + 0.5) * CELL, (cy + 0.5) * CELL - 20, label, 0.9, color))
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

    def _draw(self) -> None:
        shown = self.demo if self.state == "title" or self.world is None else self.world
        mag = self.shake if self.state == "play" else 0.0
        ox = int(math.sin(self.time * 58) * mag)
        oy = int(math.cos(self.time * 49) * mag)
        self.renderer.begin(shown.level, self.time, ox, oy)
        self.renderer.draw(shown, self.state, self.best, self.banner, self.particles, self.floaters)


def main() -> None:
    Game().run()
