"""Window, speed, and sector tables."""

from dataclasses import dataclass


CELL = 8
COLS = 100
ROWS = 78
BORDER = 2

FIELD_X = 24
FIELD_Y = 20
PANEL_W = 312
MARGIN = 24
FIELD_W = COLS * CELL
FIELD_H = ROWS * CELL
PANEL_X = FIELD_X + FIELD_W + MARGIN
WIN_W = PANEL_X + PANEL_W + MARGIN
WIN_H = FIELD_Y + FIELD_H + MARGIN

PLAYER_RATE = 18.0
HASTE_MULT = 1.5
BALL_SPEED = 132.0
BALL_RADIUS = 6.0
BOSCO_RATE = 10.5
MAX_LIVES = 6
START_LIVES = 3
EXTRA_LIFE_SCORE = 40000
COMBO_WINDOW = 3.4
MAX_COMBO = 9
PICKUP_LIFE = 13.0
MAX_BALLS = 12
MAX_STEPS_PER_FRAME = 4

EMPTY_RGB = (0, 0, 0)
FIELD_BG = (7, 10, 18)
WINDOW_BG_TOP = (8, 10, 18)
WINDOW_BG_BOTTOM = (4, 5, 10)


@dataclass(frozen=True)
class LevelSpec:
    quota: float
    balls: int
    seekers: int
    splitters: int
    boscos: int
    phantoms: int
    speed: float
    title: str
    hint: str


_LEVELS = (
    LevelSpec(0.58, 1, 0, 0, 0, 0, 1.00, "Warm-up", "Dive off the rim. Cut back to a wall to claim empty ground."),
    LevelSpec(0.65, 2, 0, 0, 1, 0, 1.05, "Bosco", "Bosco runs the rim and will follow your line. Keep the cut short."),
    LevelSpec(0.70, 2, 1, 0, 1, 0, 1.10, "The Eye", "The eye chases the line while you draw. Juke, then close."),
    LevelSpec(0.74, 3, 1, 0, 1, 0, 1.15, "Crowded", "Three balls. Claim the side they are not on."),
    LevelSpec(0.76, 2, 1, 1, 1, 0, 1.18, "Splitter", "A big claim makes the green ball divide. Fence it in early."),
    LevelSpec(0.78, 3, 1, 1, 2, 0, 1.24, "Crossfire", "Two Boscos. Don't linger on the rim after a cut."),
    LevelSpec(0.80, 3, 2, 1, 2, 1, 1.30, "Phase", "Phantoms ghost through walls. They kill only while solid."),
    LevelSpec(0.82, 4, 2, 1, 2, 1, 1.36, "Red Hour", "The quota is high. Chain claims before the swarm settles."),
)


def spec_for(level: int) -> LevelSpec:
    if level <= len(_LEVELS):
        return _LEVELS[level - 1]
    extra = level - len(_LEVELS)
    last = _LEVELS[-1]
    return LevelSpec(
        quota=min(0.86, last.quota + 0.004 * extra),
        balls=min(6, last.balls + extra // 2),
        seekers=min(3, last.seekers + (1 if extra > 2 else 0)),
        splitters=min(2, last.splitters),
        boscos=min(3, last.boscos),
        phantoms=min(2, last.phantoms + extra // 5),
        speed=min(1.85, last.speed + 0.035 * extra),
        title=f"Deep {level}",
        hint="Same rules, less room for a slow cut.",
    )


def hsv(h: float, s: float, v: float) -> tuple[int, int, int]:
    h = h % 360.0
    c = v * s
    x = c * (1 - abs((h / 60.0) % 2 - 1))
    m = v - c
    if h < 60:
        r, g, b = c, x, 0
    elif h < 120:
        r, g, b = x, c, 0
    elif h < 180:
        r, g, b = 0, c, x
    elif h < 240:
        r, g, b = 0, x, c
    elif h < 300:
        r, g, b = x, 0, c
    else:
        r, g, b = c, 0, x
    return int((r + m) * 255), int((g + m) * 255), int((b + m) * 255)


_HUES = (174, 198, 262, 322, 36, 146, 214, 12)


def accent_for(level: int) -> tuple[int, int, int]:
    return hsv(_HUES[(level - 1) % len(_HUES)], 0.72, 1.0)


PICKUPS = {
    "shield": ("SHIELD", (90, 230, 255), "Absorb the next hit."),
    "haste": ("HASTE", (255, 220, 70), "Move faster for a few seconds."),
    "freeze": ("FREEZE", (150, 210, 255), "Stop the swarm cold."),
    "slow": ("SLOW", (200, 160, 255), "Drag every enemy down."),
    "mult": ("x2", (255, 170, 80), "Double points on the next claims."),
}

KIND_LABEL = {
    "ball": "Ball",
    "seeker": "Eye",
    "splitter": "Splitter",
    "phantom": "Phantom",
    "bosco": "Bosco",
}
