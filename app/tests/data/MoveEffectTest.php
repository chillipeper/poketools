<?php

namespace App\Tests\data;

use Generator;

/**
 * Test Ability data
 *
 * @group data
 * @group location
 * @coversNothing
 */
class MoveEffectTest extends DataTestCase
{
    use DataFinderTrait;
    use YamlParserTrait;

    /**
     * Test descriptions are valid Markdown
     */
    public function testDescription(): void
    {
        $allData = $this->getMoveEffectData();

        $invalidDescriptions = [];
        foreach ($allData as $identifier => $yaml) {
            $data = $this->parseYaml($yaml);

            foreach ($data as $versionGroupSlug => $versionData) {
                $versionGroup = $this->getVersionGroup($versionGroupSlug);
                foreach ($versionGroup->getVersions() as $version) {
                    $converter = $this->getMarkdownConverter(
                        $version->getSlug(),
                        [$identifier, $versionGroupSlug],
                        $invalidDescriptions
                    );
                    self::assertNotEmpty($converter->convertToHtml($versionData['short_description']));
                    self::assertNotEmpty($converter->convertToHtml($versionData['description']));
                }
            }
        }

        self::assertEmpty($invalidDescriptions, "Some descriptions are invalid:\n".implode("\n", $invalidDescriptions));
    }

    /**
     * @return Generator
     */
    public function getMoveEffectData(): Generator
    {
        $finder = $this->getFinderForDirectory('move_effect');
        $finder->name('*.yaml');

        foreach ($finder as $fileInfo) {
            yield $fileInfo->getFilename() => $fileInfo->getContents();
        }
    }
}
