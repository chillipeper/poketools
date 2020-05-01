from enum import Enum


class Version(Enum):
    COLOSSEUM = 'colosseum'
    XD = 'xd'


type_map = {
    0x00: 'normal',
    0x01: 'fighting',
    0x02: 'flying',
    0x03: 'poison',
    0x04: 'ground',
    0x05: 'rock',
    0x06: 'bug',
    0x07: 'ghost',
    0x08: 'steel',
    0x09: 'unknown',
    0x0A: 'fire',
    0x0B: 'water',
    0x0C: 'grass',
    0x0D: 'electric',
    0x0E: 'psychic',
    0x0F: 'ice',
    0x10: 'dragon',
    0x11: 'dark',
}

move_name_changes = {
    'ancientpower': 'ancient-power',
    'bubblebeam': 'bubble-beam',
    'doubleslap': 'double-slap',
    'dragonbreath': 'dragon-breath',
    'dynamicpunch': 'dynamic-punch',
    'extremespeed': 'extreme-speed',
    'faint-attack': 'feint-attack',
    'featherdance': 'feather-dance',
    'grasswhistle': 'grass-whistle',
    'hi-jump-kick': 'high-jump-kick',
    'poisonpowder': 'poison-powder',
    'selfdestruct': 'self-destruct',
    'smellingsalt': 'smelling-salts',
    'softboiled': 'soft-boiled',
    'solarbeam': 'solar-beam',
    'sonicboom': 'sonic-boom',
    'thunderpunch': 'thunder-punch',
    'thundershock': 'thunder-shock',
    'vicegrip': 'vice-grip',
}
