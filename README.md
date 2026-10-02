# BarrackNeo

A modern take on the 1996 Ambrosia game Barrack by Greg Lovette. You fly a blaster through an open sector. Fire, and a wall shoots out both ends in a straight line. It grows until each end hits the border or a wall you already built, then every pocket with no enemy in it fills in. Fill the quota and the sector is yours.

Balls, eyes, and Bosco hunt the blaster and the line while it is still growing. A touch costs a life and the unfinished wall comes down. Splitters divide after a big claim. Phantoms ghost through walls, then turn solid again. Gems in the open slow the swarm, speed the line while it builds, or shield the blaster.

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
| Move | WASD, arrow keys, or moving the mouse |
| Fire both ways | Left click or Space |
| Rotate 90 degrees | Right click, mouse wheel, Q, or F |
| Pause | Esc |
| Restart the sector | R, while paused |
| Start, continue, confirm | Enter or Space |

You can sit anywhere in the open. A ball that hits the blaster, or the line while it is still building, costs a life.

## Checks

```
python -m barrackneo.selftest
```
