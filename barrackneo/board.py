"""Grid, coastline, and the claim rule.

A finished line becomes wall. Every open pocket that contains no enemy
is filled. Pockets that still hold an enemy stay open. That is the whole puzzle.
"""

from collections import deque

from barrackneo.settings import BORDER, CELL, COLS, ROWS

EMPTY = 0
FILLED = 1
TRAIL = 2

DIRS = ((1, 0), (-1, 0), (0, 1), (0, -1))


class Board:
    def __init__(self, cols: int = COLS, rows: int = ROWS, border: int = BORDER):
        self.cols = cols
        self.rows = rows
        self.border = border
        self.grid = [[EMPTY] * cols for _ in range(rows)]
        self.filled_count = 0
        self.territory_dirty = True
        for y in range(rows):
            for x in range(cols):
                if x < border or y < border or x >= cols - border or y >= rows - border:
                    self.grid[y][x] = FILLED
                    self.filled_count += 1

    @property
    def pixel_w(self) -> int:
        return self.cols * CELL

    @property
    def pixel_h(self) -> int:
        return self.rows * CELL

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.cols and 0 <= y < self.rows

    def ratio(self) -> float:
        return self.filled_count / (self.cols * self.rows)

    def set_cell(self, x: int, y: int, value: int) -> None:
        old = self.grid[y][x]
        if old == value:
            return
        if old == FILLED:
            self.filled_count -= 1
            self.territory_dirty = True
        if value == FILLED:
            self.filled_count += 1
            self.territory_dirty = True
        self.grid[y][x] = value

    def exposed(self, x: int, y: int) -> bool:
        """Filled cell on the coastline: it touches open field or a line being drawn."""
        if not self.in_bounds(x, y) or self.grid[y][x] != FILLED:
            return False
        for dx, dy in DIRS:
            nx, ny = x + dx, y + dy
            if self.in_bounds(nx, ny) and self.grid[ny][nx] != FILLED:
                return True
        return False

    def cell_center(self, x: int, y: int) -> tuple[float, float]:
        return (x + 0.5) * CELL, (y + 0.5) * CELL

    def cell_at(self, px: float, py: float) -> tuple[int, int]:
        return int(px // CELL), int(py // CELL)

    def circle_hits_cell(self, px: float, py: float, radius: float, cx: int, cy: int) -> bool:
        rx = cx * CELL
        ry = cy * CELL
        nx = min(max(px, rx), rx + CELL)
        ny = min(max(py, ry), ry + CELL)
        dx = px - nx
        dy = py - ny
        return dx * dx + dy * dy < radius * radius

    def circle_hits_solid(self, px: float, py: float, radius: float) -> bool:
        minx = int((px - radius) // CELL)
        maxx = int((px + radius) // CELL)
        miny = int((py - radius) // CELL)
        maxy = int((py + radius) // CELL)
        for y in range(miny, maxy + 1):
            for x in range(minx, maxx + 1):
                if not self.in_bounds(x, y):
                    return True
                if self.grid[y][x] != EMPTY and self.circle_hits_cell(px, py, radius, x, y):
                    return True
        return False

    def seal(self, trail: list[tuple[int, int]], blocked: set[tuple[int, int]]) -> tuple[int, list[tuple[int, int]]]:
        """Turn the trail into wall and fill every empty pocket that has no blocker.

        Returns the number of newly filled open cells (not counting the trail)
        and a sample of the cells that became territory, for effects.
        """
        fresh: list[tuple[int, int]] = []
        for x, y in trail:
            if self.grid[y][x] != FILLED:
                self.set_cell(x, y, FILLED)
                fresh.append((x, y))

        seen: set[tuple[int, int]] = set()
        region_count = 0
        for y in range(self.rows):
            for x in range(self.cols):
                if self.grid[y][x] != EMPTY or (x, y) in seen:
                    continue
                queue = deque([(x, y)])
                seen.add((x, y))
                comp: list[tuple[int, int]] = []
                has_enemy = False
                while queue:
                    cx, cy = queue.popleft()
                    comp.append((cx, cy))
                    if (cx, cy) in blocked:
                        has_enemy = True
                    for dx, dy in DIRS:
                        nx, ny = cx + dx, cy + dy
                        if (
                            self.in_bounds(nx, ny)
                            and (nx, ny) not in seen
                            and self.grid[ny][nx] == EMPTY
                        ):
                            seen.add((nx, ny))
                            queue.append((nx, ny))
                if not has_enemy:
                    for cx, cy in comp:
                        self.set_cell(cx, cy, FILLED)
                        fresh.append((cx, cy))
                    region_count += len(comp)
        return region_count, _sample(fresh, 80)


def _sample(cells: list[tuple[int, int]], n: int) -> list[tuple[int, int]]:
    if len(cells) <= n:
        return cells
    step = len(cells) / n
    return [cells[int(i * step)] for i in range(n)]
