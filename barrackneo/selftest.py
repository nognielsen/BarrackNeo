"""Rules tests that do not open a window."""

from barrackneo.board import EMPTY, FILLED, TRAIL, Board
from barrackneo.settings import CELL
from barrackneo.world import Ball, World


def test_seal_fills_the_empty_side() -> None:
    board = Board(20, 14)
    trail = [(10, y) for y in range(2, 12)]
    for x, y in trail:
        board.set_cell(x, y, 2)
    region, _samples = board.seal(trail, {(15, 6)})
    assert region > 0
    assert board.grid[6][5] == FILLED
    assert board.grid[6][15] != FILLED
    assert board.grid[6][10] == FILLED


def test_seal_keeps_both_sides_when_both_hold_enemies() -> None:
    board = Board(20, 14)
    trail = [(10, y) for y in range(2, 12)]
    for x, y in trail:
        board.set_cell(x, y, 2)
    region, _samples = board.seal(trail, {(4, 6), (15, 6)})
    assert region == 0
    assert board.grid[6][5] != FILLED
    assert board.grid[6][15] != FILLED
    assert board.grid[6][10] == FILLED


def _quiet(world: World) -> None:
    world.warmup = 0.0
    world.quota = 0.99


def _until_idle(world: World, limit: int = 60) -> None:
    for _ in range(limit):
        world.update(0.05)
        if world.phase != "play" or not world.building:
            return


def test_rotate_flips_the_blaster() -> None:
    world = World(level=1, populate=False, cols=24, rows=16)
    assert world.horizontal
    world.want_rotate = True
    world.update(0.05)
    assert world.horizontal is False
    world.want_rotate = True
    world.want_fire = True
    world.update(0.05)
    assert world.horizontal
    assert world.building
    world.want_rotate = True
    world.update(0.05)
    assert world.building
    assert world.horizontal


def test_full_cut_clears_an_empty_sector() -> None:
    world = World(level=1, populate=False, cols=24, rows=16)
    world.warmup = 0.0
    world.want_rotate = True
    world.want_fire = True
    for _ in range(40):
        world.update(0.05)
        if world.phase != "play":
            break
    assert world.phase == "cleared"
    assert not world.building
    assert world.board.grid[8][5] == FILLED
    assert world.board.grid[8][18] == FILLED
    assert world.score > 0


def test_ball_on_the_line_kills_instead_of_claiming() -> None:
    world = World(level=1, populate=False, cols=24, rows=16)
    _quiet(world)
    cx, cy = world.board.cell_at(world.px, world.py)
    px, py = world.board.cell_center(cx + 3, cy)
    world.balls.append(Ball(x=px, y=py, vx=0.0, vy=0.0, speed=0.0, kind="ball"))
    before = world.claim_ratio()
    world.want_fire = True
    _until_idle(world)
    assert world.lives == 2
    assert not world.building
    assert world.phase == "play"
    assert world.claim_ratio() == before
    assert all(cell != TRAIL for row in world.board.grid for cell in row)


def test_shield_spends_instead_of_a_life() -> None:
    world = World(level=1, populate=False, cols=24, rows=16)
    _quiet(world)
    world.shield = True
    cx, cy = world.board.cell_at(world.px, world.py)
    px, py = world.board.cell_center(cx + 3, cy)
    world.balls.append(Ball(x=px, y=py, vx=0.0, vy=0.0, speed=0.0, kind="ball"))
    world.want_fire = True
    _until_idle(world)
    assert world.lives == 3
    assert world.shield is False
    assert not world.building
    assert world.phase == "play"


def test_ball_on_the_blaster_does_not_cost_a_life() -> None:
    world = World(level=1, populate=False, cols=24, rows=16)
    _quiet(world)
    world.balls.append(Ball(x=world.px, y=world.py, vx=0.0, vy=0.0, speed=0.0, kind="ball"))
    world.update(0.05)
    assert world.lives == 3
    assert world.phase == "play"
    assert not world.building
    world.want_rotate = True
    world.update(0.05)
    world.balls[0].x = world.px + 14
    world.want_fire = True
    _until_idle(world)
    assert world.lives == 3
    assert not world.building
    assert world.phase == "play"


def test_enemy_side_stays_open() -> None:
    world = World(level=1, populate=False, cols=24, rows=16)
    _quiet(world)
    world.want_rotate = True
    world.update(0.05)
    cx, cy = world.board.cell_at(world.px, world.py)
    bx, by = world.board.cell_center(cx + 6, cy)
    world.balls.append(Ball(x=bx, y=by, vx=0.0, vy=0.0, speed=0.0, kind="ball"))
    world.want_fire = True
    _until_idle(world)
    assert world.phase == "play"
    assert world.board.grid[cy][cx - 4] == FILLED
    assert world.board.grid[cy][cx + 6] != FILLED
    ball = world.balls[0]
    assert not world.board.circle_hits_solid(ball.x, ball.y, ball.radius)


