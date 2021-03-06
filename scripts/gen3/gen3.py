import argparse
import csv
from dataclasses import dataclass
import io
from io import BufferedReader
import os
import struct
import sys
from typing import Any, Dict, List

from flags import Flags
import progressbar
from slugify import slugify

from gen3 import script
from gen3.enums import Version, VersionGroup
from inc import gba, group_by_version_group, group_pokemon, pokemon_text
from inc.yaml import yaml

pokemon_text.register()

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


def get_moves(rom: BufferedReader, version_group: VersionGroup, version: Version):
    num_moves = 355
    num_contest_effects = 48
    out_moves = {}
    out_contest_effects = {}
    move_slugs = {}

    print('Dumping moves')

    def _get_move_names():
        name_length = 13
        names_offset = {
            Version.RUBY: 0x1F8338,
            Version.SAPPHIRE: 0x1F82C8,
            Version.EMERALD: 0x31977C,
            Version.FIRERED: 0x247094,
            Version.LEAFGREEN: 0x247070
        }
        names_offset = names_offset[version]

        # This will skip the dummy move 0
        for move_id in range(1, num_moves):
            rom.seek(names_offset + (move_id * name_length))
            name = bytearray()
            while rom.peek(1)[0] != 0xFF and len(name) < name_length:
                name.append(rom.read(1)[0])
            name = name.decode('pokemon_gen3')
            slug = slugify(name)
            move_slugs[move_id] = slug
            out_moves[slug] = {
                'name': name,
            }

    def _get_move_data():
        target_map = {
            0: 'selected-pokemon',
            1 << 0: 'specific-move',
            1 << 2: 'random-opponent',
            1 << 3: 'all-opponents',
            1 << 4: 'user',
            1 << 5: 'all-other-pokemon',
            1 << 6: 'opponents-field',
        }

        class MoveFlags(Flags):
            CONTACT = 1 << 0, 'contact'
            PROTECT = 1 << 1, 'protect'
            REFLECTABLE = 1 << 2, 'reflectable'
            SNATCH = 1 << 3, 'snatch'
            MIRROR = 1 << 4, 'mirror'
            KINGS_ROCK = 1 << 5, 'kings-rock'

        data_length = 9
        data_length_aligned = 12
        data_offset = {
            Version.RUBY: 0x1FB144,
            Version.SAPPHIRE: 0x1FB0D4,
            Version.EMERALD: 0x31C898,
            Version.FIRERED: 0x250C04,
            Version.LEAFGREEN: 0x250BE0,
        }
        data_offset = data_offset[version]

        @dataclass()
        class MoveStats:
            def __init__(self, data: bytes):
                data = struct.unpack('<BBBBBBBbB', data)
                self.effectId = data[0] + 1
                self.power = data[1]
                self.type = type_map[data[2]]
                self.accuracy = data[3]
                self.pp = data[4]
                self.effectChance = data[5]
                self.target = target_map[data[6]]
                self.priority = data[7]
                self.flags = [flag.data for flag in MoveFlags(data[8])]

                pass

        for move_id, move_slug in move_slugs.items():
            rom.seek(data_offset + (move_id * data_length_aligned))
            data = rom.read(data_length)
            move_stats = MoveStats(data)
            out_moves[move_slug].update({
                'power': move_stats.power,
                'type': move_stats.type,
                'accuracy': move_stats.accuracy,
                'pp': move_stats.pp,
                'effect': move_stats.effectId,
                'target': move_stats.target,
                'priority': move_stats.priority,
            })
            if 0 < move_stats.effectChance < 100:
                out_moves[move_slug]['effect_chance'] = move_stats.effectChance
            if out_moves[move_slug]['power'] == 0:
                del out_moves[move_slug]['power']
            if out_moves[move_slug]['accuracy'] == 0:
                del out_moves[move_slug]['accuracy']
            if len(move_stats.flags) > 0:
                out_moves[move_slug]['flags'] = move_stats.flags

    def _pullup_data():
        pullup_keys = [
            'crit_rate_bonus',
            'drain',
            'flinch_chance',
            'ailment',
            'ailment_chance',
            'recoil',
            'healing',
            'categories',
            'hits',
            'turns',
            'stat_changes',
            'stat_change_chance',
        ]
        print('Using existing data')
        for move_slug in progressbar.progressbar(move_slugs.values()):
            if move_slug in move_name_changes:
                yaml_path = os.path.join(args.out_moves, '{move}.yaml'.format(move=move_name_changes[move_slug]))
            else:
                yaml_path = os.path.join(args.out_moves, '{move}.yaml'.format(move=move_slug))
            with open(yaml_path, 'r') as move_yaml:
                old_move_data = yaml.load(move_yaml.read())
                if version_group.value not in old_move_data:
                    # If the name has changed, try the original name, as it may have been moved already.
                    if move_slug in move_name_changes:
                        yaml_path = os.path.join(args.out_moves, '{move}.yaml'.format(move=move_slug))
                        with open(yaml_path, 'r') as move_yaml:
                            old_move_data = yaml.load(move_yaml.read())
                    else:
                        raise Exception(
                            'Move {move} has no data for version group {version_group}.'.format(
                                move=move_slug,
                                version_group=version_group.value))
                for key in pullup_keys:
                    if key in old_move_data[version_group.value]:
                        out_moves[move_slug][key] = old_move_data[version_group.value][key]

    def _get_contest_move_data():
        contest_type_map = {
            0x00: 'cool',
            0x01: 'beauty',
            0x02: 'cute',
            0x03: 'smart',
            0x04: 'tough',
        }
        data_offset = {
            Version.RUBY: 0x3CF5B0,
            Version.SAPPHIRE: 0x3CF60C,
            Version.EMERALD: 0x58C2B4,
        }
        if version not in data_offset:
            # Skip versions without contests
            return
        data_offset = data_offset[version]
        data_length = 7
        data_length_aligned = 8

        @dataclass
        class ContestMove:
            def __init__(self, data: bytes):
                data = struct.unpack('<BBB4B', data)
                self.effectId = data[0] + 1
                self.contestType = contest_type_map[data[1] & 0x07]
                self.comboStarterId = data[2]
                if self.comboStarterId == 0:
                    self.comboStarterId = None
                self.comboMoves = []
                for combo_move in data[3:7]:
                    if combo_move != 0:
                        self.comboMoves.append(combo_move)

        # First pass - contest base data
        move_combo_starters = {}
        move_combo_members = {}
        contest_data = {}
        for move_id, move_slug in move_slugs.items():
            rom.seek(data_offset + (move_id * data_length_aligned))
            data = rom.read(data_length)
            contest_move = ContestMove(data)
            contest_data[move_slug] = contest_move

            out_moves[move_slug].update({
                'contest_type': contest_move.contestType,
                'contest_effect': contest_move.effectId,
            })
            if contest_move.comboStarterId:
                move_combo_starters[contest_move.comboStarterId] = move_slug
            for combo_move in contest_move.comboMoves:
                if combo_move not in move_combo_members:
                    move_combo_members[combo_move] = []
                move_combo_members[combo_move].append(move_slug)

        # Second pass - assemble the combos
        for move_slug, contest_move in contest_data.items():
            if contest_move.comboStarterId:
                # This is the "before move"
                if 'contest_use_before' not in out_moves[move_slug]:
                    out_moves[move_slug]['contest_use_before'] = []
                out_moves[move_slug]['contest_use_before'].extend(move_combo_members[contest_move.comboStarterId])
            for combo_move in contest_move.comboMoves:
                # This is an "after move"
                if 'contest_use_after' not in out_moves[move_slug]:
                    out_moves[move_slug]['contest_use_after'] = []
                out_moves[move_slug]['contest_use_after'].append(move_combo_starters[combo_move])

    def _get_contest_effect_data():
        effect_type_map = {
            0x00: 'constant-appeal',
            0x01: 'prevent-startle',
            0x02: 'startles-last-appealer',
            0x03: 'startles-previous-appealers',
            0x04: 'affects-other-appealers',
            0x05: 'special',
            0x06: 'change-order',
        }
        data_offset = {
            Version.RUBY: 0x3D00C8,
            Version.SAPPHIRE: 0x3D0124,
            Version.EMERALD: 0x58CDCC,
        }
        if version not in data_offset:
            # Skip versions without contests
            return
        data_offset = data_offset[version]
        data_length = 3
        data_length_aligned = 4

        @dataclass()
        class ContestEffect:
            def __init__(self, data: bytes):
                data = struct.unpack('<BBB', data)
                self.effectType = effect_type_map[data[0]]
                self.appeal = data[1] // 10
                self.jam = data[2] // 10

        for effect_id in range(1, num_contest_effects + 1):
            rom.seek(data_offset + ((effect_id - 1) * data_length_aligned))
            data = rom.read(data_length)
            contest_effect = ContestEffect(data)
            out_contest_effects[effect_id] = {
                'category': contest_effect.effectType,
                'appeal': contest_effect.appeal,
                'jam': contest_effect.jam,
            }

    def _get_contest_flavor():
        flavor_offset = {
            Version.RUBY: 0x3CA508,
            Version.SAPPHIRE: 0x3CA564,
            Version.EMERALD: 0x27CB82,
        }
        if version not in flavor_offset:
            # Skip versions without contests
            return
        data_offset = flavor_offset[version]

        rom.seek(data_offset)
        for effect_id in range(1, num_contest_effects + 1):
            flavor_text = bytearray()
            while rom.peek(1)[0] != 0xFF:
                flavor_text.append(rom.read(1)[0])
            rom.seek(1, io.SEEK_CUR)
            flavor_text = flavor_text.decode('pokemon_gen3')
            out_contest_effects[effect_id]['flavor_text'] = flavor_text

    def _get_flavor():
        flavor_offset = {
            Version.RUBY: 0x3BC69C,
            Version.SAPPHIRE: 0x3BC6F8,
            Version.EMERALD: 0x6181c1,
            Version.FIRERED: 0x482834,
            Version.LEAFGREEN: 0x482110,
        }
        flavor_offset = flavor_offset[version]
        rom.seek(flavor_offset)
        for move_slug in move_slugs.values():
            flavor_text = bytearray()
            while rom.peek(1)[0] != 0xFF:
                flavor_text.append(rom.read(1)[0])
            flavor_text = flavor_text.decode('pokemon_gen3')
            out_moves[move_slug]['flavor_text'] = flavor_text
            rom.seek(1, io.SEEK_CUR)

    _get_move_names()
    _get_move_data()
    _pullup_data()
    _get_contest_move_data()
    _get_contest_effect_data()
    _get_contest_flavor()
    _get_flavor()

    return out_moves, out_contest_effects, move_slugs


def write_moves(out):
    print('Writing Moves')
    used_version_groups = set()
    for move_slug, move_data in progressbar.progressbar(out.items()):
        yaml_path = os.path.join(args.out_moves, '{slug}.yaml'.format(slug=move_slug))
        try:
            with open(yaml_path, 'r') as move_yaml:
                data = yaml.load(move_yaml.read())
        except IOError:
            data = {}
        data.update(move_data)
        used_version_groups.update(move_data.keys())
        with open(yaml_path, 'w') as move_yaml:
            yaml.dump(data, move_yaml)

    # Remove this version group's data from the new name file
    for old_name, new_name in move_name_changes.items():
        yaml_path = os.path.join(args.out_moves, '{slug}.yaml'.format(slug=new_name))
        with open(yaml_path, 'r') as move_yaml:
            data = yaml.load(move_yaml.read())
        changed = False
        for check_version_group in used_version_groups:
            try:
                del data[check_version_group]
                changed = True
            except KeyError:
                # No need to re-write this file
                continue
        if changed:
            with open(yaml_path, 'w') as move_yaml:
                yaml.dump(data, move_yaml)


