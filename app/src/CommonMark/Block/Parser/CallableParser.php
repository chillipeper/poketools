<?php
/**
 * @file ControllerParser.php
 */

namespace App\CommonMark\Block\Parser;


use App\CommonMark\Block\Element\CallableBlock;
use App\Entity\Version;
use League\CommonMark\Block\Element\HtmlBlock;
use League\CommonMark\Block\Parser\AbstractBlockParser;
use League\CommonMark\ContextInterface;
use League\CommonMark\Cursor;
use Psr\Log\LoggerInterface;
use Symfony\Component\HttpKernel\Controller\ControllerReference;
use Symfony\Component\HttpKernel\Fragment\FragmentHandler;
use Symfony\Component\Serializer\Encoder\JsonEncoder;

/**
 * Allow embedding programmed output in Markdown
 *
 * This allows advanced behavior (e.g. showing a database table) in a Markdown
 * description.
 *
 * The format is:
 * ```
 * {{service::method(json_args)}}
 * ```
 * where `service` is a service id and `json_args` are the controller/route
 * arguments as a JSON dict.
 *
 * The method will receive the given arguments, plus the currently active
 * Version entity as the last argument.
 */
class CallableParser extends AbstractBlockParser
{
    /**
     * The regex for the reference.
     */
    protected const RE_REF = '`{{(?<controller>.+?::.+?)\((?P<args>.+)\)}}`';

    /**
     * @var Version
     */
    protected $version;

    /**
     * @var LoggerInterface
     */
    protected $logger;

    /**
     * @var FragmentHandler
     */
    protected $fragmentHandler;

    /**
     * @var JsonEncoder
     */
    protected $jsonEncoder;

    /**
     * ControllerParser constructor.
     *
     * @param Version $version
     * @param LoggerInterface $logger
     * @param FragmentHandler $fragmentHandler
     * @param JsonEncoder $jsonEncoder
     */
    public function __construct(
        Version $version,
        LoggerInterface $logger,
        FragmentHandler $fragmentHandler,
        JsonEncoder $jsonEncoder
    ) {
        $this->version = $version;
        $this->logger = $logger;
        $this->fragmentHandler = $fragmentHandler;
        $this->jsonEncoder = $jsonEncoder;
    }

    /**
     * {@inheritdoc}
     */
    public function parse(ContextInterface $context, Cursor $cursor)
    {
        $previousState = $cursor->saveState();

        // Match the ref
        $ref = $cursor->match(self::RE_REF);
        if (empty($ref)) {
            $cursor->restoreState($previousState);

            return false;
        }

        preg_match(self::RE_REF, $ref, $parts);
        $controllerName = $parts['controller'];

        try {
            $args = $this->jsonEncoder->decode($parts['args'], 'json', ['json_decode_associative' => true]);
            $args['versionSlug'] = $this->version->getSlug();
            $fragment = new ControllerReference($controllerName, $args);
//            $rendered = trim($this->fragmentHandler->render($fragment));
        } catch (\Exception $e) {
            $this->logger->warning('Could not render "%s": '.$e->getMessage());

            return false;
        }

        $block = new CallableBlock($fragment);

        $context->addBlock($block);
//        $cursor->advanceToNextNonSpaceOrNewline();

        return true;
    }
}