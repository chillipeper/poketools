<?php

namespace App\DataMigration\Veekun;

use Doctrine\DBAL\Driver\Statement;
use Doctrine\DBAL\FetchMode;
use DragoonBoots\A2B\Annotations\DataMigration;
use DragoonBoots\A2B\Annotations\IdField;
use DragoonBoots\A2B\DataMigration\AbstractDataMigration;
use DragoonBoots\A2B\DataMigration\DataMigrationInterface;
use DragoonBoots\A2B\Drivers\Destination\YamlDestinationDriver;
use DragoonBoots\A2B\Drivers\DestinationDriverInterface;
use DragoonBoots\A2B\Drivers\Source\DbalSourceDriver;
use DragoonBoots\A2B\Drivers\SourceDriverInterface;

/**
 * Item migration.
 *
 * @DataMigration(
 *     name="Item",
 *     group="Veekun",
 *     source="veekun",
 *     sourceIds={@IdField(name="id")},
 *     destination="yaml:///%kernel.project_dir%/resources/data/item",
 *     destinationIds={@IdField(name="identifier", type="string")}
 * )
 */
class Item extends AbstractDataMigration implements DataMigrationInterface
{

    /**
     * @var Statement
     */
    protected $flavorTextData;

    /**
     * @var Statement
     */
    protected $berryData;

    /**
     * @var Statement
     */
    protected $berryFlavorData;

    /**
     * @var Statement
     */
    protected $machineData;

    /**
     * Map of version group identifiers to their sort order.
     *
     * @var array
     */
    protected $versionGroupSort = [];

    /**
     * Version groups with the move "fling"
     *
     * @var string[]
     */
    protected $flingVersionGroups = [];

    /**
     * Version groups with HMs
     *
     * @var string[]
     */
    protected $hmVersionGroups = [];

    /**
     * {@inheritdoc}
     * @param DbalSourceDriver $sourceDriver
     */
    public function configureSource(SourceDriverInterface $sourceDriver)
    {
        $sourceDriver->setStatement(
            <<<SQL
SELECT "items"."id",
       "items"."identifier",
       group_concat(DISTINCT "version_groups"."identifier") AS "version_groups",
       "item_names"."name",
       "item_categories"."identifier" AS "category",
       nullif("items"."cost", 0) AS "buy",
       nullif("items"."cost"/ 2, 0) AS "sell",
       "item_fling_effects"."identifier" AS "fling_effect",
       "items"."fling_power",
       group_concat(DISTINCT "item_flags"."identifier") AS "flags",
       CASE
           WHEN "machines"."item_id" IS NULL
               THEN "item_prose"."short_effect"
       END AS "short_description",
       CASE
           WHEN "machines"."item_id" IS NULL
               THEN "item_prose"."effect"
       END AS "description",
       ("berries"."id" IS NOT NULL) AS "is_berry",
       ("machines"."item_id" IS NOT NULL) AS "is_machine"
FROM "items"
     JOIN "item_names"
          ON "items"."id" = "item_names"."item_id"
     JOIN "item_categories"
          ON "items"."category_id" = "item_categories"."id"
     LEFT OUTER JOIN "item_fling_effects"
                     ON "items"."fling_effect_id" = "item_fling_effects"."id"
     LEFT OUTER JOIN "item_prose"
                     ON "items"."id" = "item_prose"."item_id"
     LEFT OUTER JOIN "item_game_indices"
                     ON "items"."id" = "item_game_indices"."item_id"
     LEFT OUTER JOIN "version_groups"
                     ON "item_game_indices"."generation_id" = "version_groups"."generation_id"
     LEFT OUTER JOIN "item_flag_map"
                     ON "items"."id" = "item_flag_map"."item_id"
     LEFT OUTER JOIN "item_flags"
                     ON "item_flag_map"."item_flag_id" = "item_flags"."id"
     LEFT OUTER JOIN "berries"
                     ON "items"."id" = "berries"."item_id"
     LEFT OUTER JOIN "machines"
                     ON "items"."id" = "machines"."item_id"
WHERE "item_names"."local_language_id" = 9
  AND ("item_prose"."local_language_id" = 9 OR "item_prose"."local_language_id" IS NULL)
GROUP BY "items"."id";
SQL
        );

        $sourceDriver->setCountStatement(
            <<<SQL
SELECT count(*)
FROM "items";
SQL
        );

        $this->flavorTextData = $sourceDriver->getConnection()->prepare(
            <<<SQL
SELECT "version_groups"."identifier" AS "version_group",
       "item_flavor_text"."flavor_text"
FROM "items"
     JOIN "item_flavor_text"
          ON "items"."id" = "item_flavor_text"."item_id"
     JOIN "version_groups"
          ON "item_flavor_text"."version_group_id" = "version_groups"."id"
WHERE "item_flavor_text"."language_id" = 9
  AND "items"."id" = :item
SQL
        );

        $this->berryData = $sourceDriver->getConnection()->prepare(
            <<<SQL
SELECT "berry_firmness"."identifier" AS "firmness",
       "types"."identifier" AS "natural_gift_type",
       "berries"."natural_gift_power",
       "berries"."size",
       1 AS "harvest_min",
       "berries"."max_harvest" AS "harvest_max",
       "berries"."growth_time",
       "berries"."soil_dryness" AS "water",
       "berries"."smoothness"
FROM "berries"
     JOIN "berry_firmness"
          ON "berries"."firmness_id" = "berry_firmness"."id"
     JOIN "types"
          ON "berries"."natural_gift_type_id" = "types"."id"
WHERE "item_id" = :item
SQL
        );

        $this->berryFlavorData = $sourceDriver->getConnection()->prepare(
            <<<SQL
SELECT lower("contest_type_names"."flavor") AS "flavor",
       "berry_flavors"."flavor" AS "level"
FROM "berry_flavors"
     JOIN "berries"
          ON "berry_flavors"."berry_id" = "berries"."id"
     JOIN "contest_types"
          ON "berry_flavors"."contest_type_id" = "contest_types"."id"
     JOIN "contest_type_names"
          ON "contest_types"."id" = "contest_type_names"."contest_type_id"
WHERE "berries"."item_id" = :item
  AND "contest_type_names"."local_language_id" = 9;
SQL
        );

        $this->machineData = $sourceDriver->getConnection()->prepare(
            <<<SQL
SELECT "version_groups"."identifier" AS "version_group",
       CASE
           WHEN "machines"."machine_number" > 100
               THEN 'HM'
           ELSE 'TM'
       END AS "type",
       CASE
           WHEN "machines"."machine_number" > 100
               THEN "machines"."machine_number" - 100
           ELSE "machines"."machine_number"
       END AS "number",
       "moves"."identifier" AS "move"
FROM "items"
     JOIN "machines"
          ON "items"."id" = "machines"."item_id"
     JOIN "version_groups"
          ON "machines"."version_group_id" = "version_groups"."id"
     JOIN "moves"
          ON "machines"."move_id" = "moves"."id"
WHERE "items"."id" = :item
SQL
        );

        $versionGroupSort = $sourceDriver->getConnection()->prepare(
            <<<SQL
SELECT "version_groups"."identifier", "version_groups"."order"
FROM "version_groups"
SQL
        );
        $versionGroupSort->execute();
        foreach ($versionGroupSort as $row) {
            $this->versionGroupSort[$row['identifier']] = (int)$row['order'];
        }

        $flingVersionGroups = $sourceDriver->getConnection()->prepare(
            <<<SQL
SELECT "version_groups"."identifier"
FROM "version_groups"
WHERE "version_groups"."generation_id" >= 4;
SQL
        );
        $flingVersionGroups->execute();
        $this->flingVersionGroups = $flingVersionGroups->fetchAll(FetchMode::COLUMN);

        $hmVersionGroups = $sourceDriver->getConnection()->prepare(
            <<<SQL
SELECT "version_groups"."identifier"
FROM "version_groups"
WHERE "generation_id" < 7;
SQL
        );
        $hmVersionGroups->execute();
        $this->hmVersionGroups = $hmVersionGroups->fetchAll(FetchMode::COLUMN);
    }