def write_contest_effects(out):
    print('Writing Contest Effects')
    for effect_id, effect_data in progressbar.progressbar(out.items()):
        yaml_path = os.path.join(args.out_contest_effects, '{slug}.yaml'.format(slug=effect_id))
        try:
            with open(yaml_path, 'r') as effect_yaml:
                data = yaml.load(effect_yaml.read())
        except IOError:
            data = {}
        data.update(effect_data)
        with open(yaml_path, 'w') as effect_yaml:
            yaml.dump(data, effect_yaml)


item_name_changes = {
    'blackglasses': 'black-glasses',
    'brightpowder': 'bright-powder',
    'deepseatooth': 'deep-sea-tooth',
    'deepseascale': 'deep-sea-scale',
    'energypowder': 'energy-powder',
    'nevermeltice': 'never-melt-ice',
    'parlyz-heal': 'paralyze-heal',
    'silverpowder': 'silver-powder',
    'x-defend': 'x-defense',
    'x-special': 'x-sp-atk',
    'thunderstone': 'thunder-stone',
    'tinymushroom': 'tiny-mushroom',
    'twistedspoon': 'twisted-spoon',
}


def get_items(rom: BufferedReader, version_group: VersionGroup, version: Version):
    num_items = {
        VersionGroup.RUBY_SAPPHIRE: 349,
        VersionGroup.EMERALD: 377,
        VersionGroup.FIRERED_LEAFGREEN: 375,
    }
    num_items = num_items[version_group]

    out = {}
    item_slugs = {}

    print('Dumping items')

    def _get_item_data():
        slug_overrides = {
            'king-s-rock': 'kings-rock',
            'oak-s-parcel': 'oaks-parcel',
            's-s-ticket': 'ss-ticket',
        }
        # This is the start of every game having every key item from the games before it, so lots of exclusions.
        skip_items = {
            VersionGroup.RUBY_SAPPHIRE: ['pokeblock'],
            VersionGroup.EMERALD: [
                'pokeblock',
                'contest-pass',
                'oaks-parcel',
                'poke-flute',
                'secret-key',
                'bike-voucher',
                'gold-teeth',
                'old-amber',
                'card-key',
                'lift-key',
                'helix-fossil',
                'dome-fossil',
                'silph-scope',
                'bicycle',
                'town-map',
                'vs-seeker',
                'fame-checker',
                'tm-case',
                'berry-pouch',
                'teachy-tv',
                'tri-pass',
                'rainbow-pass',
                'tea',
                'powder-jar',
                'ruby',
                'sapphire',
            ],
            VersionGroup.FIRERED_LEAFGREEN: [
                'pokeblock',
                'shoal-salt',
                'shoal-shell',
                'red-scarf',
                'blue-scarf',
                'pink-scarf',
                'green-scarf',
                'yellow-scarf',
                'mach-bike',
                'contest-pass',
                'wailmer-pail',
                'devon-goods',
                'soot-sack',
                'basement-key',
                'acro-bike',
                'pokeblock-case',
                'letter',
                'eon-ticket',
                'red-orb',
                'blue-orb',
                'scanner',
                'go-goggles',
                'rm-1-key',
                'rm-2-key',
                'rm-4-key',
                'rm-6-key',
                'storage-key',
                'root-fossil',
                'claw-fossil',
                'devon-scope',
                'magma-emblem',
                'old-sea-map',
            ],
        }
        data_offset = {
            Version.RUBY: 0x3C5580,
            Version.SAPPHIRE: 0x3C55DC,
            Version.EMERALD: 0x5839A0,
            Version.FIRERED: 0x3DB028,
            Version.LEAFGREEN: 0x3DAE64,
        }
        data_offset = data_offset[version]
        data_length = 38
        data_length_aligned = 44
        if version_group == VersionGroup.FIRERED_LEAFGREEN:
            pocket_map = {
                0x01: 'misc',
                0x02: 'key',
                0x03: 'pokeballs',
                0x04: 'machines',
                0x05: 'berries',
            }
        else:
            pocket_map = {
                0x01: 'misc',
                0x02: 'pokeballs',
                0x03: 'machines',
                0x04: 'berries',
                0x05: 'key',
            }

        @dataclass()
        class ItemData:
            def __init__(self, data: bytes):
                data = struct.unpack('<14sHHBB4sB?BB4sB4sB', data)
                self.name = data[0].decode('pokemon_gen3').strip()
                self.itemId = data[1]
                self.price = data[2]
                self.holdEffect = data[3]
                self.holdEffectParam = data[4]
                self.descriptionPointer = data[5]
                self.importance = data[6]
                self.exitsBagOnUse = data[7]
                self.pocket = pocket_map[data[8]]
                self.type = data[9]
                self.battleUsage = data[11]
                self.secondaryId = data[13]

        for item_id in range(0, num_items):
            rom.seek(data_offset + (item_id * data_length_aligned))
            data = rom.read(data_length)
            item_stats = ItemData(data)
            if item_stats.itemId == 0:
                # Dummy item
                continue
            slug = slugify(item_stats.name)
            if slug in slug_overrides:
                slug = slug_overrides[slug]
            # Use the new name for the icon, if applicable
            icon = '{slug}.png'.format(slug=slug)
            if slug in item_name_changes:
                icon = '{slug}.png'.format(slug=item_name_changes[slug])
            if slug in skip_items[version_group]:
                continue
            item_slugs[item_id] = slug

            out[slug] = {
                'name': item_stats.name,
                'category': None,
                'pocket': item_stats.pocket,
                'flags': [],
                'icon': icon,
            }
            if item_stats.price > 0:
                out[slug].update({
                    'buy': item_stats.price,
                    'sell': item_stats.price // 2,
                })
            rom.seek(gba.address_from_pointer(item_stats.descriptionPointer))
            description = bytearray()
            while rom.peek(1)[0] != 0xFF:
                description.append(rom.read(1)[0])
            description = description.decode('pokemon_gen3')
            out[slug]['flavor_text'] = description

    def _pullup_data():
        pullup_keys = [
            'category',
            'flags',
            'short_description',
            'description',
        ]
        print('Using existing data')
        for item_slug in progressbar.progressbar(item_slugs.values()):
            if item_slug in item_name_changes:
                yaml_path = os.path.join(args.out_items, '{item}.yaml'.format(item=item_name_changes[item_slug]))
            else:
                yaml_path = os.path.join(args.out_items, '{item}.yaml'.format(item=item_slug))
            with open(yaml_path, 'r') as item_yaml:
                old_item_data = yaml.load(item_yaml.read())
                if version_group.value not in old_item_data:
                    # If the name has changed, try the original name, as it may have been moved already.
                    if item_slug in item_name_changes:
                        yaml_path = os.path.join(args.out_items, '{item}.yaml'.format(item=item_slug))
                        with open(yaml_path, 'r') as item_yaml:
                            old_item_data = yaml.load(item_yaml.read())
                    else:
                        raise Exception(
                            'Item {item} has no data for version group {version_group}.'.format(
                                item=item_slug,
                                version_group=version_group.value))
                for key in pullup_keys:
                    if key in old_item_data[version_group.value]:
                        out[item_slug][key] = old_item_data[version_group.value][key]

    _get_item_data()
    _pullup_data()

    return out, item_slugs


def update_machines(rom: BufferedReader, version: Version, items: dict, move_slugs: dict, moves: dict):
    machine_count = {
        'TM': 50,
        'HM': 8,
    }
    machine_table_offset = {
        Version.RUBY: 0x37651C,
        Version.SAPPHIRE: 0x3764AC,
        Version.EMERALD: 0x615B94,
        Version.FIRERED: 0x45A5A4,
        Version.LEAFGREEN: 0x459FC4,
    }
    machine_table_offset = machine_table_offset[version]

    print('Dumping TM/HM data')

    def _update_machine_item(type: str, number: int, move_id: int):
        item_slug = '{type}{number:02}'.format(type=type.lower(), number=number)
        move_slug = move_slugs[move_id]
        move_type = moves[move_slug]['type']
        items[item_slug].update({
            'machine': {
                'type': type.upper(),
                'number': number,
                'move': move_slug,
            },
            # Machine icons are by type, not item
            'icon': '{type}-{move_type}.png'.format(type=type.lower(), move_type=move_type)
        })

    rom.seek(machine_table_offset)
    for machine_type, num_machines in machine_count.items():
        for machine_number in range(1, num_machines + 1):
            move_id = int.from_bytes(rom.read(2), byteorder='little')
            _update_machine_item(machine_type, machine_number, move_id)

    return items


def update_berries(rom: BufferedReader, version_group, version: Version, items: dict):
    num_berries = 42
    data_offset = {
        Version.RUBY: 0x3CD2E8,
        Version.SAPPHIRE: 0x3CD344,
        Version.EMERALD: 0x58A670,
        Version.FIRERED: 0x3DF7E8,
        Version.LEAFGREEN: 0x3DF624,
    }
    data_offset = data_offset[version]
    data_length = 27
    data_length_aligned = 28

    firmness_map = {
        0x01: 'very-soft',
        0x02: 'soft',
        0x03: 'hard',
        0x04: 'very-hard',
        0x05: 'super-hard',
    }

    print('Dumping Berry data')

    @dataclass()
    class BerryData:
        def __init__(self, data: bytes):
            data = struct.unpack('<7sBHBB4s4sBBBBBBB', data)
            self.name = data[0].decode('pokemon_gen3')
            self.firmness = firmness_map[data[1]]
            self.size = data[2]
            self.harvestMax = data[3]
            self.harvestMin = data[4]
            self.descriptionPointers = [data[5], data[6]]
            self.growthTime = data[7]
            self.flavors = {
                'spicy': data[8],
                'dry': data[9],
                'sweet': data[10],
                'bitter': data[11],
                'sour': data[12],
            }
            self.smoothness = data[13]

    for berry_number in range(1, num_berries + 1):
        rom.seek(data_offset + ((berry_number - 1) * data_length_aligned))
        data = rom.read(data_length)
        berry = BerryData(data)
        slug = slugify(berry.name)
        item_slug = '{slug}-berry'.format(slug=slug)
        if berry.harvestMin == berry.harvestMax:
            harvest = str(berry.harvestMin)
        else:
            harvest = '{min}-{max}'.format(min=berry.harvestMin, max=berry.harvestMax)
        items[item_slug]['berry'] = {
            'number': berry_number,
            'firmness': berry.firmness,
            'size': berry.size,
            'growth_time': berry.growthTime,
            'smoothness': berry.smoothness,
            'flavors': berry.flavors,
            'harvest': harvest,
        }
        if version_group != VersionGroup.FIRERED_LEAFGREEN:
            description = []
            for desc_pointer in berry.descriptionPointers:
                line = bytearray()
                rom.seek(gba.address_from_pointer(desc_pointer))
                while rom.peek(1)[0] != 0xFF:
                    line.append(rom.read(1)[0])
                line = line.decode('pokemon_gen3')
                description.append(line)
            items[item_slug]['berry']['flavor_text'] = '\n'.join(description)

    return items


