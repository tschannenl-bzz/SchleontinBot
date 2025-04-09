from dataclasses import dataclass
from enum import Enum


class CardType(Enum):
    EXPLODING_KITTEN = "Exploding Kitten"
    DEFUSE = "Defuse"
    SKIP = "Skip"
    # ATTACK = "Attack"
    SEE_THE_FUTURE = "See the Future"
    NORMAL = "Normal"
    SHUFFLE = "Shuffle"


@dataclass
class CardCounts:
    EXPLODING_KITTEN: int
    DEFUSE: int
    SKIP: int
    # ATTACK: int
    SEE_THE_FUTURE: int
    NORMAL: int
    SHUFFLE: int

@dataclass
class Card:
    card_type: CardType