    /**
     * {@inheritdoc}
     */
    public function transform($sourceData, $destinationData)
    {
        $itemId = $sourceData['id'];
        unset($sourceData['id']);
        $destinationData['identifier'] = $sourceData['identifier'];
        unset($sourceData['identifier']);

        $versionGroups = explode(',', $sourceData['version_groups']);
        usort(
            $versionGroups,
            function (string $a, string $b) {
                return $this->versionGroupSort[$a] - $this->versionGroupSort[$b];
            }
        );
        unset($sourceData['version_groups']);

        if (isset($sourceData['flags'])) {
            $sourceData['flags'] = array_merge(explode(',', $sourceData['flags']), $destinationData['flags'] ?? []);
        }

        if ($sourceData['is_berry']) {
            $this->berryData->execute(['item' => $itemId]);
            $sourceData['berry'] = array_merge(
                $this->berryData->fetch(FetchMode::ASSOCIATIVE),
                $destinationData['berry'] ?? []
            );
            $this->berryFlavorData->execute(['item' => $itemId]);
            $sourceData['berry']['flavors'] = $this->berryFlavorData->fetchAll(FetchMode::ASSOCIATIVE);
            $sourceData['berry']['flavors'] = array_combine(array_column($sourceData['berry']['flavors'], 'flavor'), array_column($sourceData['berry']['flavors'], 'level'));
            $sourceData['berry']['flavors'] = $this->convertToInts($sourceData['berry']['flavors'], array_keys($sourceData['berry']['flavors']));

            $sourceData['berry']['harvest'] = $this->buildRangeString($sourceData['berry']['harvest_min'], $sourceData['berry']['harvest_max']);
            unset($sourceData['berry']['harvest_min'], $sourceData['berry']['harvest_max']);

            $berryIntFields = [
                'natural_gift_power',
                'size',
                'growth_time',
                'water',
                'smoothness',
            ];
            $sourceData['berry'] = $this->convertToInts($sourceData['berry'], $berryIntFields);
        }
        unset($sourceData['is_berry']);

        if ($sourceData['is_machine']) {
            $this->machineData->execute(['item' => $itemId]);
            $machineData = $this->arrayKeyBy($this->machineData->fetchAll(FetchMode::ASSOCIATIVE), 'version_group');
            $flavorTextData = [];
        } else {
            $machineData = null;
            $flavorTextData = $this->arrayKeyBy($this->flavorTextData->fetchAll(FetchMode::ASSOCIATIVE), 'version_group');
        }
        unset($sourceData['is_machine']);
        $this->flavorTextData->execute(['item' => $itemId]);

        // Veekun is missing a lot of flavor text; make some substitutions if
        // it makes sense.
        if (!isset($flavorTextData['omega-ruby-alpha-sapphire'])
            && isset($flavorTextData['x-y'])
            && in_array('omega-ruby-alpha-sapphire', $versionGroups)
            && in_array('x-y', $versionGroups)) {
            $flavorTextData['omega-ruby-alpha-sapphire'] = $flavorTextData['x-y'];
        }
        if (!isset($flavorTextData['colosseum'])
            && isset($flavorTextData['ruby-sapphire'])
            && in_array('colosseum', $versionGroups)
            && in_array('ruby-sapphire', $versionGroups)) {
            $flavorTextData['colosseum'] = $flavorTextData['ruby-sapphire'];
        }
        if (!isset($flavorTextData['xd'])
            && isset($flavorTextData['ruby-sapphire'])
            && in_array('xd', $versionGroups)
            && in_array('ruby-sapphire', $versionGroups)) {
            $flavorTextData['xd'] = $flavorTextData['ruby-sapphire'];
        }

        // Take the machine category from the identifier to be more specific.
        if ($sourceData['category'] == 'all-machines') {
            $sourceData['category'] = substr($destinationData['identifier'], 0, 2);
        }

        // If there is a listed fling power and no special effect, force a
        // generic "deals damage" effect to be used.
        if (isset($sourceData['fling_power']) && !isset($sourceData['fling_effect'])) {
            $sourceData['fling_effect'] = 'damage';
        }

        $intFields = [
            'buy',
            'sell',
            'fling_power',
        ];
        $sourceData = $this->removeNulls($sourceData);
        $sourceData = $this->convertToInts($sourceData, $intFields);

        foreach ($versionGroups as $versionGroup) {
            // Because Veekun does not have complete version group info for
            // items, if the version group is set to false in the YAML, it means
            // the file has been edited manually to declare that item does not
            // appear in that version group, regardless of what Veekun thinks.
            // This is ugly and should be removed if Veekun figures it out.
            if (isset($destinationData[$versionGroup]) && $destinationData[$versionGroup] === false) {
                continue;
            }

            // Do not insert data if this is an HM and this version group does
            // not have HMs.
            if (isset($machineData[$versionGroup])) {
                if ($machineData[$versionGroup]['type'] == 'HM' && !in_array($versionGroup, $this->hmVersionGroups)) {
                    continue;
                }
            }

            $versionGroupSourceData = $sourceData;

            // Remove fling info if this version group doesn't have fling.
            if (!in_array($versionGroup, $this->flingVersionGroups)) {
                unset($versionGroupSourceData['fling_effect'], $versionGroupSourceData['fling_power']);
            }

            // Remove berry water info from Gen 7 games
            if (isset($versionGroupSourceData['berry'])
                && in_array(
                    $versionGroup, ['sun-moon', 'ultra-sun-ultra-moon']
                )) {
                unset($versionGroupSourceData['berry']['water']);
            }

            $destinationData[$versionGroup] = array_merge($versionGroupSourceData, $destinationData[$versionGroup] ?? []);
            if (!isset($destinationData[$versionGroup]['flavor_text']) && isset($flavorTextData[$versionGroup])) {
                $destinationData[$versionGroup]['flavor_text'] = $flavorTextData[$versionGroup]['flavor_text'];
            }
            if (isset($machineData[$versionGroup])) {
                $machineData[$versionGroup]['number'] = (int)$machineData[$versionGroup]['number'];
                $destinationData[$versionGroup]['machine'] = array_merge($machineData[$versionGroup], $destinationData[$versionGroup]['machine'] ?? []);
            }
        }

        return $destinationData;
    }

    /**
     * Modify the array to be keyed by the given column.
     *
     * All values of the column must be a valid array key (i.e. a string or int).
     *
     * @param array      $array
     * @param int|string $key
     *
     * @return array
     */
    protected function arrayKeyBy(array $array, $key)
    {
        $new = [];
        foreach ($array as &$item) {
            $keyValue = $item[$key];
            unset($item[$key]);

            $new[$keyValue] = $item;
        }
        unset($array);

        return $new;
    }

    /**
     * {@inheritdoc}
     * @param YamlDestinationDriver $destinationDriver
     */
    public function configureDestination(DestinationDriverInterface $destinationDriver)
    {
        $destinationDriver->setOption(
            'refs', [
                'exclude' => [
                    '`^.+\.(?:fling_.+|berry\..+)`',
                ],
            ]
        );
    }
}