def get_decorations(rom: BufferedReader, version_group: VersionGroup, version: Version):
    num_decorations = 121
    decor_offset = {
        Version.RUBY: 0x3EB6E0,
        Version.SAPPHIRE: 0x3EB73C,
        Version.EMERALD: 0x5A5C08,
    }
    if version not in decor_offset:
        return {}, {}
    decor_offset = decor_offset[version]
    decor_length = 32

    # width, height
    shape_map = {
        0x00: (1, 1),
        0x01: (2, 1),
        0x02: (3, 1),
        0x03: (4, 2),
        0x04: (2, 2),
        0x05: (1, 2),
        0x06: (1, 3),
        0x07: (2, 4),
        0x08: (3, 3),
        0x09: (3, 2),
    }
    category_map = {
        0x00: 'desks',
        0x01: 'chairs',
        0x02: 'plants',
        0x03: 'ornaments',
        0x04: 'mats',
        0x05: 'posters',
        0x06: 'dolls',
        0x07: 'cushions',
    }

    @dataclass()
    class Decoration:
        def __init__(self, data: bytes):
            data = struct.unpack('<B16sBBBH2x4s4s', data)
            self.id = data[0]
            self.name = data[1].decode('pokemon_gen3').strip()
            self.permission = data[2]
            self.width = shape_map[data[3]][0]
            self.height = shape_map[data[3]][1]
            self.category = category_map[data[4]]
            self.price = data[5]
            self.descPointer = data[6]
            self.tilesPointer = data[7]

    print('Dumping Decorations')
    out = {}
    decor_slugs = {}

    # Skip dummy decoration
    for decor_id in range(1, num_decorations):
        rom.seek(decor_offset + (decor_id * decor_length))
        decor = Decoration(rom.read(decor_length))
        slug = slugify(decor.name)
        decor_slugs[decor_id] = slug

        out[slug] = {
            'name': decor.name,
            'category': decor.category,
            'pocket': 'decorations',
            'flags': [],
            'icon': '{slug}.png'.format(slug=slug),
            'buy': None,
            'decoration': {
                'width': decor.width,
                'height': decor.height,
            },
        }
        if decor.category in ['dolls', 'cushions']:
            out[slug].update({
                'short_description': 'A decoration for your room or Secret Base.',
                'description': 'A decoration for your room or Secret Base.',
            })
        else:
            out[slug].update({
                'short_description': 'A decoration for your Secret Base.',
                'description': 'A decoration for your Secret Base.',
            })
        if decor.price > 0:
            out[slug].update({
                'buy': decor.price,
            })
        else:
            del out[slug]['buy']
        rom.seek(gba.address_from_pointer(decor.descPointer))
        description = bytearray()
        while rom.peek(1)[0] != 0xFF:
            description.append(rom.read(1)[0])
        description = description.decode('pokemon_gen3')
        out[slug]['flavor_text'] = description

    return out, decor_slugs


def write_items(out):
    print('Writing Items')
    used_version_groups = set()
    for item_slug, item_data in progressbar.progressbar(out.items()):
        yaml_path = os.path.join(args.out_items, '{slug}.yaml'.format(slug=item_slug))
        try:
            with open(yaml_path, 'r') as item_yaml:
                data = yaml.load(item_yaml.read())
        except IOError:
            data = {}
        data.update(item_data)
        used_version_groups.update(item_data.keys())
        with open(yaml_path, 'w') as item_yaml:
            yaml.dump(data, item_yaml)

    # Remove this version group's data from the new name file
    for old_name, new_name in item_name_changes.items():
        yaml_path = os.path.join(args.out_items, '{slug}.yaml'.format(slug=new_name))
        with open(yaml_path, 'r') as item_yaml:
            data = yaml.load(item_yaml.read())
        changed = False
        for check_version_group in used_version_groups:
            try:
                del data[check_version_group]
                changed = True
            except KeyError:
                # No need to re-write this file
                continue
        if changed:
            with open(yaml_path, 'w') as item_yaml:
                yaml.dump(data, item_yaml)


def _has_pointer(pointer: bytes):
    if int.from_bytes(pointer, byteorder='big') > 0:
        return pointer
    else:
        return None


@dataclass()
class MapLayout:
    length = 24

    def __init__(self, data: bytes):
        data = struct.unpack('<ii4s4s4s4s', data)
        self.width = data[0]
        self.height = data[1]
        self.borderPointer = _has_pointer(data[2])
        self.blocksPointer = _has_pointer(data[3])
        self.mapBlocks = None
        self.primaryTilesetPointer = _has_pointer(data[4])
        self.primaryTileset = None
        self.secondaryTilesetPointer = _has_pointer(data[5])
        self.secondaryTileset = None


@dataclass()
class Tileset:
    length = 24

    def __init__(self, data: bytes):
        data = struct.unpack('<??2x4s4s4s4s4s', data)
        self.compressed = data[0]
        self.secondary = data[1]
        self.tilesPointer = _has_pointer(data[2])
        self.tilePalettesPointer = _has_pointer(data[3])
        self.metatilesPointer = _has_pointer(data[4])
        self.metatileAttributesPointer = _has_pointer(data[5])
        self.callbackPointer = _has_pointer(data[6])


@dataclass()
class MapEventsHeader:
    length = 20

    def __init__(self, data: bytes):
        data = struct.unpack('<BBBB4s4s4s4s', data)
        self.numObjectEvents = data[0]
        self.numWarps = data[1]
        self.numCoordEvents = data[2]
        self.numBgEvents = data[3]
        self.objectEventsPointer = _has_pointer(data[4])
        self.objectEvents: Dict[int, ObjectEvent] = {}
        self.warpsPointer = _has_pointer(data[5])
        self.coordEventsPointer = _has_pointer(data[6])
        self.bgEventsPointer = _has_pointer(data[7])


@dataclass()
class ObjectEvent:
    length = 24

    def __init__(self, data: bytes):
        data = struct.unpack('<BBBxhhBBBxHH4sH2x', data)
        self.eventId = data[0]
        self.spriteId = data[1]
        self.replacementId = data[2]
        self.x = data[3]
        self.y = data[4]
        self.elevation = data[5]
        self.movementType = data[6]
        self.movementRangeX = data[7] & 0x0F
        self.movementRangeY = (data[7] & 0xF0) >> 4
        self.trainerType = data[8]
        # Trainer sight range and berry tree ID are stored in the same place
        self.sightRange = data[9]
        self.berryTreeId = data[9]
        self.scriptPointer = _has_pointer(data[10])
        self.eventFlagId = data[11]


@dataclass()
class MapHeader:
    length = 28

    def __init__(self, data: bytes):
        data = struct.unpack('<4s4s4s4sHHB?BBx?BB', data)
        self.layoutPointer = _has_pointer(data[0])
        self.layout = None
        self.eventsPointer = _has_pointer(data[1])
        self.events = None
        self.scriptsPointer = _has_pointer(data[2])
        self.scripts = None
        self.connectionsPointer = _has_pointer(data[3])
        self.connections = None
        self.musicId = data[4]
        self.layoutId = data[5]
        self.mapSectionId = data[6]
        self.flashRequired = data[7]
        self.weatherId = data[8]
        self.mapTypeId = data[9]
        self.escapeRope = data[10]
        self.flags = data[11]
        self.battleType = data[12]


def _get_map(rom: BufferedReader, version_group: VersionGroup, version, group_id: int, map_id: int):
    group_pointer_offset = {
        Version.RUBY: 0x3085A0,
        Version.SAPPHIRE: 0x308530,
        Version.EMERALD: 0x486578,
        Version.FIRERED: 0x3526A8,
        Version.LEAFGREEN: 0x352688,
    }
    group_pointer_offset = group_pointer_offset[version]

    # Follow the pointers to the header
    old_position = rom.tell()
    rom.seek(group_pointer_offset + (group_id * gba.pointer_length))
    map_group_pointer = rom.read(gba.pointer_length)
    map_group_offset = gba.address_from_pointer(map_group_pointer)
    rom.seek(map_group_offset + (map_id * gba.pointer_length))
    map_header_pointer = rom.read(gba.pointer_length)
    rom.seek(gba.address_from_pointer(map_header_pointer))

    game_map = MapHeader(rom.read(MapHeader.length))

    if game_map.layoutPointer:
        rom.seek(gba.address_from_pointer(game_map.layoutPointer))
        game_map.layout = MapLayout(rom.read(MapLayout.length))

        if game_map.layout.primaryTilesetPointer:
            rom.seek(gba.address_from_pointer(game_map.layout.primaryTilesetPointer))
            game_map.layout.primaryTileset = Tileset(rom.read(Tileset.length))
        if game_map.layout.secondaryTilesetPointer:
            rom.seek(gba.address_from_pointer(game_map.layout.secondaryTilesetPointer))
            game_map.layout.secondaryTileset = Tileset(rom.read(Tileset.length))

    if game_map.eventsPointer:
        rom.seek(gba.address_from_pointer(game_map.eventsPointer))
        game_map.events = MapEventsHeader(rom.read(MapEventsHeader.length))
        if game_map.events.objectEventsPointer:
            rom.seek(gba.address_from_pointer(game_map.events.objectEventsPointer))
            for i in range(game_map.events.numObjectEvents):
                object_event = ObjectEvent(rom.read(ObjectEvent.length))
                game_map.events.objectEvents[object_event.eventId] = object_event

    rom.seek(old_position)

    return game_map


def get_shops(rom: BufferedReader, version_group: VersionGroup, version: Version, item_slugs: dict, decor_slugs: dict,
              items: dict):
    if version_group == VersionGroup.RUBY_SAPPHIRE:
        from .rs_maps import map_slugs
        from .script.rs_commands import ScriptCommand
    elif version_group == VersionGroup.EMERALD:
        from .e_maps import map_slugs
        from .script.e_commands import ScriptCommand
    else:
        from .frlg_maps import map_slugs
        from .script.frlg_commands import ScriptCommand

    # location -> area -> shop identifier -> shop data
    shops: Dict[str, Dict[str, Dict[str, dict]]] = {}
    shop_items: List[Dict[str, Any]] = []

    print('Searching map scripts for shops')

    # State variables used when a Pokemart script has been triggered.
    current_location = None
    current_area = None
    current_event = None
    shop_id_counter = {}

    def _parse_shop(pointer: bytes, command_rom: BufferedReader, shop_type: str):
        # Store the shop info
        if current_location not in shops:
            shops[current_location] = {}
        if current_area not in shops[current_location]:
            shops[current_location][current_area] = {}

        # Differentiate between several pokemart commands in the same event
        counter_id = '{location}_{area}_{event}'.format(location=current_location, area=current_area,
                                                        event=current_event.eventId)
        if counter_id not in shop_id_counter:
            shop_id_counter[counter_id] = 0
        else:
            shop_id_counter[counter_id] += 1
        shop_id = shop_id_counter[counter_id]
        if current_area == 'mart':
            shop_identifier = 'mart'
            shop_name = 'Poké Mart'
        else:
            shop_identifier = 'event-{event}-shop-{shop}'.format(event=current_event.eventId, shop=shop_id)
            shop_name = 'Event {event}, Shop {shop}'.format(event=current_event.eventId, shop=shop_id)

        shops[current_location][current_area][shop_identifier] = {
            'name': shop_name,
        }
        if len(shops[current_location][current_area]) == 1:
            shops[current_location][current_area][shop_identifier]['default'] = True

        # Store the shop's inventory.  The shop name will need manual tuning.
        old_position = command_rom.tell()
        command_rom.seek(gba.address_from_pointer(pointer))
        while command_rom.peek(1)[0] != 0:
            item_id = int.from_bytes(command_rom.read(2), 'little')
            if shop_type == 'pokemart':
                item_slug = item_slugs[item_id]
            else:
                item_slug = decor_slugs[item_id]
            shop_items.append({
                'version_group': version_group.value,
                'location': current_location,
                'area': current_area,
                'shop': shop_identifier,
                'item': item_slug,
                'buy': items[item_slug]['buy']
            })
        command_rom.seek(old_position)

    def _parse_pokemart(pointer: bytes, command_rom: BufferedReader):
        _parse_shop(pointer, command_rom, 'pokemart')

    def _parse_decormart(pointer: bytes, command_rom: BufferedReader):
        _parse_shop(pointer, command_rom, 'decormart')

    # Parse all map scripts, handling pokemart calls
    if version_group in [VersionGroup.RUBY_SAPPHIRE, VersionGroup.EMERALD]:
        callbacks = {
            ScriptCommand.POKEMART: _parse_pokemart,
            ScriptCommand.POKEMARTDECORATION: _parse_decormart,
            ScriptCommand.POKEMARTDECORATION2: _parse_decormart,
        }
    else:
        callbacks = {
            ScriptCommand.POKEMART: _parse_pokemart,
            ScriptCommand.POKEMARTBP: _parse_pokemart,
            ScriptCommand.POKEMARTDECOR: _parse_decormart,
        }
    progress = progressbar.ProgressBar(max_value=sum([len(maps) for maps in map_slugs.values()]))
    i = 0
    for map_group_id, maps in map_slugs.items():
        for map_id, map_info in maps.items():
            current_location = map_info['location']
            current_area = map_info['area']
            game_map = _get_map(rom, version_group, version, map_group_id, map_id)
            event: ObjectEvent
            for event in game_map.events.objectEvents.values():
                current_event = event
                if event.scriptPointer:
                    rom.seek(gba.address_from_pointer(event.scriptPointer))
                    script.do_script(version_group, rom, callbacks)
            i += 1
            progress.update(i)
    progress.finish()

    return shops, shop_items


