import argparse
from pathlib import Path

from gen3_gc import strings
from gen3_gc.abilities import get_abilities, write_abilities
from gen3_gc.items import get_items, update_machines, write_items
from gen3_gc.pokemon import get_pokemon, write_pokemon, write_pokemon_moves
from gen3_gc.shops import get_shop_items, write_shop_items
from inc import group_by_version_group, group_pokemon
from .enums import Version
from .moves import get_moves, write_moves

if __name__ == '__main__':
    strings.register_codec()


    def to_path(path: str):
        return Path(path)


    # Get config
    argparser = argparse.ArgumentParser(description='Load Colosseum/XD data')
    argparser.add_argument('--colosseum_dir', type=to_path, required=True, help='Colosseum directory')
    argparser.add_argument('--xd_dir', type=to_path, required=True, help='XD directory')
    argparser.add_argument('--version', action='append', type=lambda version: Version(version),
                           choices=list(Version), help='Version slug to dump')

    argparser.add_argument('--out-pokemon', type=to_path, required=True, help='Pokemon YAML file dir')
    argparser.add_argument('--out-pokemon_moves', type=to_path, required=True, help='Pokemon Move CSV file')
    argparser.add_argument('--out-moves', type=to_path, required=True, help='Move YAML file dir')
    argparser.add_argument('--out-contest_effects', type=to_path, required=True, help='Contest Effect YAML file dir')
    argparser.add_argument('--out-items', type=to_path, required=True, help='Item YAML file dir')
    argparser.add_argument('--out-shop_items', type=to_path, required=True, help='Shop Data CSV file')
    argparser.add_argument('--out-locations', type=to_path, required=True, help='Location YAML file dir')
    argparser.add_argument('--out-encounters', type=to_path, required=True, help='Encounter CSV file')
    argparser.add_argument('--out-abilities', type=to_path, required=True, help='Ability YAML file dir')

    argparser.add_argument('--write-pokemon', action='store_true', help='Write Pokemon data')
    argparser.add_argument('--write-pokemon_moves', action='store_true', help='Write Pokemon move data')
    argparser.add_argument('--write-moves', action='store_true', help='Write Move data')
    argparser.add_argument('--write-contest_effects', action='store_true', help='Write Contest Effect data')
    argparser.add_argument('--write-items', action='store_true', help='Write Item data')
    argparser.add_argument('--write-shops', action='store_true', help='Write Shop data')
    argparser.add_argument('--write-shop_items', action='store_true', help='Write Shop items')
    argparser.add_argument('--write-encounters', action='store_true', help='Write Encounter data')
    argparser.add_argument('--write-abilities', action='store_true', help='Write Ability data')
    args = argparser.parse_args()

    paths = {
        Version.COLOSSEUM: args.colosseum_dir,
        Version.XD: args.xd_dir,
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

    for version in args.version:
        dump_path = paths[version]
        print('Using version {version}'.format(version=version.value))

        vg_moves, vg_move_slugs = get_moves(dump_path, version, args.out_moves)
        out_moves = group_by_version_group(version.value, vg_moves, out_moves)

        vg_items, vg_item_slugs = get_items(dump_path, version, args.out_items)
        vg_items = update_machines(dump_path, version, vg_items, vg_move_slugs)
        out_items = group_by_version_group(version.value, vg_items, out_items)

        out_shop_items.extend(get_shop_items(dump_path, version, vg_item_slugs, vg_items))

        vg_abilities, vg_ability_slugs = get_abilities(dump_path, version, args.out_abilities)
        out_abilities = group_by_version_group(version.value, vg_abilities, out_abilities)

        vg_species, vg_pokemon_moves, vg_species_slugs, vg_pokemon_slugs = \
            get_pokemon(dump_path, version, args.out_pokemon, vg_ability_slugs, vg_item_slugs, vg_move_slugs, vg_items)
        out_pokemon = group_pokemon(version.value, version.value, vg_species, out_pokemon)
        out_pokemon_moves.update(vg_pokemon_moves)

        dumped_versions.add(version.value)

    if len(dumped_versions) < len(args.version):
        # Didn't dump all requested versions
        missing_versions = []
        for requested_version in args.version:
            if requested_version not in dumped_versions:
                missing_versions.append(requested_version)
        print('Could not dump these versions because the files were not available: {versions}'.format(
            versions=', '.join(missing_versions)))
        exit(1)
    else:
        if args.write_moves:
            write_moves(out_moves, args.out_moves)
        if args.write_items:
            write_items(out_items, args.out_items)
        if args.write_shop_items:
            write_shop_items(dumped_versions, out_shop_items, args.out_shop_items)
        if args.write_abilities:
            write_abilities(out_abilities, args.out_abilities)
        if args.write_pokemon:
            write_pokemon(out_pokemon, args.out_pokemon)
        if args.write_pokemon_moves:
            write_pokemon_moves(dumped_versions, out_pokemon_moves, args.out_pokemon_moves)
        exit(0)
