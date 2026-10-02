# BarrackNeo

A modern take on the 1996 Ambrosia game Barrack by Greg Lovette. You ride the rim of a dark sector, dive in, and draw a line through a swarm of balls. When the line reconnects, every pocket with no enemy in it fills in. Fill the quota and the sector is yours.

Bosco patrols the rim and will run down your line. Eyes chase the cut. Splitters divide after a big claim. Phantoms ghost through walls, then turn solid again. Gems in the open are power-ups: draw through one, or fill the pocket it sits in.

This is an independent homage. It is not made by or affiliated with Ambrosia Software.

## Run

```
pip install -r requirements.txt
python main.py
```

Python 3.11 or newer. The window is local. No account and no network once pygame is installed.

## Controls

| Action | Keys |
| --- | --- |
| Move and draw | Arrow keys or WASD |
| Steer | Hold the left mouse button |
| Erase the line | Backtrack along it |
| Pause | Esc |
| Restart the sector | R, while paused |
| Start, continue, confirm | Enter |

You are safe on the rim. You are not safe on the line.

## Checks

```
python -m barrackneo.selftest
```