def write_shops(out: Dict[str, Dict[str, Dict[str, dict]]]):
    print('Writing Shops to Locations')

    def _write_data(child_slugs, area_data, shop_data):
        if len(child_slugs) == 0:
            # Leaf node
            area_data['shops'] = shop_data
        else:
            # Branch node
            leaf_slug = child_slugs.pop(0)
            if 'children' not in area_data:
                area_data['children'] = {}
            if leaf_slug not in area_data['children']:
                if leaf_slug == 'mart':
                    name = 'Poké Mart'
                else:
                    name = leaf_slug.replace('-', ' ').title()
                area_data['children'][leaf_slug] = {'name': name}
            area_data['children'][leaf_slug] = _write_data(child_slugs, area_data['children'][leaf_slug], shop_data)
        return area_data

    for location_slug, vg_data in progressbar.progressbar(out.items()):
        yaml_path = os.path.join(args.out_locations, '{slug}.yaml'.format(slug=location_slug))
        try:
            with open(yaml_path, 'r') as location_yaml:
                data = yaml.load(location_yaml.read())
        except IOError:
            data = {}

        for vg_slug, location_info in vg_data.items():
            # Write shop data, adding area if necessary
            for area_slugs, shop_data in location_info.items():
                area_slugs = area_slugs.split('/')
                root_area = area_slugs.pop(0)
                if root_area not in data[vg_slug]['areas']:
                    if root_area == 'mart':
                        name = 'Poké Mart'
                    else:
                        name = root_area.replace('-', ' ').title()
                    data[vg_slug]['areas'][root_area] = {'name': name}
                data[vg_slug]['areas'][root_area] = _write_data(area_slugs, data[vg_slug]['areas'][root_area],
                                                                shop_data)

        with open(yaml_path, 'w') as location_yaml:
            yaml.dump(data, location_yaml)


def write_shop_items(used_version_groups, out: List[Dict[str, Any]]):
    print('Writing shop items')

    data = []
    with open(args.out_shop_items, 'r') as shop_items_csv:
        for row in csv.DictReader(shop_items_csv):
            if row['version_group'] not in used_version_groups:
                data.append(row)
    data.extend(out)

    with open(args.out_shop_items, 'w') as shop_items_csv:
        writer = csv.DictWriter(shop_items_csv, data[0].keys())
        writer.writeheader()
        writer.writerows(data)


ability_name_changes = {
    'lightningrod': 'lightning-rod',
    'compoundeyes': 'compound-eyes',
}


def get_abilities(rom: BufferedReader, version_group: VersionGroup, version: Version):
    out = {}
    ability_slugs = {}
    num_abilities = 78

    print('Dumping Abilities')

    def _get_names():
        name_offset = {
            Version.RUBY: 0x1FA260,
            Version.SAPPHIRE: 0x1FA1F0,
            Version.EMERALD: 0x31B6DB,
            Version.FIRERED: 0x24FC40,
            Version.LEAFGREEN: 0x24FC1C,
        }
        name_offset = name_offset[version]
        name_length = 13
        # Skip over "None" ability
        for ability_id in range(1, num_abilities):
            rom.seek(name_offset + (ability_id * name_length))
            name = bytearray()
            while rom.peek(1)[0] != 0xFF:
                name.append(rom.read(1)[0])

            name = name.decode('pokemon_gen3')
            slug = slugify(name)
            if slug == 'cacophony':
                # Unused ability
                continue
            ability_slugs[ability_id] = slug
            out[slug] = {
                'name': name
            }

    def _get_flavor_text():
        flavor_offset = {
            Version.RUBY: 0x1F99F8,
            Version.SAPPHIRE: 0x1F9988,
            Version.EMERALD: 0x31AFAC,
            Version.FIRERED: 0x24F3D8,
            Version.LEAFGREEN: 0x24F3B4,
        }
        flavor_offset = flavor_offset[version]

        rom.seek(flavor_offset)
        last_id = 0
        for ability_id, ability_slug in ability_slugs.items():
            # Because we skip some descriptions inside the list but flavor text is stored sequentially,
            # need special handling.
            skip = ability_id - last_id - 1
            while skip >= 0:
                flavor = bytearray()
                while rom.peek(1)[0] != 0xFF:
                    flavor.append(rom.read(1)[0])
                rom.seek(1, io.SEEK_CUR)
                skip -= 1
            flavor = flavor.decode('pokemon_gen3')
            out[ability_slug]['flavor_text'] = flavor
            last_id = ability_id

    def _pullup_data():
        pullup_keys = [
            'short_description',
            'description',
        ]
        print('Using existing data')
        for ability_slug in progressbar.progressbar(ability_slugs.values()):
            if ability_slug in ability_name_changes:
                yaml_path = os.path.join(args.out_abilities,
                                         '{ability}.yaml'.format(ability=ability_name_changes[ability_slug]))
            else:
                yaml_path = os.path.join(args.out_abilities, '{ability}.yaml'.format(ability=ability_slug))
            with open(yaml_path, 'r') as ability_yaml:
                old_ability_data = yaml.load(ability_yaml.read())
                if version_group.value not in old_ability_data:
                    # If the name has changed, try the original name, as it may have been moved already.
                    if ability_slug in ability_name_changes:
                        yaml_path = os.path.join(args.out_abilities, '{ability}.yaml'.format(ability=ability_slug))
                        with open(yaml_path, 'r') as ability_yaml:
                            old_ability_data = yaml.load(ability_yaml.read())
                    else:
                        raise Exception(
                            'Ability {ability} has no data for version group {version_group}.'.format(
                                ability=ability_slug,
                                version_group=version_group.value))
                for key in pullup_keys:
                    if key in old_ability_data[version_group.value]:
                        out[ability_slug][key] = old_ability_data[version_group.value][key]

    _get_names()
    _get_flavor_text()
    _pullup_data()

    return out, ability_slugs


def write_abilities(out):
    print('Writing Abilities')
    used_version_groups = set()
    for ability_slug, ability_data in progressbar.progressbar(out.items()):
        yaml_path = os.path.join(args.out_abilities, '{slug}.yaml'.format(slug=ability_slug))
        try:
            with open(yaml_path, 'r') as ability_yaml:
                data = yaml.load(ability_yaml.read())
        except IOError:
            data = {}
        data.update(ability_data)
        used_version_groups.update(ability_data.keys())
        with open(yaml_path, 'w') as ability_yaml:
            yaml.dump(data, ability_yaml)

    # Remove this version group's data from the new name file
    for old_name, new_name in ability_name_changes.items():
        yaml_path = os.path.join(args.out_abilities, '{slug}.yaml'.format(slug=new_name))
        with open(yaml_path, 'r') as ability_yaml:
            data = yaml.load(ability_yaml.read())
        changed = False
        for check_version_group in used_version_groups:
            try:
                del data[check_version_group]
                changed = True
            except KeyError:
                # No need to re-write this file
                continue
        if changed:
            with open(yaml_path, 'w') as ability_yaml:
                yaml.dump(data, ability_yaml)


