<?php

namespace App\Repository;

use App\Entity\MoveFlag;
use Doctrine\Bundle\DoctrineBundle\Repository\ServiceEntityRepository;
use Symfony\Bridge\Doctrine\RegistryInterface;

/**
 * @method MoveFlag|null find($id, $lockMode = null, $lockVersion = null)
 * @method MoveFlag|null findOneBy(array $criteria, array $orderBy = null)
 * @method MoveFlag[]    findAll()
 * @method MoveFlag[]    findBy(array $criteria, array $orderBy = null, $limit = null, $offset = null)
 */
class MoveFlagRepository extends ServiceEntityRepository
{
    public function __construct(RegistryInterface $registry)
    {
        parent::__construct($registry, MoveFlag::class);
    }

//    /**
//     * @return MoveFlag[] Returns an array of MoveFlag objects
//     */
    /*
    public function findByExampleField($value)
    {
        return $this->createQueryBuilder('m')
            ->andWhere('m.exampleField = :val')
            ->setParameter('val', $value)
            ->orderBy('m.id', 'ASC')
            ->setMaxResults(10)
            ->getQuery()
            ->getResult()
        ;
    }
    */

    /*
    public function findOneBySomeField($value): ?MoveFlag
    {
        return $this->createQueryBuilder('m')
            ->andWhere('m.exampleField = :val')
            ->setParameter('val', $value)
            ->getQuery()
            ->getOneOrNullResult()
        ;
    }
    */
}