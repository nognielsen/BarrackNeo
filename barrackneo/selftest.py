"""Rules tests that do not open a window."""

from barrackneo.board import FILLED, Board
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


def _advance(world: World, direction: tuple[int, int], moves: int) -> None:
    """Step the sim until the player has committed `moves` cell changes."""
    world.desired = direction
    done = 0
    previous = (world.player_x, world.player_y, world.lives, world.phase)
    for _ in range(moves * 6 + 8):
        world.update(0.05)
        current = (world.player_x, world.player_y, world.lives, world.phase)
        if current != previous:
            done += 1
            previous = current
        if done >= moves or world.phase != "play":
            return


def test_full_cut_clears_an_empty_sector() -> None:
    world = World(level=1, populate=False, cols=24, rows=16)
    _advance(world, (0, 1), 20)
    assert world.phase == "cleared"
    assert world.board.grid[8][5] == FILLED
    assert world.board.grid[8][18] == FILLED
    assert world.score > 0


def test_backtrack_cancels_a_one_cell_line() -> None:
    world = World(level=1, populate=False, cols=24, rows=16)
    _advance(world, (0, 1), 1)
    assert world.drawing
    x = world.player_x
    _advance(world, (0, -1), 1)
    assert not world.drawing
    assert world.trail == []
    assert world.board.grid[2][x] != 2


def test_ball_on_the_line_kills_instead_of_claiming() -> None:
    world = World(level=1, populate=False, cols=24, rows=16)
    world.lives = 3
    px, py = world.board.cell_center(world.player_x, world.player_y + 1)
    world.balls.append(Ball(x=px, y=py, vx=0, vy=0, speed=0, kind="ball"))
    _advance(world, (0, 1), 1)
    assert world.lives == 2
    assert not world.drawing
    assert world.phase == "play"


def test_shield_spends_instead_of_a_life() -> None:
    world = World(level=1, populate=False, cols=24, rows=16)
    world.shield = True
    px, py = world.board.cell_center(world.player_x, world.player_y + 1)
    world.balls.append(Ball(x=px, y=py, vx=0, vy=0, speed=0, kind="ball"))
    _advance(world, (0, 1), 1)
    assert world.lives == 3
    assert world.shield is False
    assert not world.drawing


def test_enemy_side_stays_open() -> None:
    world = World(level=1, populate=False, cols=24, rows=16)
    world.quota = 0.99
    world.drawing = True
    world.draw_origin = (12, 1)
    world.trail = [(12, y) for y in range(2, 14)]
    for x, y in world.trail:
        world.board.set_cell(x, y, 2)
    world.player_x, world.player_y = 12, 14
    cx, cy = world.board.cell_center(18, 8)
    world.balls.append(Ball(x=cx, y=cy, vx=40, vy=20, speed=80, kind="ball"))
    world._close_line()
    assert world.board.grid[8][6] == FILLED
    assert world.board.grid[8][18] != FILLED
    assert world.phase == "play"
    # The ball still has somewhere to sit.
    assert not world.board.circle_hits_solid(world.balls[0].x, world.balls[0].y, world.balls[0].radius)


def test_cell_size_matches_centers() -> None:
    board = Board(10, 8)
    px, py = board.cell_center(3, 4)
    assert board.cell_at(px, py) == (3, 4)
    assert CELL == 8


def main() -> None:
    tests = [
        test_seal_fills_the_empty_side,
        test_seal_keeps_both_sides_when_both_hold_enemies,
        test_full_cut_clears_an_empty_sector,
        test_backtrack_cancels_a_one_cell_line,
        test_ball_on_the_line_kills_instead_of_claiming,
        test_shield_spends_instead_of_a_life,
        test_enemy_side_stays_open,
        test_cell_size_matches_centers,
    ]
    for test in tests:
        test()
        print(f"ok  {test.__name__}")
    print(f"{len(tests)} tests passed")


if __name__ == "__main__":
    main()