def get_pokemon(rom: BufferedReader, version_group: VersionGroup, version: Version, item_slugs: dict, ability_slugs):
    num_pokemon = 412  # This includes some dummy mons in the middle
    species_slugs = {}
    # Keyed by species slug; the first item is always the default Pokemon
    pokemon_slugs = {}
    out = {}

    form_default_map = {
        'castform': 'castform-default',
        'deoxys': 'deoxys-normal',
    }

    def _get_names():
        names_offset = {
            Version.RUBY: 0x1F7184,
            Version.SAPPHIRE: 0x1F7114,
            Version.EMERALD: 0x3185C8,
            Version.FIRERED: 0x245EE0,
            Version.LEAFGREEN: 0x245EBC,
        }
        names_offset = names_offset[version]
        name_length = 11

        slug_overrides = {
            'farfetch-d': 'farfetchd',
        }

        # Skip dummy mon at the beginning
        for species_id in range(1, num_pokemon):
            rom.seek(names_offset + (species_id * name_length))
            name = bytearray()
            while rom.peek(1)[0] != 0xFF:
                name.append(rom.read(1)[0])
            name = name.decode('pokemon_gen3')
            if name == '?':
                # Dummy mon
                continue

            slug = slugify(name.replace('♀', '-f').replace('♂', '-m'))
            if slug in slug_overrides:
                slug = slug_overrides[slug]
            species_slugs[species_id] = slug
            if slug in form_default_map:
                pokemon_slug = form_default_map[slug]
            else:
                pokemon_slug = slug
            pokemon_slugs[slug] = [pokemon_slug]

            out[slug] = {
                'name': name,
                'position': 0,
                'numbers': {},
                'pokemon': {
                    pokemon_slug: {
                        'name': name,
                    }
                }
            }

    def _get_numbers():
        hoenn_dex_offset = {
            Version.RUBY: 0x1FC1F8,
            Version.SAPPHIRE: 0x1FC188,
            Version.EMERALD: 0x31D94C,
        }
        national_dex_offset = {
            Version.RUBY: 0x1FC52E,
            Version.SAPPHIRE: 0x1FC4BE,
            Version.EMERALD: 0x31DC82,
            Version.FIRERED: 0x251FEE,
            Version.LEAFGREEN: 0x251FCA,
        }
        national_dex_offset = national_dex_offset[version]
        if version in hoenn_dex_offset:
            # R/S/E
            hoenn_dex_offset = hoenn_dex_offset[version]

            for species_id, species_slug in species_slugs.items():
                rom.seek(national_dex_offset + ((species_id - 1) * 2))
                out[species_slug]['numbers']['national'] = int.from_bytes(rom.read(2), byteorder='little')
                out[species_slug]['position'] = out[species_slug]['numbers']['national']
            for species_id, species_slug in species_slugs.items():
                rom.seek(hoenn_dex_offset + ((species_id - 1) * 2))
                out[species_slug]['numbers']['hoenn'] = int.from_bytes(rom.read(2), byteorder='little')
        else:
            # FR/LG
            hoenn_dex_offset = None

            for species_id, species_slug in species_slugs.items():
                rom.seek(national_dex_offset + ((species_id - 1) * 2))
                out[species_slug]['numbers']['national'] = int.from_bytes(rom.read(2), byteorder='little')
                if out[species_slug]['numbers']['national'] <= 151:
                    # This is actually the game's logic.  This order is not stored anywhere.  (But Hoenn is!!!)
                    out[species_slug]['numbers']['kanto'] = out[species_slug]['numbers']['national']
                out[species_slug]['position'] = out[species_slug]['numbers']['national']

    def _get_stats():
        stats_offset = {
            Version.RUBY: 0x1FEC30,
            Version.SAPPHIRE: 0x1FEBC0,
            Version.EMERALD: 0x3203CC,
            Version.FIRERED: 0x254784,
            Version.LEAFGREEN: 0x254760,
        }
        stats_offset = stats_offset[version]
        stats_length = 26
        stats_length_aligned = 28

        growth_rate_map = {
            0x00: 'medium',
            0x01: 'slow-then-very-fast',
            0x02: 'fast-then-very-slow',
            0x03: 'medium-slow',
            0x04: 'fast',
            0x05: 'slow',
        }

        egg_group_map = {
            0x01: 'monster',
            0x02: 'water1',
            0x03: 'bug',
            0x04: 'flying',
            0x05: 'ground',
            0x06: 'fairy',
            0x07: 'plant',
            0x08: 'humanshape',
            0x09: 'water3',
            0x0A: 'mineral',
            0x0B: 'indeterminate',
            0x0C: 'water2',
            0x0D: 'ditto',
            0x0E: 'dragon',
            0x0F: 'no-eggs',
        }

        color_map = {
            0x00: 'red',
            0x01: 'blue',
            0x02: 'yellow',
            0x03: 'green',
            0x04: 'black',
            0x05: 'brown',
            0x06: 'purple',
            0x07: 'gray',
            0x08: 'white',
            0x09: 'pink',
        }

        @dataclass()
        class BaseStats:
            def __init__(self, data: bytes):
                data = struct.unpack('<BBBBBBBBBBHHHBBBBBBBBBB', data)
                self.hp = data[0]
                self.attack = data[1]
                self.defense = data[2]
                self.speed = data[3]
                self.specialAttack = data[4]
                self.specialDefense = data[5]
                if data[6] == data[7]:
                    self.types = [type_map[data[6]]]
                else:
                    self.types = [type_map[data[6]], type_map[data[7]]]
                self.captureRate = data[8]
                self.experience = data[9]
                self.evHp = (data[10] & 0b0000000000000011) >> 0
                self.evAttack = (data[10] & 0b0000000000001100) >> 2
                self.evDefense = (data[10] & 0b0000000000110000) >> 4
                self.evSpeed = (data[10] & 0b0000000011000000) >> 6
                self.evSpecialAttack = (data[10] & 0b0000001100000000) >> 8
                self.evSpecialDefense = (data[10] & 0b0000110000000000) >> 10
                if data[11] > 0:
                    self.item1 = item_slugs[data[11]]
                else:
                    self.item1 = None
                if data[12] > 0:
                    self.item2 = item_slugs[data[12]]
                else:
                    self.item2 = None
                self.femaleRate = data[13]
                self.hatchSteps = data[14]
                self.happiness = data[15]
                self.growthRate = growth_rate_map[data[16]]
                self.eggGroups = []
                for egg_group_id in data[17:19]:
                    if egg_group_id > 0 and egg_group_map[egg_group_id] not in self.eggGroups:
                        self.eggGroups.append(egg_group_map[egg_group_id])
                self.ability1, self.ability2 = None, None
                if data[19] > 0:
                    self.ability1 = ability_slugs[data[19]]
                if data[20] > 0:
                    self.ability2 = ability_slugs[data[20]]
                self.safariZoneFleeRate = data[21]
                self.color = color_map[data[22] & 0b01111111]

        for species_id, species_slug in species_slugs.items():
            rom.seek(stats_offset + (species_id * stats_length_aligned))
            stats = BaseStats(rom.read(stats_length))
            pokemon = out[species_slug]['pokemon'][pokemon_slugs[species_slug][0]]
            pokemon.update({
                'default': True,
                'forms_switchable': False,
                'forms_note': None,
                'capture_rate': stats.captureRate,
                'experience': stats.experience,
                'types': stats.types,
                'stats': {
                    'hp': {
                        'base_value': stats.hp,
                        'effort_change': stats.evHp,
                    },
                    'attack': {
                        'base_value': stats.attack,
                        'effort_change': stats.evAttack,
                    },
                    'defense': {
                        'base_value': stats.defense,
                        'effort_change': stats.evDefense,
                    },
                    'speed': {
                        'base_value': stats.speed,
                        'effort_change': stats.evSpeed,
                    },
                    'special-attack': {
                        'base_value': stats.specialAttack,
                        'effort_change': stats.evSpecialDefense,
                    },
                    'special-defense': {
                        'base_value': stats.hp,
                        'effort_change': stats.evSpecialDefense,
                    },
                },
                'growth_rate': stats.growthRate,
                'female_rate': stats.femaleRate,
                'hatch_steps': stats.hatchSteps,
                'egg_groups': stats.eggGroups,
                'wild_held_items': {},
                'happiness': stats.happiness,
                'abilities': {}
            })

            # Gender
            if pokemon['female_rate'] == 255:
                # Genderless
                del pokemon['female_rate']
            else:
                pokemon['female_rate'] = round((pokemon['female_rate']) / 254 * 100)

            # Wild held items
            if stats.item1 or stats.item2:
                if stats.item1 == stats.item2:
                    pokemon['wild_held_items'][stats.item1] = 100
                else:
                    # These chances are hard coded in
                    if stats.item1:
                        pokemon['wild_held_items'][stats.item1] = 50
                    if stats.item2:
                        pokemon['wild_held_items'][stats.item2] = 5
            else:
                del pokemon['wild_held_items']

            # Abilities
            i = 1
            for ability in [stats.ability1, stats.ability2]:
                if not ability:
                    continue
                pokemon['abilities'][ability] = {'hidden': False, 'position': i}
                i += 1

            out[species_slug]['pokemon'][pokemon_slugs[species_slug][0]] = pokemon

    def _get_flavor():
        flavor_offset = {
            Version.RUBY: 0x3B1874,
            Version.SAPPHIRE: 0x3B18D0,
            Version.EMERALD: 0x56B5B0,
            Version.FIRERED: 0x44E850,
            Version.LEAFGREEN: 0x44E270,
        }
        flavor_offset = flavor_offset[version]
        if version_group == VersionGroup.EMERALD:
            # Emerald eliminates the second description pointer
            flavor_length = 30
            flavor_length_aligned = 32
        else:
            flavor_length = 34
            flavor_length_aligned = 36

        @dataclass()
        class Flavor:
            def __init__(self, data: bytes):
                if version_group == VersionGroup.EMERALD:
                    # Emerald eliminates the second description pointer
                    data = struct.unpack('<12sHH4s2xHHHH', data)
                else:
                    data = struct.unpack('<12sHH4s4s2xHHHH', data)

                self.genus = data[0].decode('pokemon_gen3').strip()
                self.height = data[1]
                self.weight = data[2]
                self.flavorPointers = [data[3]]
                if version_group == VersionGroup.EMERALD:
                    self.pokemonScale = data[4]
                    self.pokemonOffset = data[5]
                    self.tainerScale = data[6]
                    self.trainerOffset = data[7]
                else:
                    if int.from_bytes(data[4], byteorder='little', signed=False) > 0:
                        self.flavorPointers.append(data[4])
                    self.pokemonScale = data[5]
                    self.pokemonOffset = data[6]
                    self.trainerScale = data[7]
                    self.trainerOffset = data[8]

        for species_slug in species_slugs.values():
            pokedex_id = out[species_slug]['numbers']['national']
            rom.seek(flavor_offset + (pokedex_id * flavor_length_aligned))
            flavor = Flavor(rom.read(flavor_length))
            pokemon = out[species_slug]['pokemon'][pokemon_slugs[species_slug][0]]
            pokemon.update({
                'genus': '{genus} Pokémon'.format(genus=flavor.genus),
                'height': flavor.height,
                'weight': flavor.weight
            })
            flavor_text = []
            for flavor_pointer in flavor.flavorPointers:
                rom.seek(gba.address_from_pointer(flavor_pointer))
                page_text = bytearray()
                while rom.peek(1)[0] != 0xFF:
                    page_text.append(rom.read(1)[0])
                page_text = page_text.decode('pokemon_gen3')
                flavor_text.append(page_text)
            pokemon['flavor_text'] = '\n'.join(flavor_text)
            out[species_slug]['pokemon'][pokemon_slugs[species_slug][0]] = pokemon

    def _build_forms():
        for species_slug in species_slugs.values():
            if species_slug in form_default_map:
                form_slug = form_default_map[species_slug]
            else:
                form_slug = '{slug}-default'.format(slug=pokemon_slugs[species_slug][0])
            form_name = out[species_slug]['name']

            form = {
                'name': form_name,
                'form_name': 'Default Form',
                'default': True,
                'battle_only': False,
                'icon': 'gen5/{slug}.png'.format(slug=form_slug),
                'sprites': [
                    '{version_group}/{slug}.png'.format(version_group=version_group.value, slug=form_slug),
                    '{version_group}/back/{slug}.png'.format(version_group=version_group.value, slug=form_slug),
                    '{version_group}/shiny/{slug}.png'.format(version_group=version_group.value, slug=form_slug),
                ],
                'art': ['{slug}.png'.format(slug=form_slug)],
                'footprint': '{slug}.png'.format(slug=species_slug),
                'cry': 'gen5/{slug}.webm'.format(slug=form_slug),
            }
            if version_group == VersionGroup.EMERALD:
                form['sprites'] = [
                    '{version_group}/{slug}.png'.format(version_group=version_group.value, slug=form_slug),
                    '{version_group}/shiny/{slug}.png'.format(version_group=version_group.value, slug=form_slug),
                    '{version_group}/animated/{slug}.webm'.format(version_group=version_group.value, slug=form_slug),
                    '{version_group}/animated/shiny/{slug}.webm'.format(version_group=version_group.value,
                                                                        slug=form_slug),
                ]
            out[species_slug]['pokemon'][pokemon_slugs[species_slug][0]]['forms'] = {
                pokemon_slugs[species_slug][0]: form
            }

    def _get_evolution():
        evolution_offset = {
            Version.RUBY: 0x203B80,
            Version.SAPPHIRE: 0x203B10,
            Version.EMERALD: 0x32531C,
            Version.FIRERED: 0x259754,
            Version.LEAFGREEN: 0x259734,
        }
        evolution_offset = evolution_offset[version]

        @dataclass()
        class Evolution:
            def __init__(self, data: bytes):
                data = struct.unpack('<HHH', data)
                self.methodTrigger = data[0]
                self.param = data[1]
                self.evolvesIntoId = data[2]

        # Each species has 5 entries in the evolution table.  Most of them are blank, but this leaves enough room
        # to store all of Eevee's evolutions.
        num_entries = 5
        evolution_length = 6
        evolution_length_aligned = 8
        for species_id, species_slug in species_slugs.items():
            for i in range(0, num_entries):
                rom.seek(evolution_offset + (species_id * evolution_length_aligned * num_entries) + (
                        i * evolution_length_aligned))
                evolution = Evolution(rom.read(evolution_length))
                if evolution.methodTrigger == 0:
                    continue

                evolves_into = species_slugs[evolution.evolvesIntoId]
                out[evolves_into]['pokemon'][pokemon_slugs[evolves_into][0]].update({
                    'evolution_parent': '{species}/{pokemon}'.format(species=species_slug,
                                                                     pokemon=pokemon_slugs[species_slug][0])
                })

                # The methodTrigger entry doesn't map cleanly to our data format, so everything
                # is a special case.
                if evolution.methodTrigger == 0x01:
                    # Friendship, any time
                    out[evolves_into]['pokemon'][pokemon_slugs[evolves_into][0]].update({
                        'evolution_conditions': {
                            'level-up': {
                                'minimum_happiness': 220,
                            }
                        }
                    })
                elif evolution.methodTrigger == 0x02:
                    # Friendship, during the day
                    out[evolves_into]['pokemon'][pokemon_slugs[evolves_into][0]].update({
                        'evolution_conditions': {
                            'level-up': {
                                'minimum_happiness': 220,
                                'time_of_day': ['day'],
                            }
                        }
                    })
                elif evolution.methodTrigger == 0x03:
                    # Friendship, during the night
                    out[evolves_into]['pokemon'][pokemon_slugs[evolves_into][0]].update({
                        'evolution_conditions': {
                            'level-up': {
                                'minimum_happiness': 220,
                                'time_of_day': ['night'],
                            }
                        }
                    })
                elif evolution.methodTrigger == 0x04:
                    # Minimum level
                    out[evolves_into]['pokemon'][pokemon_slugs[evolves_into][0]].update({
                        'evolution_conditions': {
                            'level-up': {
                                'minimum_level': evolution.param,
                            }
                        }
                    })
                elif evolution.methodTrigger == 0x05:
                    # Traded
                    out[evolves_into]['pokemon'][pokemon_slugs[evolves_into][0]].update({
                        'evolution_conditions': {
                            'trade': {}
                        }
                    })
                elif evolution.methodTrigger == 0x06:
                    # Traded, with item
                    out[evolves_into]['pokemon'][pokemon_slugs[evolves_into][0]].update({
                        'evolution_conditions': {
                            'trade': {
                                'held_item': item_slugs[evolution.param],
                            }
                        }
                    })
                elif evolution.methodTrigger == 0x07:
                    # Use item
                    out[evolves_into]['pokemon'][pokemon_slugs[evolves_into][0]].update({
                        'evolution_conditions': {
                            'use-item': {
                                'trigger_item': item_slugs[evolution.param],
                            }
                        }
                    })
                elif evolution.methodTrigger == 0x08:
                    # Minimum level, Attack > Defense
                    out[evolves_into]['pokemon'][pokemon_slugs[evolves_into][0]].update({
                        'evolution_conditions': {
                            'level-up': {
                                'minimum_level': evolution.param,
                                'physical_stats_difference': 1,
                            }
                        }
                    })
                elif evolution.methodTrigger == 0x09:
                    # Minimum level, Attack == Defense
                    out[evolves_into]['pokemon'][pokemon_slugs[evolves_into][0]].update({
                        'evolution_conditions': {
                            'level-up': {
                                'minimum_level': evolution.param,
                                'physical_stats_difference': 0,
                            }
                        }
                    })
                elif evolution.methodTrigger == 0x0A:
                    # Minimum level, Attack < Defense
                    out[evolves_into]['pokemon'][pokemon_slugs[evolves_into][0]].update({
                        'evolution_conditions': {
                            'level-up': {
                                'minimum_level': evolution.param,
                                'physical_stats_difference': -1,
                            }
                        }
                    })
                elif evolution.methodTrigger == 0x0B or evolution.methodTrigger == 0x0C:
                    # Minimum level (Wurmple to Silcoon or Cascoon)
                    # Because our data structure is flipped from the way the games store it,
                    # we already know what species the Wurmple will evolve into.  As such,
                    # this is stored no differently from a normal level_up evolution condition.
                    out[evolves_into]['pokemon'][pokemon_slugs[evolves_into][0]].update({
                        'evolution_conditions': {
                            'level-up': {
                                'minimum_level': evolution.param,
                            }
                        }
                    })
                elif evolution.methodTrigger == 0x0D:
                    # Minimum level
                    # This is the Ninjask side of the evolution and functions no differently
                    # from a normal level_up evolution condition
                    out[evolves_into]['pokemon'][pokemon_slugs[evolves_into][0]].update({
                        'evolution_conditions': {
                            'level-up': {
                                'minimum_level': evolution.param,
                            }
                        }
                    })
                elif evolution.methodTrigger == 0x0E:
                    # Shedinja
                    out[evolves_into]['pokemon'][pokemon_slugs[evolves_into][0]].update({
                        'evolution_conditions': {
                            'shed': {}
                        }
                    })
                elif evolution.methodTrigger == 0x0F:
                    # Minimum beauty
                    out[evolves_into]['pokemon'][pokemon_slugs[evolves_into][0]].update({
                        'evolution_conditions': {
                            'level-up': {
                                'minimum_beauty': evolution.param,
                            }
                        }
                    })
                else:
                    raise Exception('0x{method_trigger:2x} is not a valid method/trigger value'.format(
                        method_trigger=evolution.methodTrigger))

    def _handle_specials():
        # Generate the Unown forms
        # A-Z
        unown_letters = [char.to_bytes(1, byteorder=sys.byteorder).decode('ascii') for char in range(0x41, 0x5B)]
        # Add the new ! and ? forms
        unown_letters.extend(['!', '?'])
        for letter in unown_letters:
            form_slug = 'unown-{letter}'.format(
                letter=letter.lower().replace('!', 'exclamation').replace('?', 'question'))
            form = out['unown']['pokemon']['unown']['forms']['unown'].copy()
            form.update({
                'name': 'UNOWN ({letter})'.format(letter=letter.upper()),
                'form_name': letter.upper(),
                'default': letter.upper() == 'A',
                'battle_only': False,
                'icon': 'gen5/{slug}.png'.format(slug=form_slug),
                'sprites': [
                    '{version_group}/{slug}.png'.format(version_group=version_group.value, slug=form_slug),
                    '{version_group}/back/{slug}.png'.format(version_group=version_group.value, slug=form_slug),
                    '{version_group}/shiny/{slug}.png'.format(version_group=version_group.value, slug=form_slug),
                ],
                'art': ['unown-f.png'],
            })
            if version_group == VersionGroup.EMERALD:
                form['sprites'] = [
                    '{version_group}/{slug}.png'.format(version_group=version_group.value, slug=form_slug),
                    '{version_group}/shiny/{slug}.png'.format(version_group=version_group.value, slug=form_slug),
                    '{version_group}/animated/{slug}.webm'.format(version_group=version_group.value, slug=form_slug),
                    '{version_group}/animated/shiny/{slug}.webm'.format(version_group=version_group.value,
                                                                        slug=form_slug),
                ]
            out['unown']['pokemon']['unown']['forms'][form_slug] = form
        del out['unown']['pokemon']['unown']['forms']['unown']

        # Castform's transformations are special cases in the battle code
        castform_type_map = {
            'sunny': 'fire',
            'rainy': 'water',
            'snowy': 'ice',
        }
        for form_slug, form_type in castform_type_map.items():
            pokemon_slug = 'castform-{form}'.format(form=form_slug)
            pokemon_name = '{form} CASTFORM'.format(form=form_slug.title())
            pokemon_slugs['castform'].append(pokemon_slug)
            pokemon = out['castform']['pokemon'][pokemon_slugs['castform'][0]].copy()
            pokemon.update({
                'name': pokemon_name,
                'default': False,
                'types': [form_type],
            })
            form = pokemon['forms'][pokemon_slugs['castform'][0]].copy()
            form.update({
                'name': pokemon_name,
                'form_name': '{form} Form'.format(form=form_slug.title()),
                'default': True,
                'battle_only': True,
                'icon': '{slug}.png'.format(slug=pokemon_slug),
                'sprites': [
                    '{version_group}/{slug}'.format(version_group=version_group.value, slug=pokemon_slug),
                    '{version_group}/back/{slug}'.format(version_group=version_group.value, slug=pokemon_slug),
                    '{version_group}/shiny/{slug}'.format(version_group=version_group.value, slug=pokemon_slug),
                ],
            })
            if version_group == VersionGroup.EMERALD:
                form['sprites'] = [
                    '{version_group}/{slug}.png'.format(version_group=version_group.value, slug=form_slug),
                    '{version_group}/shiny/{slug}.png'.format(version_group=version_group.value, slug=form_slug),
                    '{version_group}/animated/{slug}.webm'.format(version_group=version_group.value, slug=form_slug),
                    '{version_group}/animated/shiny/{slug}.webm'.format(version_group=version_group.value,
                                                                        slug=form_slug),
                ]
            pokemon['forms'] = {pokemon_slug: form}
            out['castform']['pokemon'][pokemon_slug] = pokemon

        # Deoxys is a special case in the game's data.  Only the form present in the version is
        # in that version's code.  R/S only have Normal Deoxys, which has been inserted already.
        deoxys_stats_offset = {
            Version.EMERALD: 0x329D48,
            Version.FIRERED: 0x25E026,
            Version.LEAFGREEN: 0x25E00C,
        }
        deoxys_form_map = {
            Version.EMERALD: 'speed',
            Version.FIRERED: 'attack',
            Version.LEAFGREEN: 'defense',
        }
        if version in deoxys_stats_offset:
            # Using the normal form as a template, update the stats
            rom.seek(deoxys_stats_offset[version])
            pokemon_slug = 'deoxys-{form}'.format(form=deoxys_form_map[version])
            pokemon_name = '{form} DEOXYS'.format(form=deoxys_form_map[version].title())
            pokemon_slugs['deoxys'].append(pokemon_slug)
            pokemon = out['deoxys']['pokemon'][pokemon_slugs['deoxys'][0]].copy()
            del out['deoxys']['pokemon'][pokemon_slugs['deoxys'][0]]

            is_default = version in [Version.EMERALD, Version.FIRERED]  # Need to pick one default
            pokemon.update({
                'name': pokemon_name,
                'default': is_default,
            })

            # Update stats
            stats = ['hp', 'attack', 'defense', 'speed', 'special-attack', 'special-defense']
            i = 0
            for stat in stats:
                pokemon['stats'][stat]['base_value'] = int.from_bytes(rom.read(2), byteorder='little')
                i += 1

            # Update appearance
            form = pokemon['forms'][pokemon_slugs['deoxys'][0]].copy()
            del pokemon['forms'][pokemon_slugs['deoxys'][0]]
            form.update({
                'name': pokemon_name,
                'form_name': '{form} Forme'.format(form=deoxys_form_map[version].title()),
                'default': True,
                'icon': 'gen5/{slug}.png'.format(slug=pokemon_slug),
                'sprites': [
                    '{version_group}/{slug}'.format(version_group=version_group.value, slug=pokemon_slug),
                    '{version_group}/back/{slug}'.format(version_group=version_group.value, slug=pokemon_slug),
                    '{version_group}/shiny/{slug}'.format(version_group=version_group.value, slug=pokemon_slug),
                ],
                'art': ['{slug}.png'.format(slug=pokemon_slug)],
            })
            if version_group == VersionGroup.EMERALD:
                form['sprites'] = [
                    '{version_group}/{slug}.png'.format(version_group=version_group.value, slug=pokemon_slug),
                    '{version_group}/shiny/{slug}.png'.format(version_group=version_group.value, slug=pokemon_slug),
                    '{version_group}/animated/{slug}.webm'.format(version_group=version_group.value, slug=pokemon_slug),
                    '{version_group}/animated/shiny/{slug}.webm'.format(version_group=version_group.value,
                                                                        slug=pokemon_slug),
                ]
            pokemon['forms'] = {pokemon_slug: form}
            out['deoxys']['pokemon'][pokemon_slug] = pokemon
            del pokemon_slugs['deoxys'][0]
        else:
            # Update the names for R/S
            out['deoxys']['pokemon'][pokemon_slugs['deoxys'][0]]['name'] = 'Normal DEOXYS'
            out['deoxys']['pokemon'][pokemon_slugs['deoxys'][0]]['forms'][pokemon_slugs['deoxys'][0]].update({
                'name': 'Normal DEOXYS',
                'form_name': 'Normal Forme',
            })

    def _pullup_data():
        pullup_keys = [
            'forms_note',
        ]
        print('Using existing data')
        for species_slug in progressbar.progressbar(species_slugs.values()):
            yaml_path = os.path.join(args.out_pokemon, '{species}.yaml'.format(species=species_slug))
            with open(yaml_path, 'r') as species_yaml:
                old_species_data = yaml.load(species_yaml.read())
                for key in pullup_keys:
                    for pokemon_slug, pokemon_data in old_species_data[version_group.value]['pokemon'].items():
                        if pokemon_slug not in out[species_slug]['pokemon']:
                            # Not all version have the same Pokemon as their version group partner.
                            continue
                        if key in pokemon_data:
                            out[species_slug]['pokemon'][pokemon_slug][key] = pokemon_data[key]
                        elif key in out[species_slug]['pokemon'][pokemon_slug]:
                            del out[species_slug]['pokemon'][pokemon_slug][key]

    print('Dumping Pokemon')
    _get_names()
    _get_numbers()
    _get_stats()
    _get_flavor()
    _build_forms()
    _get_evolution()
    _handle_specials()
    _pullup_data()

    return out, species_slugs, pokemon_slugs


