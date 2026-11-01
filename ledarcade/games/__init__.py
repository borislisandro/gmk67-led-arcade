from .base import Game
from .echo import Echo
from .lightsout import LightsOut
from .minesweeper import Minesweeper
from .ripple import Ripple
from .snake import Snake
from .whack import Whack

GAMES: dict[str, type[Game]] = {g.name: g for g in (Snake, Minesweeper, Whack, Echo, LightsOut, Ripple)}

__all__ = ["GAMES", "Game"]
