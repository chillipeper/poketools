<?php

namespace App\Tests\dataschema;


use App\Tests\Traits\CsvParserTrait;

/**
 * Test Move Damage Class
 *
 * @group data
 * @group move_damage_class
 * @coversNothing
 */
class MoveDamageClassTest extends DataSchemaTestCase
{

    use CsvParserTrait;

    /**
     * Test data matches schema
     *
     * @dataProvider dataProvider
     */
    public function testData(array $row): void
    {
        $this->assertDataSchema('move_damage_class', $row);
    }

    public function dataProvider()
    {
        return $this->buildCsvDataProvider('move_damage_class', 'identifier');
    }

}