def write_pokemon(out):
    print('Writing Pokemon')
    for species_slug, species_data in progressbar.progressbar(out.items()):
        yaml_path = os.path.join(args.out_pokemon, '{slug}.yaml'.format(slug=species_slug))
        try:
            with open(yaml_path, 'r') as species_yaml:
                data = yaml.load(species_yaml.read())
        except IOError:
            data = {}
        data.update(species_data)
        with open(yaml_path, 'w') as species_yaml:
            yaml.dump(data, species_yaml)


def get_pokemon_moves(rom: BufferedReader, version_group: VersionGroup, version: Version, species_slugs: dict,
                      pokemon_slugs: dict, move_slugs: dict, items: dict):
    out = set()

    def _get_levelup():
        levelup_pointer_offset = {
            Version.RUBY: 0x207BE0,
            Version.SAPPHIRE: 0x207B70,
            Version.EMERALD: 0x32937C,
            Version.FIRERED: 0x25D7B4,
            Version.LEAFGREEN: 0x25D794,
        }
        levelup_pointer_offset = levelup_pointer_offset[version]
        levelup_entry_length = 2

        for species_id, species_slug in species_slugs.items():
            rom.seek(levelup_pointer_offset + (species_id * gba.pointer_length))
            levelup_offset = gba.address_from_pointer(rom.read(gba.pointer_length))
            rom.seek(levelup_offset)
            while int.from_bytes(rom.peek(levelup_entry_length)[:levelup_entry_length], byteorder='little') != 0xFFFF:
                data = int.from_bytes(rom.read(levelup_entry_length), byteorder='little')
                move_id = data & 0x01FF
                level = (data & 0xFE00) >> 9
                for pokemon_slug in pokemon_slugs[species_slug]:
                    out.add((
                        ('species', species_slug),
                        ('pokemon', pokemon_slug),
                        ('version_group', version_group.value),
                        ('move', move_slugs[move_id]),
                        ('learn_method', 'level-up'),
                        ('level', level),
                        ('machine', None),
                    ))

    def _get_machines():
        machines_offset = {
            Version.RUBY: 0x1FD108,
            Version.SAPPHIRE: 0x1FD098,
            Version.EMERALD: 0x31E898,
            Version.FIRERED: 0x252BC8,
            Version.LEAFGREEN: 0x252BA4,
        }
        machines_offset = machines_offset[version]
        machines_length = 8

        # Get the moves each tm teaches
        machine_moves = {}
        for item_slug, item_data in items.items():
            if 'machine' not in item_data:
                continue
            machine_data = item_data['machine']
            machine_moves[item_slug] = machine_data['move']

        for species_id, species_slug in species_slugs.items():
            rom.seek(machines_offset + (species_id * machines_length))
            machine_bits = int.from_bytes(rom.read(machines_length), byteorder='little')
            for machine_id in range(1, 59):
                can_learn = (machine_bits & (1 << (machine_id - 1))) > 0
                if can_learn:
                    if machine_id > 50:
                        machine_type = 'HM'
                        machine_number = machine_id - 50
                    else:
                        machine_type = 'TM'
                        machine_number = machine_id
                    item_slug = '{type}{number:02}'.format(type=machine_type.lower(), number=machine_number)

                    for pokemon_slug in pokemon_slugs[species_slug]:
                        out.add((
                            ('species', species_slug),
                            ('pokemon', pokemon_slug),
                            ('version_group', version_group.value),
                            ('move', machine_moves[item_slug]),
                            ('learn_method', 'machine'),
                            ('level', None),
                            ('machine', item_slug),
                        ))

    def _get_egg_moves():
        egg_moves_offset = {
            Version.RUBY: 0x2091F4,
            Version.SAPPHIRE: 0x209184,
            Version.EMERALD: 0x32ADD8,
            Version.FIRERED: 0x25EF0C,
            Version.LEAFGREEN: 0x25EEEC,
        }
        egg_moves_offset = egg_moves_offset[version]

        rom.seek(egg_moves_offset)
        species_slug = None
        while int.from_bytes(rom.peek(2)[:2], byteorder='little') != 0xFFFF:
            data = int.from_bytes(rom.read(2), byteorder='little')
            if (data - 20000) > 0:
                # New species
                species_slug = species_slugs[data - 20000]
                continue

            # Learnable move
            move_slug = move_slugs[data]
            for pokemon_slug in pokemon_slugs[species_slug]:
                out.add((
                    ('species', species_slug),
                    ('pokemon', pokemon_slug),
                    ('version_group', version_group.value),
                    ('move', move_slug),
                    ('learn_method', 'egg'),
                    ('level', None),
                    ('machine', None),
                ))

    def _get_tutors():
        tutored_moves_offset = {
            Version.EMERALD: 0x61500C,
            Version.FIRERED: 0x459B60,
            Version.LEAFGREEN: 0x459580,
        }
        tutor_learnset_offset = {
            Version.EMERALD: 0x615048,
            Version.FIRERED: 0x459B7E,
            Version.LEAFGREEN: 0x45959E,
        }
        if version not in tutored_moves_offset:
            # R/S has no move tutors
            return
        tutored_moves_offset = tutored_moves_offset[version]
        tutor_learnset_offset = tutor_learnset_offset[version]
        if version_group == VersionGroup.FIRERED_LEAFGREEN:
            tutor_count = 15
            tutor_length = 2
        else:
            tutor_count = 30
            tutor_length = 4

        # Find what move each tutor teaches
        tutor_move_map = {}
        for tutor_id in range(0, tutor_count):
            rom.seek(tutored_moves_offset + (tutor_id * 2))
            move_id = int.from_bytes(rom.read(2), byteorder='little')
            tutor_move_map[tutor_id] = move_slugs[move_id]

        # Get the learnsets
        for species_id, species_slug in species_slugs.items():
            rom.seek(tutor_learnset_offset + (species_id * tutor_length))
            tutor_bits = int.from_bytes(rom.read(tutor_length), byteorder='little')
            for tutor_id, move_slug in tutor_move_map.items():
                can_learn = (tutor_bits & (1 << tutor_id)) > 0
                if can_learn:
                    for pokemon_slug in pokemon_slugs[species_slug]:
                        out.add((
                            ('species', species_slug),
                            ('pokemon', pokemon_slug),
                            ('version_group', version_group.value),
                            ('move', move_slug),
                            ('learn_method', 'tutor'),
                            ('level', None),
                            ('machine', None),
                        ))

        if version_group == VersionGroup.FIRERED_LEAFGREEN:
            # FR/LG has three special case move tutors that will teach a move to a
            # fully-evolved starter.  These are not listed in a table anywhere!
            out.add((
                ('species', 'venusaur'),
                ('pokemon', 'venusaur'),
                ('version_group', version_group.value),
                ('move', 'frenzy-plant'),
                ('learn_method', 'tutor'),
                ('level', None),
                ('machine', None),
            ))
            out.add((
                ('species', 'charizard'),
                ('pokemon', 'charizard'),
                ('version_group', version_group.value),
                ('move', 'blast-burn'),
                ('learn_method', 'tutor'),
                ('level', None),
                ('machine', None),
            ))
            out.add((
                ('species', 'blastoise'),
                ('pokemon', 'blastoise'),
                ('version_group', version_group.value),
                ('move', 'hydro-cannon'),
                ('learn_method', 'tutor'),
                ('level', None),
                ('machine', None),
            ))

    print('Dumping Pokemon moves')
    _get_levelup()
    _get_machines()
    _get_egg_moves()
    _get_tutors()

    if version_group == VersionGroup.EMERALD:
        # This is a special case in the daycare egg code
        out.add((
            ('species', 'pichu'),
            ('pokemon', 'pichu'),
            ('version_group', version_group.value),
            ('move', 'volt-tackle'),
            ('learn_method', 'light-ball-egg'),
            ('level', None),
            ('machine', None),
        ))

    return out


