<?php

namespace App\Tests\dataschema;


use App\Tests\data\DataFinderTrait;
use App\Tests\data\YamlParserTrait;
use App\Tests\dataschema\Filter\YamlIdentifierExists;

/**
 * Test Item Pocket
 *
 * @group data
 * @group item_pocket
 * @coversNothing
 */
class ItemPocketTest extends DataSchemaTestCase
{
    use DataFinderTrait;
    use YamlParserTrait;

    /**
     * Test data matches schema
     */
    public function testData(): void
    {
        $allData = $this->getData();
        foreach ($allData as $identifier => $yaml) {
            $data = $this->parseYaml($yaml);
            $this->assertDataSchema('item_pocket', $data, $identifier);
        }
    }

    /**
     * @return \Generator
     */
    public function getData(): \Generator
    {
        $finder = $this->getFinderForDirectory('item_pocket');
        $finder->name('*.yaml');

        foreach ($finder as $fileInfo) {
            yield $fileInfo->getFilename() => $fileInfo->getContents();
        }
    }

    /**
     * @inheritDoc
     */
    protected function getFilters(): array
    {
        return [
            'string' => [
                'versionGroupIdentifier' => new YamlIdentifierExists('version_group'),
            ],
        ];
    }
}