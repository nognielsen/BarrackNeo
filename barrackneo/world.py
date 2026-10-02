"""Simulation: the blaster, the swarm, and the score. No drawing in here.

The blaster moves anywhere in the field. Fire sends a wall out both ends. The wall
grows until each end hits the border or an existing line, then every pocket
with no enemy in it fills. Filled ground does not block the blaster. A ball that
touches the blaster, or the wall while it is still growing, costs a life and the
unfinished wall comes back down.
"""

import math
import random
from dataclasses import dataclass

from barrackneo.board import EMPTY, TRAIL, Board
from barrackneo.settings import (
    BALL_RADIUS,
    BALL_SPEED,
    BLASTER_HIT,
    BLASTER_SPEED,
    BUILD_RATE,
    CELL,
    COMBO_WINDOW,
    EXTRA_LIFE_SCORE,
    HASTE_BUILD,
    MAX_BALLS,
    MAX_COMBO,
    MAX_LIVES,
    PICKUP_LIFE,
    START_LIVES,
    spec_for,
)


@dataclass
class Ball:
    x: float
    y: float
    vx: float
    vy: float
    speed: float
    kind: str
    radius: float = BALL_RADIUS
    visual: float = 16.0
    generation: int = 0
    can_split: bool = False
    cycle: float = 0.0
    phased: bool = False
    warning: bool = False


@dataclass
class Pickup:
    x: int
    y: int
    kind: str
    life: float = PICKUP_LIFE
    max_life: float = PICKUP_LIFE


