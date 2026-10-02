"""Short synthesized stingers. The game still runs if audio cannot start."""

import array
import math
import random

import pygame


def _tone(freq: float, ms: int, volume: float = 0.22, slide: float = 0.0) -> pygame.mixer.Sound:
    rate = 22050
    count = int(rate * ms / 1000)
    buf = array.array("h")
    for i in range(count):
        t = i / rate
        env = 1.0 - i / count
        f = freq + slide * (i / count)
        sample = int(volume * 32767 * env * math.sin(2 * math.pi * f * t))
        buf.append(sample)
    return pygame.mixer.Sound(buffer=buf.tobytes())


def _noise(ms: int, volume: float = 0.28) -> pygame.mixer.Sound:
    rate = 22050
    count = int(rate * ms / 1000)
    rng = random.Random(7)
    buf = array.array("h")
    for i in range(count):
        env = (1.0 - i / count) ** 2
        sample = int(volume * 32767 * env * rng.uniform(-1, 1))
        buf.append(sample)
    return pygame.mixer.Sound(buffer=buf.tobytes())


def _chord(freqs: tuple[float, ...], ms: int, volume: float = 0.14) -> pygame.mixer.Sound:
    rate = 22050
    count = int(rate * ms / 1000)
    buf = array.array("h")
    for i in range(count):
        t = i / rate
        env = 1.0 - i / count
        wave = sum(math.sin(2 * math.pi * freq * t) for freq in freqs) / len(freqs)
        buf.append(int(volume * 32767 * env * wave))
    return pygame.mixer.Sound(buffer=buf.tobytes())


class Audio:
    def __init__(self) -> None:
        self.ok = False
        self.sounds: dict[str, pygame.mixer.Sound] = {}
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(22050, -16, 1, 512)
            self.sounds = {
                "dive": _tone(720, 45, 0.12),
                "cancel": _tone(280, 50, 0.1, slide=-80),
                "capture": _chord((523, 659, 784), 140, 0.16),
                "capture_big": _chord((523, 659, 784, 1046), 240, 0.18),
                "hurt": _noise(180, 0.32),
                "shield": _tone(980, 90, 0.16, slide=200),
                "power": _chord((880, 1320), 120, 0.15),
                "clear": _chord((523, 659, 784, 1046), 420, 0.18),
                "life": _tone(880, 80, 0.14, slide=220),
                "split": _tone(180, 90, 0.16, slide=40),
            }
            self.ok = True
        except (pygame.error, OSError):
            self.ok = False

    def play(self, name: str) -> None:
        sound = self.sounds.get(name)
        if self.ok and sound is not None:
            sound.play()