def write_pokemon_moves(used_version_groups, out: set):
    print('Writing Pokemon moves')

    # Get existing data, removing those that have just been ripped.
    delete_learn_methods = [
        'level-up',
        'machine',
        'tutor',
        'egg',
        'light-ball-egg',
    ]
    data = []
    with open(args.out_pokemon_moves, 'r') as pokemon_moves_csv:
        for row in progressbar.progressbar(csv.DictReader(pokemon_moves_csv)):
            if row['version_group'] not in used_version_groups or row['learn_method'] not in delete_learn_methods:
                data.append(row)

    data.extend([dict(row) for row in out])
    with open(args.out_pokemon_moves, 'w') as pokemon_moves_csv:
        writer = csv.DictWriter(pokemon_moves_csv, fieldnames=data[0].keys())
        writer.writeheader()
        for row in progressbar.progressbar(data):
            writer.writerow(row)


def get_encounters(rom: BufferedReader, version_group: VersionGroup, version: Version, species_slugs: dict,
                   pokemon_slugs: dict):
    if version_group == VersionGroup.RUBY_SAPPHIRE:
        from .rs_maps import map_slugs
    elif version_group == VersionGroup.EMERALD:
        from .e_maps import map_slugs
    else:
        from .frlg_maps import map_slugs

    print('Dumping encounters')

    out = []

    map_encounter_header_offset = {
        Version.RUBY: 0x39D46C,
        Version.SAPPHIRE: 0x39D2B4,
        Version.EMERALD: 0x552D48,
        Version.FIRERED: 0x3C9CB8,
        Version.LEAFGREEN: 0x3C9AF4,
    }
    map_encounter_header_offset = map_encounter_header_offset[version]

    method_slot_chances = {
        'walk': [20, 20, 10, 10, 10, 10, 5, 5, 4, 4, 1, 1],
        'surf': [60, 30, 5, 4, 1],
        'rock-smash': [60, 30, 5, 4, 1],
        'old-rod': [70, 30],
        'good-rod': [60, 20, 20],
        'super-rod': [40, 40, 15, 4, 1],
    }

    @dataclass()
    class WildPokemonHeader:
        length = 20

        def __init__(self, data: bytes):
            data = struct.unpack('<BB2x4s4s4s4s', data)
            self.mapGroup = data[0]
            self.mapId = data[1]
            self.grassEncountersPointer = None
            self.surfEncountersPointer = None
            self.rockSmashEncountersPointer = None
            self.fishingEncountersPointer = None
            if int.from_bytes(data[2], byteorder='little') > 0:
                self.grassEncountersPointer = data[2]
            if int.from_bytes(data[3], byteorder='little') > 0:
                self.surfEncountersPointer = data[3]
            if int.from_bytes(data[4], byteorder='little') > 0:
                self.rockSmashEncountersPointer = data[4]
            if int.from_bytes(data[5], byteorder='little') > 0:
                self.fishingEncountersPointer = data[5]

    @dataclass()
    class WildPokemonInfo:
        length = 8

        def __init__(self, data: bytes):
            data = struct.unpack('<B3x4s', data)
            self.mapEncounterRate = data[0]
            self.encountersPointer = data[1]

    @dataclass()
    class WildPokemon:
        length = 4

        def __init__(self, data: bytes):
            data = struct.unpack('<BBH', data)
            self.levelMin = data[0]
            self.levelMax = data[1]
            self.species = species_slugs[data[2]]

    def _process_encounters(map_info: dict, method: str, table_pointer: bytes):
        if not table_pointer:
            # No encounters for this method
            return

        rom.seek(gba.address_from_pointer(table_pointer))
        encounter_info = WildPokemonInfo(rom.read(WildPokemonInfo.length))
        rom.seek(gba.address_from_pointer(encounter_info.encountersPointer))
        # The rods use different parts of the table:
        # Old rod = 0-1
        # Good rod = 2-4
        # Super rod = 5-9
        # This will seek to the correct place in the table.
        if method == 'good-rod':
            rom.seek(len(method_slot_chances['old-rod']) * WildPokemon.length, io.SEEK_CUR)
        elif method == 'super-rod':
            rom.seek(len(method_slot_chances['old-rod']) * WildPokemon.length, io.SEEK_CUR)
            rom.seek(len(method_slot_chances['good-rod']) * WildPokemon.length, io.SEEK_CUR)
        for encounter_chance in method_slot_chances[method]:
            encounter = WildPokemon(rom.read(WildPokemon.length))
            if encounter.levelMin == encounter.levelMax:
                level_range = str(encounter.levelMin)
            else:
                level_range = '{min}-{max}'.format(min=encounter.levelMin, max=encounter.levelMax)
            out.append({
                'version': version.value,
                'location': map_info['location'],
                'area': map_info['area'],
                'method': method,
                'species': encounter.species,
                'pokemon': pokemon_slugs[encounter.species][0],
                'level': level_range,
                'chance': encounter_chance,
                'conditions': None,
                'note': None,
            })

    rom.seek(map_encounter_header_offset)
    while int.from_bytes(rom.peek(2)[:2], byteorder='little') != 0xFFFF:
        map_encounter_header = WildPokemonHeader(rom.read(WildPokemonHeader.length))
        # Need a bookmark of sorts as we follow the pointers around
        next_header_start_position = rom.tell()

        if map_encounter_header.mapGroup not in map_slugs \
                or map_encounter_header.mapId not in map_slugs[map_encounter_header.mapGroup]:
            # There's quite a few unused maps with encounter data, but we don't care about them.
            continue
        map_info = map_slugs[map_encounter_header.mapGroup][map_encounter_header.mapId]

        _process_encounters(map_info, 'walk', map_encounter_header.grassEncountersPointer)
        _process_encounters(map_info, 'surf', map_encounter_header.surfEncountersPointer)
        _process_encounters(map_info, 'rock-smash', map_encounter_header.rockSmashEncountersPointer)
        # The three rods use the same table, just different parts of it.
        _process_encounters(map_info, 'old-rod', map_encounter_header.fishingEncountersPointer)
        _process_encounters(map_info, 'good-rod', map_encounter_header.fishingEncountersPointer)
        _process_encounters(map_info, 'super-rod', map_encounter_header.fishingEncountersPointer)

        # Return to the bookmark
        rom.seek(next_header_start_position)

    return out