def test_line_stops_at_an_existing_wall() -> None:
    world = World(level=1, populate=False, cols=24, rows=16)
    _quiet(world)
    cx, cy = world.board.cell_at(world.px, world.py)
    for y in range(world.board.rows):
        world.board.set_cell(cx + 4, y, FILLED)
    bx, by = world.board.cell_center(cx + 8, cy)
    world.balls.append(Ball(x=bx, y=by, vx=0.0, vy=0.0, speed=0.0, kind="ball"))
    world.want_fire = True
    _until_idle(world)
    assert not world.building
    assert world.phase == "play"
    assert world.lives == 3
    assert world.board.grid[cy][cx + 3] == FILLED
    assert world.board.grid[cy][cx + 5] != FILLED


def test_slow_cuts_enemy_motion() -> None:
    px, py = 80.0, 68.0

    def place() -> World:
        world = World(level=1, populate=False, cols=24, rows=16)
        world.warmup = 0.0
        world.balls.append(Ball(x=px, y=py, vx=100.0, vy=0.0, speed=100.0, kind="ball"))
        return world

    slowed = place()
    slowed.slow = 5.0
    slowed.update(0.05)
    plain = place()
    plain.update(0.05)
    assert plain.balls[0].x - px > (slowed.balls[0].x - px) * 1.5


def test_blaster_moves_and_can_fire_again() -> None:
    world = World(level=1, populate=False, cols=24, rows=16)
    _quiet(world)
    world.pointer = None
    world.move = (1.0, 0.0)
    start_x = world.px
    world.update(0.05)
    assert world.px > start_x + 10

    world.move = (0.0, 0.0)
    cx, cy = world.board.cell_at(world.px, world.py)
    bx, by = world.board.cell_center(cx, cy - 5)
    world.balls.append(Ball(x=bx, y=by, vx=0.0, vy=0.0, speed=0.0, kind="ball"))
    world.px, world.py = world.board.cell_center(cx, cy)
    world.want_fire = True
    _until_idle(world)
    assert world.phase == "play"
    assert not world.building
    assert world.board.cell_at(world.px, world.py) == (cx, cy)
    assert world.board.grid[cy + 2][cx] == FILLED
    world.pointer = None
    world.move = (0.0, 1.0)
    for _ in range(8):
        world.update(0.05)
    nx, ny = world.board.cell_at(world.px, world.py)
    assert ny > cy
    assert world.board.grid[ny][nx] == FILLED
    world.move = (0.0, -1.0)
    landed = None
    for _ in range(30):
        world.update(0.05)
        lx, ly = world.board.cell_at(world.px, world.py)
        if ly < cy and world.board.grid[ly][lx] == EMPTY:
            landed = (lx, ly)
            break
    world.move = (0.0, 0.0)
    assert landed is not None
    assert world.lives == 3
    world.want_fire = True
    world.update(0.05)
    assert world.building


def test_fire_from_a_wall_still_cuts() -> None:
    world = World(level=1, populate=False, cols=24, rows=16)
    _quiet(world)
    cx, cy = world.board.cell_at(world.px, world.py)
    world.board.set_cell(cx, cy, FILLED)
    world.want_fire = True
    world.update(0.05)
    assert world.building
    assert world.board.grid[cy][cx] == FILLED
    assert world.board.grid[cy][cx + 1] == TRAIL


def test_fire_inside_a_solid_box_does_not_claim() -> None:
    world = World(level=1, populate=False, cols=24, rows=16)
    _quiet(world)
    cx, cy = world.board.cell_at(world.px, world.py)
    for y in range(cy - 2, cy + 3):
        for x in range(cx - 2, cx + 3):
            world.board.set_cell(x, y, FILLED)
    before = world.claim_ratio()
    world.want_fire = True
    world.update(0.05)
    assert not world.building
    assert world.claim_ratio() == before


def test_haste_builds_the_line_faster() -> None:
    slow = World(level=1, populate=False, cols=24, rows=16)
    fast = World(level=1, populate=False, cols=24, rows=16)
    slow.warmup = 0.0
    fast.warmup = 0.0
    fast.haste = 5.0
    slow.want_fire = True
    fast.want_fire = True
    slow.update(0.05)
    fast.update(0.05)
    assert slow.building and fast.building
    assert len(fast.trail) > len(slow.trail)


def test_cell_size_matches_centers() -> None:
    board = Board(10, 8)
    px, py = board.cell_center(3, 4)
    assert board.cell_at(px, py) == (3, 4)
    assert CELL == 8


def main() -> None:
    tests = [
        test_seal_fills_the_empty_side,
        test_seal_keeps_both_sides_when_both_hold_enemies,
        test_rotate_flips_the_blaster,
        test_full_cut_clears_an_empty_sector,
        test_ball_on_the_line_kills_instead_of_claiming,
        test_shield_spends_instead_of_a_life,
        test_ball_on_the_blaster_does_not_cost_a_life,
        test_enemy_side_stays_open,
        test_line_stops_at_an_existing_wall,
        test_slow_cuts_enemy_motion,
        test_blaster_moves_and_can_fire_again,
        test_fire_from_a_wall_still_cuts,
        test_fire_inside_a_solid_box_does_not_claim,
        test_haste_builds_the_line_faster,
        test_cell_size_matches_centers,
    ]
    for test in tests:
        test()
        print(f"ok  {test.__name__}")
    print(f"{len(tests)} tests passed")


if __name__ == "__main__":
    main()
