<?php

namespace App\DataTable\Type;


use App\DataTable\Adapter\ObjectAdapter;
use App\Entity\Nature;
use App\Entity\Version;
use Omines\DataTablesBundle\DataTable;

/**
 * Pokemon Table for Nature view
 */
class NaturePokemonTableType extends PokemonTableType
{
    /**
     * {@inheritdoc}
     */
    public function configure(DataTable $dataTable, array $options)
    {
        parent::configure($dataTable, $options);

        /** @var Version $version */
        $version = $options['version'];
        /** @var Nature $nature */
        $nature = $options['nature'];

        $dataTable->setName(self::class)->createAdapter(
            ObjectAdapter::class,
            [
                'data' => function (int $start, int $limit) use ($version, $nature) {
                    return $this->pokemonRepo->findMatchingStats(
                        $version,
                        $nature->getStatIncreased(),
                        $nature->getStatDecreased()
                    );
                },
            ]
        );
    }

}