def write_encounters(used_versions, out):
    print('Writing encounters')
    delete_encounter_methods = [
        'walk',
        'surf',
        'old-rod',
        'good-rod',
        'super-rod',
        'rock-smash',
    ]
    data = []
    highest_id = 0
    with open(args.out_encounters, 'r') as encounters_csv:
        for row in progressbar.progressbar(csv.DictReader(encounters_csv)):
            if row['version'] not in used_versions or row['method'] not in delete_encounter_methods:
                data.append(row)
                highest_id = max(highest_id, int(row['id']))

    # Need to generate ids for our data; start with the highest id number in the existing data
    last_id = highest_id
    for encounter in out:
        encounter['id'] = last_id + 5
        last_id = encounter['id']
        data.append(encounter)
    with open(args.out_encounters, 'w') as encounters_csv:
        writer = csv.DictWriter(encounters_csv, fieldnames=data[0].keys())
        writer.writeheader()
        for row in progressbar.progressbar(data):
            writer.writerow(row)


if __name__ == '__main__':
    # Get config
    argparser = argparse.ArgumentParser(description='Load Gen 3 data.  (R/S uses Rev 1.2 ROMs)')
    argparser.add_argument('--rom', action='append', type=argparse.FileType('rb'), required=True, help='ROM File path')
    argparser.add_argument('--version', action='append', type=str, choices=[version.value for version in Version],
                           help='Version slug to dump')
    argparser.add_argument('--out-pokemon', type=str, required=True, help='Pokemon YAML file dir')
    argparser.add_argument('--out-pokemon_moves', type=str, required=True, help='Pokemon Move CSV file')
    argparser.add_argument('--out-moves', type=str, required=True, help='Move YAML file dir')
    argparser.add_argument('--out-contest_effects', type=str, required=True, help='Contest Effect YAML file dir')
    argparser.add_argument('--out-items', type=str, required=True, help='Item YAML file dir')
    argparser.add_argument('--out-shop_items', type=str, required=True, help='Shop Data CSV file')
    argparser.add_argument('--out-locations', type=str, required=True, help='Location YAML file dir')
    argparser.add_argument('--out-encounters', type=str, required=True, help='Encounter CSV file')
    argparser.add_argument('--out-abilities', type=str, required=True, help='Ability YAML file dir')
    argparser.add_argument('--write-pokemon', action='store_true', help='Write Pokemon data')
    argparser.add_argument('--write-pokemon_moves', action='store_true', help='Write Pokemon move data')
    argparser.add_argument('--write-moves', action='store_true', help='Write Move data')
    argparser.add_argument('--write-contest_effects', action='store_true', help='Write Contest Effect data')
    argparser.add_argument('--write-items', action='store_true', help='Write Item data')
    argparser.add_argument('--write-shops', action='store_true', help='Write Shop data')
    argparser.add_argument('--write-shop_items', action='store_true', help='Write Shop items')
    argparser.add_argument('--write-encounters', action='store_true', help='Write Encounter data')
    argparser.add_argument('--write-abilities', action='store_true', help='Write Ability data')
    global args
    args = argparser.parse_args()

    # What version is this?
    versionmap = {
        'AXVE': Version.RUBY,
        'AXPE': Version.SAPPHIRE,
        'BPEE': Version.EMERALD,
        'BPRE': Version.FIRERED,
        'BPGE': Version.LEAFGREEN,
    }
    versiongroupmap = {
        Version.RUBY: VersionGroup.RUBY_SAPPHIRE,
        Version.SAPPHIRE: VersionGroup.RUBY_SAPPHIRE,
        Version.EMERALD: VersionGroup.EMERALD,
        Version.FIRERED: VersionGroup.FIRERED_LEAFGREEN,
        Version.LEAFGREEN: VersionGroup.FIRERED_LEAFGREEN,
    }

    out_moves = {}
    out_contest_effects = {}
    out_items = {}
    out_shops = {}
    out_shop_items = []
    out_abilities = {}
    out_pokemon = {}
    out_pokemon_moves = set()
    out_encounters = []
    dumped_versions = set()
    dumped_version_groups = set()
    dump_rom: BufferedReader
    for dump_rom in args.rom:
        dump_rom.seek(0xAC)
        dump_version = dump_rom.read(4)
        dump_version = dump_version.decode('ascii')
        dump_version = versionmap[dump_version]
        if len(args.version) > 0 and dump_version.value not in args.version:
            # Skip this version
            continue
        dump_version_group = versiongroupmap[dump_version]
        print('Using version group {version_group}'.format(version_group=dump_version_group.value))
        print('Using version {version}'.format(version=dump_version.value))

        vg_moves, vg_contest_effects, vg_move_slugs = get_moves(dump_rom, dump_version_group, dump_version)
        out_moves = group_by_version_group(dump_version_group.value, vg_moves, out_moves)
        out_contest_effects = group_by_version_group(dump_version_group.value, vg_contest_effects, out_contest_effects)
        vg_items, vg_item_slugs = get_items(dump_rom, dump_version_group, dump_version)
        vg_items = update_machines(dump_rom, dump_version, vg_items, vg_move_slugs, vg_moves)
        vg_items = update_berries(dump_rom, dump_version_group, dump_version, vg_items)
        vg_decor, vg_decor_slugs = get_decorations(dump_rom, dump_version_group, dump_version)
        vg_items.update(vg_decor)
        out_items = group_by_version_group(dump_version_group.value, vg_items, out_items)
        vg_shops, vg_shop_items = get_shops(dump_rom, dump_version_group, dump_version, vg_item_slugs, vg_decor_slugs,
                                            vg_items)
        out_shops = group_by_version_group(dump_version_group.value, vg_shops, out_shops)
        out_shop_items.extend(vg_shop_items)
        vg_abilities, vg_ability_slugs = get_abilities(dump_rom, dump_version_group, dump_version)
        out_abilities = group_by_version_group(dump_version_group.value, vg_abilities, out_abilities)
        v_pokemon, vg_species_slugs, vg_pokemon_slugs = get_pokemon(dump_rom, dump_version_group, dump_version,
                                                                    vg_item_slugs, vg_ability_slugs)
        out_pokemon = group_pokemon(dump_version.value, dump_version_group.value, v_pokemon, out_pokemon)
        out_pokemon_moves.update(
            get_pokemon_moves(dump_rom, dump_version_group, dump_version, vg_species_slugs, vg_pokemon_slugs,
                              vg_move_slugs, vg_items))
        out_encounters.extend(
            get_encounters(dump_rom, dump_version_group, dump_version, vg_species_slugs, vg_pokemon_slugs))

        dumped_versions.add(dump_version.value)
        dumped_version_groups.add(dump_version_group.value)

    if len(dumped_versions) < len(args.version):
        # Didn't dump all requested versions
        missing_versions = []
        for requested_version in args.version:
            if requested_version not in dumped_versions:
                missing_versions.append(requested_version)
        print('Could not dump these versions because the ROMs were not available: {roms}'.format(
            roms=', '.join(missing_versions)))
        exit(1)
    else:
        if args.write_moves:
            write_moves(out_moves)
        if args.write_contest_effects:
            write_contest_effects(out_contest_effects)
        if args.write_items:
            write_items(out_items)
        if args.write_shops:
            write_shops(out_shops)
        if args.write_shop_items:
            write_shop_items(dumped_version_groups, out_shop_items)
        if args.write_abilities:
            write_abilities(out_abilities)
        if args.write_pokemon:
            write_pokemon(out_pokemon)
        if args.write_pokemon_moves:
            write_pokemon_moves(dumped_version_groups, out_pokemon_moves)
        if args.write_encounters:
            write_encounters(dumped_versions, out_encounters)
        exit(0)
