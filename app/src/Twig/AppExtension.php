<?php

namespace App\Twig;

use Twig\Extension\AbstractExtension;
use Twig\TwigFilter;
use Twig\TwigFunction;

/**
 * App Twig Extension
 */
class AppExtension extends AbstractExtension
{
    public function getFunctions(): array
    {
        return [
            new TwigFunction('version_list', [AppExtensionRuntime::class, 'versionList']),
            new TwigFunction(
                'damage_chart_attacking', [AppExtensionRuntime::class, 'damageChartAttacking'],
                [
                    'needs_environment' => true,
                    'needs_context' => true,
                    'is_safe' => ['html'],
                ]
            ),
            new TwigFunction(
                'damage_chart_defending', [AppExtensionRuntime::class, 'damageChartDefending'],
                [
                    'needs_environment' => true,
                    'needs_context' => true,
                    'is_safe' => ['html'],
                ]
            ),
            new TwigFunction(
                'label_item', [AppExtensionRuntime::class, 'itemLabel'],
                [
                    'needs_context' => true,
                    'is_safe' => ['html'],
                ]
            ),
        ];
    }

    public function getFilters(): array
    {
        return [
            new TwigFilter(
                'type_emblem', [AppExtensionRuntime::class, 'typeEmblem'], [
                    'needs_environment' => true,
                    'needs_context' => true,
                    'is_safe' => ['html'],
                ]
            ),
            new TwigFilter(
                'type_efficacy', [AppExtensionRuntime::class, 'typeEfficacy'], [
                    'needs_environment' => true,
                    'is_safe' => ['html'],
                ]
            ),
        ];
    }
}