class World:
    def __init__(
        self,
        level: int = 1,
        rng: random.Random | None = None,
        cols: int | None = None,
        rows: int | None = None,
        populate: bool = True,
        god: bool = False,
    ):
        self.rng = rng or random.Random()
        self.level = level
        self.spec = spec_for(level)
        self.quota = self.spec.quota
        self.speed_mult = self.spec.speed
        self.god = god
        self.board = Board(cols, rows) if cols and rows else Board()
        cx = self.board.cols // 2
        cy = self.board.rows // 2
        self.px, self.py = self.board.cell_center(cx, cy)
        self.horizontal = True
        self.move = (0.0, 0.0)
        self.pointer: tuple[float, float] | None = None
        self.want_fire = False
        self.want_rotate = False
        self.building = False
        self.trail: list[tuple[int, int]] = []
        self.arms: list[dict] = []
        self.build_acc = 0.0
        self.balls: list[Ball] = []
        self.pickups: list[Pickup] = []
        self.score = 0
        self.lives = START_LIVES
        self.next_life = EXTRA_LIFE_SCORE
        self.combo = 1
        self.combo_timer = 0.0
        self.shield = False
        self.haste = 0.0
        self.freeze = 0.0
        self.slow = 0.0
        self.mult = 0.0
        self.invuln = 0.0
        self.warmup = 1.1 if level == 1 else 0.55
        self.pickup_timer = 2.2 if populate else 1e9
        self.phase = "play"
        self.events: list[tuple] = []
        if populate:
            self._spawn_roster()

    def claim_ratio(self) -> float:
        return self.board.ratio()

    def render_pixel(self) -> tuple[float, float]:
        return self.px, self.py

    def ordered_trail(self) -> list[tuple[int, int]]:
        cells = list(self.trail)
        if self.horizontal:
            cells.sort(key=lambda cell: cell[0])
        else:
            cells.sort(key=lambda cell: cell[1])
        return cells

    def aim_cells(self) -> list[tuple[int, int]]:
        """Empty cells the next shot would cross, including the blaster."""
        if self.building or self.phase != "play":
            return []
        cx, cy = self.board.cell_at(self.px, self.py)
        if not self.board.in_bounds(cx, cy):
            return []
        cells = [(cx, cy)] if self.board.grid[cy][cx] == EMPTY else []
        for dx, dy in self._axes():
            x, y = cx, cy
            for _ in range(max(self.board.cols, self.board.rows)):
                x += dx
                y += dy
                if not self.board.in_bounds(x, y) or self.board.grid[y][x] != EMPTY:
                    break
                cells.append((x, y))
        return cells

    def nearest_threat(self) -> float:
        best = 9999.0
        for ball in self.balls:
            if ball.phased:
                continue
            best = min(best, math.hypot(ball.x - self.px, ball.y - self.py))
            if self.building:
                for cell in self.trail:
                    cx, cy = self.board.cell_center(*cell)
                    best = min(best, math.hypot(ball.x - cx, ball.y - cy))
        return best

    def roster(self) -> list[tuple[str, int]]:
        counts: dict[str, int] = {}
        for ball in self.balls:
            counts[ball.kind] = counts.get(ball.kind, 0) + 1
        order = ("ball", "seeker", "splitter", "phantom", "bosco")
        return [(name, counts[name]) for name in order if name in counts]

    def update(self, dt: float) -> None:
        self.events.clear()
        if self.phase != "play":
            return
        dt = min(max(dt, 0.0), 0.05)
        self._tick_timers(dt)
        if self.want_rotate:
            self._rotate()
        if self.want_fire:
            self._fire()
        self.want_fire = False
        self.want_rotate = False
        if self.building:
            self._grow(dt)
        else:
            self._move_blaster(dt)
            self._collect_blaster()
        if self.phase != "play":
            return
        if self._threatened():
            self._hurt("swarm")
            if self.phase != "play":
                return
        enemy_dt = self._enemy_dt(dt)
        for ball in self.balls:
            self._update_phantom(ball, enemy_dt)
            target = self._chase_target(ball)
            if target is not None and enemy_dt > 0:
                turn = 2.4 if ball.kind == "bosco" else 1.75
                self._steer(ball, enemy_dt, target, turn)
            self._move_ball(ball, enemy_dt)
        self._separate_balls()
        if self.phase != "play":
            return
        if self._threatened():
            self._hurt("swarm")
            return
        self._update_pickups(dt)
        if not self.building and self.claim_ratio() + 1e-6 >= self.quota:
            self._clear_sector()

    def _axes(self) -> tuple[tuple[int, int], tuple[int, int]]:
        if self.horizontal:
            return ((-1, 0), (1, 0))
        return ((0, -1), (0, 1))

    def _tick_timers(self, dt: float) -> None:
        self.invuln = max(0.0, self.invuln - dt)
        self.haste = max(0.0, self.haste - dt)
        self.freeze = max(0.0, self.freeze - dt)
        self.slow = max(0.0, self.slow - dt)
        self.mult = max(0.0, self.mult - dt)
        if self.warmup > 0:
            self.warmup = max(0.0, self.warmup - dt)
        if self.combo_timer > 0:
            self.combo_timer -= dt
            if self.combo_timer <= 0:
                self.combo = 1

    def _enemy_dt(self, dt: float) -> float:
        if self.freeze > 0:
            scaled = 0.0
        elif self.slow > 0:
            scaled = dt * 0.45
        else:
            scaled = dt
        if self.warmup > 0:
            scaled *= 0.2
        return scaled

    def _rotate(self) -> None:
        if self.building or self.phase != "play":
            return
        self.horizontal = not self.horizontal
        self.events.append(("rotate",))

    def _fire(self) -> None:
        if self.building or self.phase != "play" or self.invuln > 0:
            return
        cx, cy = self.board.cell_at(self.px, self.py)
        if not self.board.in_bounds(cx, cy):
            return
        origin_open = self.board.grid[cy][cx] == EMPTY
        if not origin_open and not self._shot_has_room(cx, cy):
            return
        self.building = True
        self.trail = []
        if origin_open:
            self.trail = [(cx, cy)]
            self.board.set_cell(cx, cy, TRAIL)
            self._collect_at(cx, cy)
        self.arms = []
        for dx, dy in self._axes():
            self.arms.append({"dx": dx, "dy": dy, "x": cx, "y": cy, "done": False})
        self.build_acc = 0.0
        self.events.append(("fire",))

    def _shot_has_room(self, cx: int, cy: int) -> bool:
        for dx, dy in self._axes():
            nx, ny = cx + dx, cy + dy
            if self.board.in_bounds(nx, ny) and self.board.grid[ny][nx] == EMPTY:
                return True
        return False

    def _grow(self, dt: float) -> None:
        rate = BUILD_RATE * (HASTE_BUILD if self.haste > 0 else 1.0)
        self.build_acc += dt * rate
        steps = 0
        while self.build_acc >= 1.0 and steps < 8 and self.building:
            self.build_acc -= 1.0
            steps += 1
            for arm in self.arms:
                if arm["done"]:
                    continue
                nx = arm["x"] + arm["dx"]
                ny = arm["y"] + arm["dy"]
                if not self.board.in_bounds(nx, ny) or self.board.grid[ny][nx] != EMPTY:
                    arm["done"] = True
                    continue
                self.board.set_cell(nx, ny, TRAIL)
                self.trail.append((nx, ny))
                arm["x"], arm["y"] = nx, ny
                self._collect_at(nx, ny)
            if self._threatened():
                self._hurt("line")
                return
            if self.arms and all(arm["done"] for arm in self.arms):
                if not self.trail:
                    self.building = False
                    self.arms.clear()
                    self.build_acc = 0.0
                    return
                self._finish_line()
                return

    def _finish_line(self) -> None:
        if not self.building:
            return
        if self._threatened():
            self._hurt("line")
            return
        trail = list(self.trail)
        region, samples = self.board.seal(trail, self._blocker_cells())
        self.building = False
        self.trail.clear()
        self.arms.clear()
        self.build_acc = 0.0
        self._collect_filled_pickups()
        self._unstick_balls()
        if self.combo_timer > 0:
            self.combo = min(MAX_COMBO, self.combo + 1)
        else:
            self.combo = 1
        self.combo_timer = COMBO_WINDOW
        gain = region * (8 + self.level) * self.combo + len(trail) * 2
        if self.mult > 0:
            gain *= 2
        self.score += gain
        self._check_life()
        self.events.append(("capture", region, gain, samples))
        self._maybe_split(region)
        if self.claim_ratio() + 1e-6 >= self.quota:
            self._clear_sector()

    def _clear_sector(self) -> None:
        if self.phase != "play":
            return
        over = max(0.0, self.claim_ratio() - self.quota)
        bonus = 2000 * self.level + int(over * 80000)
        if self.mult > 0:
            bonus *= 2
        self.score += bonus
        self._check_life()
        self.phase = "cleared"
        self.building = False
        self.events.append(("cleared", bonus))

    def _hurt(self, cause: str) -> None:
        if self.invuln > 0 or self.phase != "play":
            return
        if self.god:
            self._abort_line()
            self.invuln = 0.75
            self.events.append(("dodge", cause))
            return
        if self.shield:
            self.shield = False
            self._abort_line()
            self.invuln = 1.15
            self._respawn()
            self.events.append(("shield", cause))
            return
        self.lives -= 1
        self._abort_line()
        self.events.append(("hurt", cause))
        if self.lives <= 0:
            self.phase = "dead"
            return
        self.invuln = 1.5
        self._respawn()

    def _abort_line(self) -> None:
        for x, y in self.trail:
            if self.board.in_bounds(x, y) and self.board.grid[y][x] == TRAIL:
                self.board.set_cell(x, y, EMPTY)
        self.trail.clear()
        self.arms.clear()
        self.building = False
        self.build_acc = 0.0

    def _respawn(self) -> None:
        best = None
        best_score = -1.0
        for y in range(self.board.rows):
            for x in range(self.board.cols):
                if self.board.grid[y][x] != EMPTY:
                    continue
                clearance = self._clearance(x, y)
                if clearance > best_score:
                    best_score = clearance
                    best = (x, y)
        if best:
            self.px, self.py = self.board.cell_center(*best)

    def _clearance(self, x: int, y: int) -> float:
        px, py = self.board.cell_center(x, y)
        best = 9999.0
        for ball in self.balls:
            best = min(best, math.hypot(ball.x - px, ball.y - py))
        return best

    def _threatened(self) -> bool:
        if self.invuln > 0:
            return False
        for ball in self.balls:
            if ball.phased:
                continue
            reach = ball.radius + BLASTER_HIT
            if math.hypot(ball.x - self.px, ball.y - self.py) < reach:
                return True
            if not self.building:
                continue
            for cell in self.trail:
                if self.board.circle_hits_cell(ball.x, ball.y, ball.radius + 0.5, cell[0], cell[1]):
                    return True
        return False

    def _move_blaster(self, dt: float) -> None:
        if self.pointer is not None:
            self._travel(self.pointer[0], self.pointer[1])
            return
        dx, dy = self.move
        if dx == 0 and dy == 0:
            return
        speed = BLASTER_SPEED * (1.2 if self.haste > 0 else 1.0)
        self._travel(self.px + dx * speed * dt, self.py + dy * speed * dt)

    def _travel(self, tx: float, ty: float) -> None:
        dx = tx - self.px
        dy = ty - self.py
        dist = math.hypot(dx, dy)
        if dist < 0.35:
            return
        steps = max(1, int(dist / 3.0) + 1)
        sx = dx / steps
        sy = dy / steps
        for _ in range(steps):
            self._nudge(sx, sy)

    def _nudge(self, dx: float, dy: float) -> None:
        self._slide(dx, 0.0)
        self._slide(0.0, dy)
        margin = 3.0
        self.px = min(max(self.px, margin), self.board.pixel_w - margin)
        self.py = min(max(self.py, margin), self.board.pixel_h - margin)

    def _slide(self, dx: float, dy: float) -> None:
        if dx == 0.0 and dy == 0.0:
            return
        nx = self.px + dx
        ny = self.py + dy
        if self._can_occupy(nx, ny):
            self.px, self.py = nx, ny

    def _can_occupy(self, x: float, y: float) -> bool:
        cx, cy = self.board.cell_at(x, y)
        return self.board.in_bounds(cx, cy)

    def _blocker_cells(self) -> set[tuple[int, int]]:
        blocked: set[tuple[int, int]] = set()
        for ball in self.balls:
            reach = ball.radius
            minx = int((ball.x - reach) // CELL)
            maxx = int((ball.x + reach) // CELL)
            miny = int((ball.y - reach) // CELL)
            maxy = int((ball.y + reach) // CELL)
            for y in range(miny, maxy + 1):
                for x in range(minx, maxx + 1):
                    if not self.board.in_bounds(x, y) or self.board.grid[y][x] != EMPTY:
                        continue
                    if self.board.circle_hits_cell(ball.x, ball.y, ball.radius, x, y):
                        blocked.add((x, y))
        return blocked

    def _check_life(self) -> None:
        while self.score >= self.next_life:
            self.next_life += EXTRA_LIFE_SCORE
            if self.lives < MAX_LIVES:
                self.lives += 1
                self.events.append(("life",))

    def _spawn_roster(self) -> None:
        spec = self.spec
        for _ in range(spec.balls):
            self._spawn_ball("ball")
        for _ in range(spec.seekers):
            self._spawn_ball("seeker")
        for _ in range(spec.splitters):
            self._spawn_ball("splitter")
        for _ in range(spec.phantoms):
            self._spawn_ball("phantom")
        for _ in range(spec.boscos):
            self._spawn_ball("bosco")

    def _spawn_ball(self, kind: str) -> None:
        for _ in range(70):
            x = self.rng.randrange(self.board.border + 3, self.board.cols - self.board.border - 3)
            y = self.rng.randrange(self.board.border + 3, self.board.rows - self.board.border - 3)
            if self.board.grid[y][x] != EMPTY:
                continue
            px, py = self.board.cell_center(x, y)
            if math.hypot(px - self.px, py - self.py) < 110:
                continue
            if any(math.hypot(px - other.x, py - other.y) < 46 for other in self.balls):
                continue
            speed = BALL_SPEED * self.speed_mult * self.rng.uniform(0.92, 1.08)
            if kind == "seeker":
                speed *= 1.08
            elif kind == "phantom":
                speed *= 1.05
            elif kind == "splitter":
                speed *= 0.94
            elif kind == "bosco":
                speed *= 1.12
            angle = self.rng.random() * math.tau
            visual = {
                "ball": 16.0,
                "seeker": 18.0,
                "splitter": 20.0,
                "phantom": 17.0,
                "bosco": 20.0,
            }[kind]
            self.balls.append(
                Ball(
                    x=px,
                    y=py,
                    vx=math.cos(angle) * speed,
                    vy=math.sin(angle) * speed,
                    speed=speed,
                    kind=kind,
                    visual=visual,
                    can_split=kind == "splitter",
                    cycle=self.rng.random() * 6.0,
                )
            )
            return

    def _chase_target(self, ball: Ball) -> tuple[float, float] | None:
        if ball.kind == "bosco":
            return self.px, self.py
        if ball.kind != "seeker":
            return None
        if self.building and self.trail:
            best = (self.px, self.py)
            best_d = 1e18
            for cell in self.trail:
                cx, cy = self.board.cell_center(*cell)
                dist = (cx - ball.x) ** 2 + (cy - ball.y) ** 2
                if dist < best_d:
                    best_d = dist
                    best = (cx, cy)
            return best
        return self.px, self.py

    def _steer(self, ball: Ball, dt: float, target: tuple[float, float], turn: float) -> None:
        dx = target[0] - ball.x
        dy = target[1] - ball.y
        mag = math.hypot(dx, dy) or 1.0
        want_x = dx / mag * ball.speed
        want_y = dy / mag * ball.speed
        rate = min(1.0, dt * turn)
        ball.vx += (want_x - ball.vx) * rate
        ball.vy += (want_y - ball.vy) * rate

    def _update_phantom(self, ball: Ball, dt: float) -> None:
        if ball.kind != "phantom":
            ball.phased = False
            ball.warning = False
            return
        ball.cycle += dt
        local = ball.cycle % 6.0
        ball.warning = local > 4.15
        if local > 4.85:
            ball.phased = True
        elif self.board.circle_hits_solid(ball.x, ball.y, ball.radius):
            ball.phased = True
        else:
            ball.phased = False

    def _move_ball(self, ball: Ball, dt: float) -> None:
        if dt <= 0 or ball.speed <= 0:
            return
        if ball.phased:
            ball.x += ball.vx * dt
            ball.y += ball.vy * dt
            self._contain(ball)
            self._normalize(ball)
            return
        distance = ball.speed * dt
        steps = max(1, int(distance / 2.0) + 1)
        step_dt = dt / steps
        for _ in range(steps):
            nx = ball.x + ball.vx * step_dt
            if self.board.circle_hits_solid(nx, ball.y, ball.radius):
                ball.vx *= -1
                self._nudge_angle(ball)
            else:
                ball.x = nx
            ny = ball.y + ball.vy * step_dt
            if self.board.circle_hits_solid(ball.x, ny, ball.radius):
                ball.vy *= -1
                self._nudge_angle(ball)
            else:
                ball.y = ny
        self._normalize(ball)
        if self.board.circle_hits_solid(ball.x, ball.y, ball.radius):
            self._shove_to_empty(ball)

    def _contain(self, ball: Ball) -> None:
        margin = ball.radius + 2
        max_x = self.board.pixel_w - margin
        max_y = self.board.pixel_h - margin
        if ball.x < margin:
            ball.x = margin
            ball.vx = abs(ball.vx)
        elif ball.x > max_x:
            ball.x = max_x
            ball.vx = -abs(ball.vx)
        if ball.y < margin:
            ball.y = margin
            ball.vy = abs(ball.vy)
        elif ball.y > max_y:
            ball.y = max_y
            ball.vy = -abs(ball.vy)

    def _normalize(self, ball: Ball) -> None:
        speed = math.hypot(ball.vx, ball.vy)
        if speed < 1:
            ball.vx = ball.speed
            ball.vy = 0.0
            return
        ball.vx = ball.vx / speed * ball.speed
        ball.vy = ball.vy / speed * ball.speed

    def _nudge_angle(self, ball: Ball) -> None:
        angle = math.atan2(ball.vy, ball.vx) + self.rng.uniform(-0.12, 0.12)
        ball.vx = math.cos(angle) * ball.speed
        ball.vy = math.sin(angle) * ball.speed

    def _shove_to_empty(self, ball: Ball) -> None:
        best = None
        best_d = 1e18
        for y in range(self.board.rows):
            row = self.board.grid[y]
            for x in range(self.board.cols):
                if row[x] != EMPTY:
                    continue
                px, py = self.board.cell_center(x, y)
                if self.board.circle_hits_solid(px, py, ball.radius):
                    continue
                dist = (px - ball.x) ** 2 + (py - ball.y) ** 2
                if dist < best_d:
                    best_d = dist
                    best = (px, py)
        if best:
            ball.x, ball.y = best

    def _unstick_balls(self) -> None:
        for ball in self.balls:
            if not ball.phased and self.board.circle_hits_solid(ball.x, ball.y, ball.radius):
                self._shove_to_empty(ball)

    def _separate_balls(self) -> None:
        solid = [ball for ball in self.balls if not ball.phased]
        for i in range(len(solid)):
            for j in range(i + 1, len(solid)):
                a = solid[i]
                b = solid[j]
                dx = b.x - a.x
                dy = b.y - a.y
                dist = math.hypot(dx, dy) or 0.001
                need = a.radius + b.radius + 1.5
                if dist >= need:
                    continue
                push = (need - dist) * 0.5
                ux, uy = dx / dist, dy / dist
                a.x -= ux * push
                a.y -= uy * push
                b.x += ux * push
                b.y += uy * push

    def _maybe_split(self, region_cells: int) -> None:
        if region_cells < int(self.board.cols * self.board.rows * 0.045):
            return
        if len(self.balls) >= MAX_BALLS:
            return
        born: list[Ball] = []
        for ball in self.balls:
            if ball.kind != "splitter" or not ball.can_split or ball.generation >= 2:
                continue
            if len(self.balls) + len(born) >= MAX_BALLS:
                break
            ball.can_split = False
            child = self._clone_splitter(ball)
            if child:
                born.append(child)
                self.events.append(("split",))
        self.balls.extend(born)

    def _clone_splitter(self, ball: Ball) -> Ball | None:
        angle = math.atan2(ball.vy, ball.vx)
        child_angle = angle + 0.9
        parent_angle = angle - 0.9
        speed = ball.speed * 1.06
        ball.vx = math.cos(parent_angle) * ball.speed
        ball.vy = math.sin(parent_angle) * ball.speed
        child = Ball(
            x=ball.x + math.cos(child_angle) * 8,
            y=ball.y + math.sin(child_angle) * 8,
            vx=math.cos(child_angle) * speed,
            vy=math.sin(child_angle) * speed,
            speed=speed,
            kind="splitter",
            visual=max(8.0, ball.visual - 2.5),
            generation=ball.generation + 1,
            can_split=ball.generation + 1 < 2,
        )
        if self.board.circle_hits_solid(child.x, child.y, child.radius):
            child.x, child.y = ball.x, ball.y
            if self.board.circle_hits_solid(child.x, child.y, child.radius):
                return None
        return child

    def _update_pickups(self, dt: float) -> None:
        alive = []
        for pickup in self.pickups:
            pickup.life -= dt
            if pickup.life <= 0:
                continue
            if self.board.grid[pickup.y][pickup.x] == 1:
                self._apply_power(pickup.kind)
            else:
                alive.append(pickup)
        self.pickups = alive
        self.pickup_timer -= dt
        if self.pickup_timer <= 0:
            self.pickup_timer = self.rng.uniform(8.5, 13.5)
            if len(self.pickups) < 2:
                self._spawn_pickup()

    def _spawn_pickup(self) -> None:
        kind = self.rng.choice(("shield", "haste", "freeze", "slow", "mult"))
        for _ in range(40):
            x = self.rng.randrange(self.board.border + 2, self.board.cols - self.board.border - 2)
            y = self.rng.randrange(self.board.border + 2, self.board.rows - self.board.border - 2)
            if self.board.grid[y][x] != EMPTY:
                continue
            px, py = self.board.cell_center(x, y)
            if math.hypot(px - self.px, py - self.py) < 70:
                continue
            if any(math.hypot(px - ball.x, py - ball.y) < 36 for ball in self.balls):
                continue
            self.pickups.append(Pickup(x=x, y=y, kind=kind))
            return

    def _collect_blaster(self) -> None:
        cx, cy = self.board.cell_at(self.px, self.py)
        if self.board.in_bounds(cx, cy):
            self._collect_at(cx, cy)

    def _collect_at(self, x: int, y: int) -> None:
        kept = []
        for pickup in self.pickups:
            if pickup.x == x and pickup.y == y:
                self._apply_power(pickup.kind)
            else:
                kept.append(pickup)
        self.pickups = kept

    def _collect_filled_pickups(self) -> None:
        kept = []
        for pickup in self.pickups:
            if self.board.grid[pickup.y][pickup.x] == 1:
                self._apply_power(pickup.kind)
            else:
                kept.append(pickup)
        self.pickups = kept

    def _apply_power(self, kind: str) -> None:
        if kind == "shield":
            self.shield = True
        elif kind == "haste":
            self.haste = max(self.haste, 7.0)
        elif kind == "freeze":
            self.freeze = max(self.freeze, 4.4)
        elif kind == "slow":
            self.slow = max(self.slow, 7.0)
        elif kind == "mult":
            self.mult = max(self.mult, 8.0)
        self.score += 250 * self.level
        self._check_life()
        self.events.append(("power", kind))
