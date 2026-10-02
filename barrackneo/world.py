"""Simulation: the line, the swarm, and the score. No drawing in here."""

import math
import random
from collections import deque
from dataclasses import dataclass

from barrackneo.board import DIRS, EMPTY, TRAIL, Board
from barrackneo.settings import (
    BALL_RADIUS,
    BALL_SPEED,
    BOSCO_RATE,
    CELL,
    COMBO_WINDOW,
    EXTRA_LIFE_SCORE,
    HASTE_MULT,
    MAX_BALLS,
    MAX_COMBO,
    MAX_LIVES,
    MAX_STEPS_PER_FRAME,
    PICKUP_LIFE,
    PLAYER_RATE,
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
    visual: float = 9.0
    generation: int = 0
    can_split: bool = False
    cycle: float = 0.0
    phased: bool = False
    warning: bool = False


@dataclass
class Bosco:
    x: int
    y: int
    acc: float = 0.0
    facing: tuple = (1, 0)


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
        self.player_x = self.board.cols // 2
        self.player_y = 1
        self.from_x = self.player_x
        self.from_y = self.player_y
        self.facing = (1, 0)
        self.desired = (0, 0)
        self.move_acc = 0.0
        self.drawing = False
        self.trail: list[tuple[int, int]] = []
        self.draw_origin: tuple[int, int] | None = None
        self.balls: list[Ball] = []
        self.boscos: list[Bosco] = []
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
        self.warmup = 1.3 if level == 1 else 0.7
        self.pickup_timer = 2.2 if populate else 1e9
        self.phase = "play"
        self.events: list[tuple] = []
        if populate:
            self._spawn_roster()

    def claim_ratio(self) -> float:
        return self.board.ratio()

    def step_interval(self) -> float:
        rate = PLAYER_RATE * (HASTE_MULT if self.haste > 0 else 1.0)
        return 1.0 / rate

    def update(self, dt: float) -> None:
        self.events.clear()
        if self.phase != "play":
            return
        dt = min(dt, 0.05)
        self._tick_timers(dt)
        self._move_player(dt)
        if self.phase != "play":
            return
        enemy_dt = self._enemy_dt(dt)
        for ball in self.balls:
            self._update_phantom(ball, enemy_dt)
            if ball.kind == "seeker":
                self._steer_seeker(ball, enemy_dt)
            self._move_ball(ball, enemy_dt)
        self._separate_balls()
        if self.drawing and self._trail_hit():
            self._hurt("swarm")
            return
        self._move_boscos(enemy_dt)
        if self.phase != "play":
            return
        self._update_pickups(dt)
        if not self.drawing and self.claim_ratio() + 1e-6 >= self.quota:
            self._clear_sector()

    def classify(self, nx: int, ny: int) -> str | None:
        if not self.board.in_bounds(nx, ny):
            return None
        dest = self.board.grid[ny][nx]
        if not self.drawing:
            if dest == 1 and self.board.exposed(nx, ny):
                return "walk"
            if dest == 0 and self.board.exposed(self.player_x, self.player_y):
                return "dive"
            return None
        if len(self.trail) >= 2 and (nx, ny) == self.trail[-2]:
            return "back"
        if len(self.trail) == 1 and (nx, ny) == self.draw_origin:
            return "cancel"
        if dest == 0:
            return "draw"
        if dest == 1:
            return "close"
        return None

    def legal_moves(self) -> list[tuple[int, int]]:
        found = []
        for dx, dy in DIRS:
            if self.classify(self.player_x + dx, self.player_y + dy):
                found.append((dx, dy))
        return found

    def nearest_threat(self) -> float:
        if not self.drawing or not self.trail:
            return 9999.0
        tx, ty = self.board.cell_center(*self.trail[-1])
        best = 9999.0
        for ball in self.balls:
            if ball.phased:
                continue
            best = min(best, math.hypot(ball.x - tx, ball.y - ty))
        for bosco in self.boscos:
            bx, by = self.board.cell_center(bosco.x, bosco.y)
            best = min(best, math.hypot(bx - tx, by - ty))
        return best

    def render_cell(self) -> tuple[float, float]:
        if (self.from_x, self.from_y) == (self.player_x, self.player_y):
            return float(self.player_x), float(self.player_y)
        t = min(1.0, self.move_acc / self.step_interval())
        return (
            self.from_x + (self.player_x - self.from_x) * t,
            self.from_y + (self.player_y - self.from_y) * t,
        )

    def roster(self) -> list[tuple[str, int]]:
        counts: dict[str, int] = {}
        for ball in self.balls:
            counts[ball.kind] = counts.get(ball.kind, 0) + 1
        if self.boscos:
            counts["bosco"] = len(self.boscos)
        order = ("ball", "seeker", "splitter", "phantom", "bosco")
        return [(name, counts[name]) for name in order if name in counts]

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
            scaled *= 0.15
        return scaled

    def _move_player(self, dt: float) -> None:
        if self.desired == (0, 0):
            self.move_acc = 0.0
            self.from_x = self.player_x
            self.from_y = self.player_y
            return
        self.move_acc += dt
        interval = self.step_interval()
        steps = 0
        while self.move_acc >= interval and steps < MAX_STEPS_PER_FRAME:
            self.move_acc -= interval
            steps += 1
            if not self._try_step():
                self.move_acc = 0.0
                self.from_x = self.player_x
                self.from_y = self.player_y
                break
            if self.phase != "play":
                break
            if self.drawing and self._trail_hit():
                self._hurt("swarm")
                break

    def _try_step(self) -> bool:
        dx, dy = self.desired
        if dx == 0 and dy == 0:
            return False
        nx = self.player_x + dx
        ny = self.player_y + dy
        kind = self.classify(nx, ny)
        if kind is None:
            return False
        if kind == "walk":
            self._move_to(nx, ny)
            return True
        if kind == "dive":
            self.draw_origin = (self.player_x, self.player_y)
            self.drawing = True
            self.board.set_cell(nx, ny, TRAIL)
            self.trail = [(nx, ny)]
            self._move_to(nx, ny)
            self._collect_at(nx, ny)
            self.events.append(("dive",))
            return True
        if kind == "draw":
            self.board.set_cell(nx, ny, TRAIL)
            self.trail.append((nx, ny))
            self._move_to(nx, ny)
            self._collect_at(nx, ny)
            return True
        if kind == "back":
            cx, cy = self.trail.pop()
            self.board.set_cell(cx, cy, EMPTY)
            self._move_to(nx, ny)
            return True
        if kind == "cancel":
            cx, cy = self.trail.pop()
            self.board.set_cell(cx, cy, EMPTY)
            self.trail.clear()
            self.drawing = False
            self.draw_origin = None
            self._move_to(nx, ny)
            self.events.append(("cancel",))
            return True
        if kind == "close":
            self._move_to(nx, ny)
            self._close_line()
            return True
        return False

    def _move_to(self, nx: int, ny: int) -> None:
        self.from_x = self.player_x
        self.from_y = self.player_y
        self.facing = (nx - self.player_x, ny - self.player_y)
        self.player_x = nx
        self.player_y = ny

    def _close_line(self) -> None:
        if not self.drawing:
            return
        if self._trail_hit():
            self._hurt("swarm")
            return
        blocked = self._blocker_cells()
        trail = list(self.trail)
        region, samples = self.board.seal(trail, blocked)
        self.drawing = False
        self.trail.clear()
        self.draw_origin = None
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
        elif not self.board.exposed(self.player_x, self.player_y):
            self._respawn()

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
        self.drawing = False
        self.events.append(("cleared", bonus))

    def _hurt(self, cause: str) -> None:
        if self.invuln > 0 or self.phase != "play":
            return
        origin = self.draw_origin
        if self.god:
            self._abort_line()
            if origin and self.board.exposed(*origin):
                self.player_x, self.player_y = origin
                self.from_x, self.from_y = origin
            else:
                self._respawn()
            self.invuln = 0.7
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
        self.invuln = 1.55
        self._respawn()

    def _abort_line(self) -> None:
        for x, y in self.trail:
            self.board.set_cell(x, y, 0)
        self.trail.clear()
        self.drawing = False
        self.draw_origin = None

    def _respawn(self) -> None:
        best = None
        best_score = -1.0
        for y in range(self.board.rows):
            for x in range(self.board.cols):
                if not self.board.exposed(x, y):
                    continue
                clearance = self._clearance(x, y)
                # Prefer a bit of distance from the last death, all else equal.
                if clearance > best_score:
                    best_score = clearance
                    best = (x, y)
        if best:
            self.player_x, self.player_y = best
        self.from_x = self.player_x
        self.from_y = self.player_y
        self.move_acc = 0.0

    def _clearance(self, x: int, y: int) -> float:
        px, py = self.board.cell_center(x, y)
        best = 9999.0
        for ball in self.balls:
            best = min(best, math.hypot(ball.x - px, ball.y - py))
        for bosco in self.boscos:
            bx, by = self.board.cell_center(bosco.x, bosco.y)
            best = min(best, math.hypot(bx - px, by - py))
        return best

    def _trail_hit(self) -> bool:
        if not self.drawing:
            return False
        for ball in self.balls:
            if ball.phased:
                continue
            cx, cy = self.board.cell_at(ball.x, ball.y)
            for y in range(cy - 2, cy + 3):
                for x in range(cx - 2, cx + 3):
                    if not self.board.in_bounds(x, y):
                        continue
                    if self.board.grid[y][x] != TRAIL:
                        continue
                    if self.board.circle_hits_cell(ball.x, ball.y, ball.radius, x, y):
                        return True
        return False

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
                    if not self.board.in_bounds(x, y):
                        continue
                    if self.board.grid[y][x] != 0:
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
            self._spawn_bosco()

    def _spawn_ball(self, kind: str) -> None:
        player_px, player_py = self.board.cell_center(self.player_x, self.player_y)
        for _ in range(70):
            x = self.rng.randrange(self.board.border + 3, self.board.cols - self.board.border - 3)
            y = self.rng.randrange(self.board.border + 3, self.board.rows - self.board.border - 3)
            if self.board.grid[y][x] != 0:
                continue
            px, py = self.board.cell_center(x, y)
            if math.hypot(px - player_px, py - player_py) < 90:
                continue
            if any(math.hypot(px - other.x, py - other.y) < 46 for other in self.balls):
                continue
            speed = BALL_SPEED * self.speed_mult * self.rng.uniform(0.92, 1.08)
            if kind == "seeker":
                speed *= 1.12
            elif kind == "phantom":
                speed *= 1.05
            elif kind == "splitter":
                speed *= 0.94
            angle = self.rng.random() * math.tau
            visual = {"ball": 16.0, "seeker": 18.0, "splitter": 20.0, "phantom": 17.0}[kind]
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

    def _spawn_bosco(self) -> None:
        far = []
        near = []
        for y in range(self.board.rows):
            for x in range(self.board.cols):
                if not self.board.exposed(x, y):
                    continue
                dist = abs(x - self.player_x) + abs(y - self.player_y)
                if dist > 24:
                    far.append((x, y))
                elif dist > 4:
                    near.append((x, y))
        pool = far or near
        if not pool:
            return
        x, y = self.rng.choice(pool)
        self.boscos.append(Bosco(x=x, y=y, acc=self.rng.random() * 0.2))

    def _steer_seeker(self, ball: Ball, dt: float) -> None:
        if dt <= 0 or not self.drawing or not self.trail:
            return
        tx, ty = self.board.cell_center(*self.trail[-1])
        dx = tx - ball.x
        dy = ty - ball.y
        mag = math.hypot(dx, dy) or 1.0
        want_x = dx / mag * ball.speed
        want_y = dy / mag * ball.speed
        rate = min(1.0, dt * 1.7)
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
                if row[x] != 0:
                    continue
                px, py = self.board.cell_center(x, y)
                if self.board.circle_hits_solid(px, py, ball.radius):
                    continue
                d = (px - ball.x) ** 2 + (py - ball.y) ** 2
                if d < best_d:
                    best_d = d
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

    def _move_boscos(self, dt: float) -> None:
        if dt <= 0:
            return
        interval = 1.0 / (BOSCO_RATE * self.speed_mult)
        for bosco in self.boscos:
            bosco.acc += dt
            steps = 0
            while bosco.acc >= interval and steps < 3:
                bosco.acc -= interval
                steps += 1
                self._step_bosco(bosco)
                if self.phase != "play":
                    return

    def _bosco_walkable(self, x: int, y: int) -> bool:
        if not self.board.in_bounds(x, y):
            return False
        cell = self.board.grid[y][x]
        if cell == TRAIL:
            return True
        return cell == 1 and self.board.exposed(x, y)

    def _step_bosco(self, bosco: Bosco) -> None:
        if not self._bosco_walkable(bosco.x, bosco.y):
            self._relocate_bosco(bosco)
            return
        start = (bosco.x, bosco.y)
        goal = (self.player_x, self.player_y)
        if start == goal:
            self._hurt("bosco")
            return
        nxt = self._bosco_next(start, goal)
        if nxt is None or nxt == start:
            return
        bosco.facing = (nxt[0] - start[0], nxt[1] - start[1])
        bosco.x, bosco.y = nxt
        if (bosco.x, bosco.y) == (self.player_x, self.player_y):
            self._hurt("bosco")

    def _bosco_next(self, start: tuple[int, int], goal: tuple[int, int]) -> tuple[int, int] | None:
        if not self._bosco_walkable(*goal):
            goal = self._nearest_walkable(goal) or start
        queue = deque([start])
        prev = {start: None}
        found = None
        while queue:
            cur = queue.popleft()
            if cur == goal:
                found = cur
                break
            for dx, dy in DIRS:
                nxt = (cur[0] + dx, cur[1] + dy)
                if nxt not in prev and self._bosco_walkable(*nxt):
                    prev[nxt] = cur
                    queue.append(nxt)
        if found is None:
            options = []
            for dx, dy in DIRS:
                nxt = (start[0] + dx, start[1] + dy)
                if self._bosco_walkable(*nxt):
                    options.append(nxt)
            return self.rng.choice(options) if options else start
        cur = found
        while prev[cur] is not None and prev[cur] != start:
            cur = prev[cur]
        return cur

    def _nearest_walkable(self, goal: tuple[int, int]) -> tuple[int, int] | None:
        best = None
        best_d = 1e9
        gx, gy = goal
        for y in range(self.board.rows):
            for x in range(self.board.cols):
                if not self._bosco_walkable(x, y):
                    continue
                d = abs(x - gx) + abs(y - gy)
                if d < best_d:
                    best_d = d
                    best = (x, y)
        return best

    def _relocate_bosco(self, bosco: Bosco) -> None:
        spot = self._nearest_walkable((bosco.x, bosco.y))
        if spot:
            bosco.x, bosco.y = spot

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
            visual=max(7.0, ball.visual - 2.5),
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
            if pickup.life > 0 and self.board.grid[pickup.y][pickup.x] != 1:
                alive.append(pickup)
            elif pickup.life > 0 and self.board.grid[pickup.y][pickup.x] == 1:
                self._apply_power(pickup.kind)
        self.pickups = alive
        self.pickup_timer -= dt
        if self.pickup_timer <= 0:
            self.pickup_timer = self.rng.uniform(8.5, 13.5)
            if len(self.pickups) < 2:
                self._spawn_pickup()

    def _spawn_pickup(self) -> None:
        kind = self.rng.choice(("shield", "haste", "freeze", "slow", "mult"))
        player_px, player_py = self.board.cell_center(self.player_x, self.player_y)
        for _ in range(40):
            x = self.rng.randrange(self.board.border + 2, self.board.cols - self.board.border - 2)
            y = self.rng.randrange(self.board.border + 2, self.board.rows - self.board.border - 2)
            if self.board.grid[y][x] != 0:
                continue
            px, py = self.board.cell_center(x, y)
            if math.hypot(px - player_px, py - player_py) < 70:
                continue
            if any(math.hypot(px - b.x, py - b.y) < 36 for b in self.balls):
                continue
            self.pickups.append(Pickup(x=x, y=y, kind=kind))
            return

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
