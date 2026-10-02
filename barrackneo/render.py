"""Drawing. The simulation lives in world.py; this file only paints it."""

import math

import pygame

from barrackneo.settings import (
    CELL,
    FIELD_BG,
    FIELD_H,
    FIELD_W,
    FIELD_X,
    FIELD_Y,
    KIND_LABEL,
    PANEL_W,
    PANEL_X,
    PICKUPS,
    WIN_H,
    WIN_W,
    WINDOW_BG_BOTTOM,
    WINDOW_BG_TOP,
    accent_for,
)


def _mix(a, b, t: float) -> tuple[int, int, int]:
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _clamp(color) -> tuple[int, int, int]:
    return tuple(max(0, min(255, int(c))) for c in color)


def _wrap(font: pygame.font.Font, text: str, width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        trial = word if not current else f"{current} {word}"
        if font.size(trial)[0] <= width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


class Renderer:
    def __init__(self, screen: pygame.Surface):
        self.screen = screen
        self.font = pygame.font.SysFont("Bahnschrift", 20)
        self.bold = pygame.font.SysFont("Bahnschrift", 22, bold=True)
        self.small = pygame.font.SysFont("Bahnschrift", 15)
        self.tiny = pygame.font.SysFont("Bahnschrift", 13)
        self.huge = pygame.font.SysFont("Bahnschrift", 76, bold=True)
        self.mid = pygame.font.SysFont("Bahnschrift", 34, bold=True)
        self.num = pygame.font.SysFont("Bahnschrift", 42, bold=True)
        self.bg = self._gradient()
        self.dots = self._dots()
        self.vignette = self._vignette()
        self.scrim = pygame.Surface((FIELD_W, FIELD_H), pygame.SRCALPHA)
        self.scrim.fill((5, 7, 14, 168))
        self.territory: pygame.Surface | None = None
        self.bloom: pygame.Surface | None = None
        self.paint_key = None
        self.after: list[tuple[float, float]] = []
        self.ox = 0
        self.oy = 0
        self.accent = (80, 220, 210)
        self.time = 0.0

    def begin(self, level: int, time: float, ox: int, oy: int) -> None:
        self.accent = accent_for(level)
        self.time = time
        self.ox = ox
        self.oy = oy

    def origin(self) -> tuple[int, int]:
        return FIELD_X + self.ox, FIELD_Y + self.oy

    def draw(self, world, state: str, best: int, banner: float, particles, floaters) -> None:
        screen = self.screen
        screen.blit(self.bg, (0, 0))
        self._panel_chrome()
        ox, oy = self.origin()
        clip = pygame.Rect(ox, oy, FIELD_W, FIELD_H)
        screen.set_clip(clip)
        pygame.draw.rect(screen, FIELD_BG, clip)
        screen.blit(self.dots, (ox, oy))
        self._sync_territory(world)
        if self.territory is not None:
            screen.blit(self.territory, (ox, oy))
        if self.bloom is not None:
            screen.blit(self.bloom, (ox, oy), special_flags=pygame.BLEND_ADD)
        self._glow(world)
        self._trail(world)
        self._pickups(world)
        self._balls(world)
        self._player(world)
        screen.blit(self.vignette, (ox, oy))
        self._particles(particles)
        self._floaters(floaters)
        if state == "title":
            self._title()
        elif state == "play" and banner > 0:
            self._banner(world, min(255, int(255 * min(1.0, banner))))
        elif state == "clear":
            self._center_card("SECTOR SECURED", "Enter for the next sector")
        elif state == "over":
            self._center_card("FIELD LOST", "Enter to try again")
        elif state == "pause":
            self._center_card("PAUSED", "Enter resumes    R restarts sector")
        screen.set_clip(None)
        self._frame()
        if state == "title":
            self._title_panel()
        else:
            self._hud(world, best, state)

    def _gradient(self) -> pygame.Surface:
        surf = pygame.Surface((WIN_W, WIN_H))
        for y in range(WIN_H):
            t = y / max(1, WIN_H - 1)
            surf.fill(_mix(WINDOW_BG_TOP, WINDOW_BG_BOTTOM, t), (0, y, WIN_W, 1))
        return surf

    def _dots(self) -> pygame.Surface:
        surf = pygame.Surface((FIELD_W, FIELD_H), pygame.SRCALPHA)
        for y in range(ROWS_SAFE()):
            for x in range(COLS_SAFE()):
                if (x + y) % 2:
                    continue
                pygame.draw.circle(
                    surf,
                    (160, 190, 230, 48),
                    (x * CELL + CELL // 2, y * CELL + CELL // 2),
                    1,
                )
        return surf

    def _vignette(self) -> pygame.Surface:
        surf = pygame.Surface((FIELD_W, FIELD_H), pygame.SRCALPHA)
        for i in range(42):
            fade = (1 - i / 42) ** 2
            alpha = int(78 * fade)
            pygame.draw.rect(
                surf,
                (0, 0, 0, alpha),
                (i, i, FIELD_W - 2 * i, FIELD_H - 2 * i),
                1,
            )
        return surf

    def _sync_territory(self, world) -> None:
        board = world.board
        key = (board.filled_count, self.accent, board.cols, board.rows)
        if not board.territory_dirty and self.paint_key == key and self.territory is not None:
            return
        board.territory_dirty = False
        self.paint_key = key
        low = pygame.Surface((board.cols, board.rows))
        pixels = pygame.PixelArray(low)
        accent = self.accent
        body = tuple(max(1, int(c * 0.74)) for c in accent)
        rim = tuple(min(255, int(c * 0.74) + 64) for c in accent)
        grid = board.grid
        for y in range(board.rows):
            row = grid[y]
            for x in range(board.cols):
                if row[x] != 1:
                    pixels[x, y] = (0, 0, 0)
                    continue
                lift = ((x * 13 + y * 7) % 5) - 2
                color = _clamp(c + lift * 7 for c in body)
                edge = False
                for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                    if not board.in_bounds(nx, ny) or grid[ny][nx] != 1:
                        edge = True
                        break
                if edge:
                    color = _clamp(c + 18 for c in rim)
                if color == (0, 0, 0):
                    color = (1, 1, 1)
                pixels[x, y] = color
        del pixels
        territory = pygame.transform.scale(low, (FIELD_W, FIELD_H))
        territory.set_colorkey((0, 0, 0))
        self.territory = territory
        dimmed = low.copy()
        dimmed.fill((120, 120, 120), special_flags=pygame.BLEND_RGB_MULT)
        tiny = pygame.transform.smoothscale(dimmed, (FIELD_W // 7, FIELD_H // 7))
        self.bloom = pygame.transform.smoothscale(tiny, (FIELD_W, FIELD_H))

    def _glow(self, world) -> None:
        glow = pygame.Surface((FIELD_W // 2, FIELD_H // 2))

        def half(px: float, py: float) -> tuple[int, int]:
            return int(px / 2), int(py / 2)

        if world.building and world.trail:
            hot = world.nearest_threat() < 64
            color = (255, 70, 90) if hot else _mix(self.accent, (255, 255, 255), 0.35)
            for x, y in world.trail:
                pygame.draw.circle(glow, color, half((x + 0.5) * CELL, (y + 0.5) * CELL), 5)
        for ball in world.balls:
            color = _ball_color(ball.kind, self.accent)
            if ball.phased:
                color = _mix(color, (255, 255, 255), 0.45)
            pygame.draw.circle(glow, color, half(ball.x, ball.y), int(ball.visual / 1.4))
        cx, cy = world.render_pixel()
        pygame.draw.circle(glow, (255, 255, 255), half(cx, cy), 6)
        blurred = pygame.transform.smoothscale(glow, (FIELD_W, FIELD_H))
        self.screen.blit(blurred, self.origin(), special_flags=pygame.BLEND_ADD)

    def _trail(self, world) -> None:
        if world.building and world.trail:
            cells = world.ordered_trail()
            points = [self._grid(x, y) for x, y in cells]
            hot = world.nearest_threat() < 64
            outer = (255, 70, 88) if hot else self.accent
            for point in points:
                pygame.draw.circle(self.screen, outer, point, 7)
            if len(points) >= 2:
                pygame.draw.lines(self.screen, outer, False, points, 10)
                pygame.draw.lines(self.screen, (255, 255, 255), False, points, 3)
            return
        aim = world.aim_cells()
        if len(aim) < 2:
            return
        if world.horizontal:
            aim.sort(key=lambda cell: cell[0])
        else:
            aim.sort(key=lambda cell: cell[1])
        points = [self._grid(x, y) for x, y in aim]
        guide = _mix(self.accent, (255, 255, 255), 0.25)
        pygame.draw.lines(self.screen, guide, False, points, 2)

    def _pickups(self, world) -> None:
        for pickup in world.pickups:
            if pickup.life < 3.2 and int(self.time * 10) % 2 == 0:
                continue
            label, color, _hint = PICKUPS[pickup.kind]
            bob = math.sin(self.time * 3.2 + pickup.x) * 3
            sx, sy = self._grid(pickup.x, pickup.y)
            sy += bob
            pygame.draw.polygon(
                self.screen,
                color,
                [(sx, sy - 9), (sx + 8, sy), (sx, sy + 9), (sx - 8, sy)],
            )
            pygame.draw.polygon(
                self.screen,
                (255, 255, 255),
                [(sx, sy - 9), (sx + 8, sy), (sx, sy + 9), (sx - 8, sy)],
                1,
            )
            text = self.tiny.render(label, True, (12, 14, 20))
            self.screen.blit(text, text.get_rect(center=(sx, sy + 16)))

    def _balls(self, world) -> None:
        px, py = self._pix(*world.render_pixel())
        for ball in world.balls:
            if ball.kind == "bosco":
                self._shark(ball)
                continue
            color = _ball_color(ball.kind, self.accent)
            sx, sy = self._pix(ball.x, ball.y)
            halo = max(8, int(ball.visual))
            core = max(5, halo // 2)
            if ball.kind == "phantom" and ball.phased:
                wobble = 1 + math.sin(self.time * 16) * 0.12
                pygame.draw.circle(self.screen, color, (sx, sy), int(halo * wobble), 2)
                continue
            if ball.warning and int(self.time * 14) % 2 == 0:
                color = (255, 245, 255)
            pygame.draw.circle(self.screen, _mix(color, (0, 0, 0), 0.45), (sx, sy), halo)
            pygame.draw.circle(self.screen, color, (sx, sy), core + 2)
            pygame.draw.circle(self.screen, _mix(color, (255, 255, 255), 0.45), (sx, sy), core)
            pygame.draw.circle(
                self.screen,
                (255, 255, 255),
                (sx - core // 3, sy - core // 3),
                max(2, core // 3),
            )
            if ball.kind == "seeker":
                dx, dy = px - sx, py - sy
                mag = math.hypot(dx, dy) or 1
                eye = (int(sx + dx / mag * 3), int(sy + dy / mag * 3))
                pygame.draw.circle(self.screen, (250, 252, 255), (sx, sy), core + 1)
                pygame.draw.circle(self.screen, (255, 46, 72), (sx, sy), max(3, core // 2))
                pygame.draw.circle(self.screen, (16, 18, 28), eye, max(2, core // 3))
            elif ball.kind == "splitter":
                pygame.draw.circle(self.screen, (236, 255, 190), (sx, sy), core + 2, 2)

    def _shark(self, ball) -> None:
        sx, sy = self._pix(ball.x, ball.y)
        ang = math.atan2(ball.vy, ball.vx)
        body = [(22, 0), (-16, 11), (-9, 0), (-16, -11)]
        points = [self._spin(sx, sy, x, y, ang) for x, y in body]
        pygame.draw.polygon(self.screen, (255, 92, 48), points)
        pygame.draw.polygon(self.screen, (255, 214, 170), points, 1)
        ex, ey = self._spin(sx, sy, 8, 0, ang)
        pygame.draw.circle(self.screen, (255, 244, 220), (ex, ey), 2)

    def _player(self, world) -> None:
        sx, sy = self._pix(*world.render_pixel())
        if self.after:
            last = self.after[-1]
            if math.hypot(sx - last[0], sy - last[1]) > 80:
                self.after.clear()
        self.after.append((sx, sy))
        if len(self.after) > 6:
            self.after.pop(0)
        blinking = world.invuln > 0 and int(self.time * 18) % 2 == 0
        for i, (ax, ay) in enumerate(self.after[:-1]):
            fade = (i + 1) / len(self.after)
            pygame.draw.circle(self.screen, _mix((0, 0, 0), self.accent, fade * 0.7), (int(ax), int(ay)), 3)
        if blinking:
            return
        ang = 0.0 if world.horizontal else math.pi / 2
        # A bar with a muzzle pointing both ways.
        shape = [(20, 0), (7, 5), (7, 3), (-7, 3), (-7, 5), (-20, 0), (-7, -5), (-7, -3), (7, -3), (7, -5)]
        points = [self._spin(sx, sy, x, y, ang) for x, y in shape]
        fill = (255, 255, 255) if not world.building else (255, 244, 210)
        pygame.draw.polygon(self.screen, fill, points)
        pygame.draw.polygon(self.screen, self.accent if not world.building else (255, 90, 90), points, 2)
        pygame.draw.circle(self.screen, self.accent, (int(sx), int(sy)), 3)
        if world.shield:
            pulse = 16 + int(2 * math.sin(self.time * 9))
            pygame.draw.circle(self.screen, (120, 235, 255), (int(sx), int(sy)), pulse, 2)

    def _particles(self, particles) -> None:
        ox, oy = self.origin()
        for bit in particles:
            fade = max(0.0, bit.life / bit.max_life)
            color = _clamp(c * fade for c in bit.color)
            pygame.draw.circle(self.screen, color, (int(ox + bit.x), int(oy + bit.y)), max(1, int(bit.radius * fade)))

    def _floaters(self, floaters) -> None:
        ox, oy = self.origin()
        for floater in floaters:
            fade = max(0.0, min(1.0, floater.life / 0.35))
            image = self.bold.render(floater.text, True, floater.color)
            image.set_alpha(int(255 * fade))
            self.screen.blit(image, (ox + floater.x, oy + floater.y))

    def _title(self) -> None:
        ox, oy = self.origin()
        self.screen.blit(self.scrim, (ox, oy))
        word = self.huge.render("BARRACK", True, (244, 247, 255))
        neo = self.mid.render("NEO", True, self.accent)
        sub = self.small.render("Cut the field. Starve the swarm.", True, (196, 206, 224))
        prompt_on = math.sin(self.time * 4) > -0.15
        block_h = word.get_height() + neo.get_height() + 36
        y = oy + FIELD_H // 2 - block_h // 2
        self.screen.blit(word, word.get_rect(midtop=(ox + FIELD_W // 2, y)))
        self.screen.blit(neo, neo.get_rect(midtop=(ox + FIELD_W // 2, y + word.get_height() - 8)))
        self.screen.blit(sub, sub.get_rect(midtop=(ox + FIELD_W // 2, y + word.get_height() + neo.get_height() + 8)))
        if prompt_on:
            prompt = self.bold.render("ENTER TO PLAY", True, (255, 236, 180))
            self.screen.blit(prompt, prompt.get_rect(midtop=(ox + FIELD_W // 2, y + block_h + 8)))

    def _banner(self, world, alpha: int) -> None:
        ox, oy = self.origin()
        title = self.mid.render(f"SECTOR {world.level:02d}", True, (244, 247, 255))
        name = self.bold.render(world.spec.title.upper(), True, self.accent)
        title.set_alpha(alpha)
        name.set_alpha(alpha)
        self.screen.blit(title, title.get_rect(midtop=(ox + FIELD_W // 2, oy + 28)))
        self.screen.blit(name, name.get_rect(midtop=(ox + FIELD_W // 2, oy + 68)))

    def _center_card(self, title: str, sub: str) -> None:
        ox, oy = self.origin()
        dim = pygame.Surface((FIELD_W, FIELD_H), pygame.SRCALPHA)
        dim.fill((4, 6, 12, 140))
        self.screen.blit(dim, (ox, oy))
        head = self.mid.render(title, True, (244, 247, 255))
        body = self.small.render(sub, True, self.accent)
        self.screen.blit(head, head.get_rect(center=(ox + FIELD_W // 2, oy + FIELD_H // 2 - 12)))
        self.screen.blit(body, body.get_rect(center=(ox + FIELD_W // 2, oy + FIELD_H // 2 + 24)))

    def _frame(self) -> None:
        ox, oy = self.origin()
        outer = pygame.Rect(ox - 6, oy - 6, FIELD_W + 12, FIELD_H + 12)
        inner = pygame.Rect(ox - 1, oy - 1, FIELD_W + 2, FIELD_H + 2)
        dim = _mix(self.accent, (0, 0, 0), 0.55)
        pygame.draw.rect(self.screen, dim, outer, 2, border_radius=12)
        pygame.draw.rect(self.screen, self.accent, inner, 1, border_radius=8)

    def _panel_chrome(self) -> None:
        rect = pygame.Rect(PANEL_X - 8, 16, PANEL_W + 16, WIN_H - 32)
        pygame.draw.rect(self.screen, (10, 14, 24), rect, border_radius=16)
        pygame.draw.rect(self.screen, (32, 42, 64), rect, 1, border_radius=16)

    def _title_panel(self) -> None:
        x = PANEL_X + 8
        y = 36
        y = self._label(x, y, "HOW TO PLAY", self.accent)
        rules = [
            "Move the blaster through open field.",
            "Fire to shoot a wall out both ends.",
            "It grows until it hits the border or a line.",
            "Empty pockets fill. Occupied ones stay.",
            "A ball on you, or on a growing line, costs a life.",
            "Gems speed the line or slow the swarm.",
        ]
        for rule in rules:
            for line in _wrap(self.small, rule, PANEL_W - 24):
                y = self._text(x, y, line, (206, 214, 230), self.small)
            y += 6
        y += 8
        y = self._label(x, y, "CONTROLS", self.accent)
        for line in ("WASD or arrows to move", "Move the mouse to place it too", "Click or Space to fire", "Right click or Q to rotate", "Esc pauses"):
            y = self._text(x, y, line, (206, 214, 230), self.small)
        credit = self.tiny.render("Inspired by Barrack, Ambrosia 1996", True, (120, 132, 156))
        self.screen.blit(credit, (x, WIN_H - 48))

    def _hud(self, world, best: int, state: str) -> None:
        x = PANEL_X + 8
        y = 32
        y = self._label(x, y, "BARRACK NEO", self.accent)
        y = self._text(x, y, f"SECTOR {world.level:02d}   {world.spec.title.upper()}", (230, 236, 248), self.bold)
        y += 6
        y = self._text(x, y, "SCORE", (130, 142, 166), self.tiny)
        y = self._text(x, y - 4, f"{world.score:,}", (255, 226, 140), self.num)
        y = self._text(x, y, f"BEST  {best:,}", (150, 162, 186), self.small)
        y += 4
        y = self._lives(x, y, world.lives)
        y += 8
        ratio = world.claim_ratio()
        quota = world.quota
        done = ratio + 1e-6 >= quota
        y = self._text(x, y, "CLAIMED", (130, 142, 166), self.tiny)
        percent_color = (255, 220, 120) if done else (236, 242, 252)
        y = self._text(x, y - 6, f"{ratio * 100:.0f}%", percent_color, self.num)
        self._bar(x, y, ratio, quota)
        y += 28
        y = self._text(x, y, f"QUOTA {quota * 100:.0f}%", self.accent if not done else (255, 220, 120), self.small)
        if world.combo >= 2:
            y = self._text(x, y, f"CHAIN x{world.combo}", (255, 196, 96), self.bold)
        y = self._effects(x, y, world)
        y += 6
        y = self._label(x, y, "SWARM", self.accent)
        roster = world.roster()
        if not roster:
            y = self._text(x, y, "Clear", (150, 162, 186), self.small)
        for name, count in roster:
            color = _ball_color(name, self.accent)
            pygame.draw.circle(self.screen, color, (x + 6, y + 8), 5)
            y = self._text(x + 18, y, f"{KIND_LABEL.get(name, name)}  {count}", (220, 226, 240), self.small)
        y += 8
        for line in _wrap(self.small, world.spec.hint, PANEL_W - 28):
            y = self._text(x, y, line, (168, 180, 204), self.small)
        foot = WIN_H - 78
        self._text(x, foot, "WASD or mouse    Click / Space fires", (130, 142, 166), self.tiny)
        extra = "Right click rotates    R restarts" if state == "pause" else "Right click or Q rotates"
        self._text(x, foot + 18, extra, (130, 142, 166), self.tiny)

    def _effects(self, x: int, y: int, world) -> int:
        active = []
        if world.shield:
            active.append(("SHIELD", PICKUPS["shield"][1], None))
        if world.haste > 0:
            active.append(("LINE", PICKUPS["haste"][1], world.haste))
        if world.freeze > 0:
            active.append(("FREEZE", PICKUPS["freeze"][1], world.freeze))
        if world.slow > 0:
            active.append(("SLOW", PICKUPS["slow"][1], world.slow))
        if world.mult > 0:
            active.append(("x2", PICKUPS["mult"][1], world.mult))
        if not active:
            return y
        cursor = x
        for label, color, timer in active:
            text = label if timer is None else f"{label} {timer:.0f}"
            image = self.tiny.render(text, True, (16, 18, 28))
            width = image.get_width() + 12
            if cursor + width > PANEL_X + PANEL_W - 8:
                cursor = x
                y += 22
            pygame.draw.rect(self.screen, color, (cursor, y, width, 18), border_radius=8)
            self.screen.blit(image, (cursor + 6, y + 2))
            cursor += width + 6
        return y + 26

    def _bar(self, x: int, y: int, ratio: float, quota: float) -> None:
        width = PANEL_W - 28
        pygame.draw.rect(self.screen, (22, 28, 44), (x, y, width, 12), border_radius=6)
        fill = int(width * max(0.0, min(1.0, ratio)))
        if fill > 0:
            color = (255, 206, 96) if ratio >= quota else self.accent
            pygame.draw.rect(self.screen, color, (x, y, fill, 12), border_radius=6)
        mark = x + int(width * quota)
        pygame.draw.line(self.screen, (255, 255, 255), (mark, y - 3), (mark, y + 15), 2)

    def _lives(self, x: int, y: int, lives: int) -> int:
        for i in range(6):
            color = self.accent if i < lives else (36, 44, 64)
            cx = x + 10 + i * 22
            cy = y + 8
            pygame.draw.polygon(self.screen, color, [(cx, cy - 7), (cx + 6, cy), (cx, cy + 7), (cx - 6, cy)])
        return y + 22

    def _label(self, x: int, y: int, text: str, color) -> int:
        return self._text(x, y, text, color, self.tiny)

    def _text(self, x: int, y: int, text: str, color, font) -> int:
        image = font.render(text, True, color)
        self.screen.blit(image, (x, y))
        return y + image.get_height() + 2

    def _grid(self, cx: float, cy: float) -> tuple[int, int]:
        ox, oy = self.origin()
        return int(ox + (cx + 0.5) * CELL), int(oy + (cy + 0.5) * CELL)

    def _pix(self, px: float, py: float) -> tuple[int, int]:
        ox, oy = self.origin()
        return int(ox + px), int(oy + py)

    def _spin(self, sx: float, sy: float, x: float, y: float, ang: float) -> tuple[int, int]:
        rx = x * math.cos(ang) - y * math.sin(ang)
        ry = x * math.sin(ang) + y * math.cos(ang)
        return int(sx + rx), int(sy + ry)


def _ball_color(kind: str, accent) -> tuple[int, int, int]:
    if kind == "seeker":
        return (255, 70, 90)
    if kind == "splitter":
        return (186, 240, 90)
    if kind == "phantom":
        return (206, 140, 255)
    if kind == "bosco":
        return (255, 96, 52)
    return _mix(accent, (180, 230, 255), 0.55)


def ROWS_SAFE() -> int:
    return FIELD_H // CELL


def COLS_SAFE() -> int:
    return FIELD_W // CELL
