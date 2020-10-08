#!/bin/bash
set -xe

docker info
docker login -u gitlab-ci-token -p "${CI_JOB_TOKEN}" "${CI_REGISTRY}"

# Try to get the current image
set +e
docker pull "${IMAGE_BASENAME}/db:${CI_COMMIT_BRANCH}"
pull_failed=$?
set -e

apk add --no-cache gcc libc-dev libffi-dev make openssl-dev py-pip python3-dev
pip install docker-compose
if [[ ${CI_COMMIT_MESSAGE} =~ ^.*\[data\] || ${pull_failed} -gt 0 ]]; then
  docker pull "${IMAGE_BASENAME}/app:${CI_COMMIT_BRANCH}"
  docker tag "${IMAGE_BASENAME}/app:${CI_COMMIT_BRANCH}" app:latest
  # Creates an empty database
  DB_TARGET=db_dev docker-compose up --detach db

  # Do the migration
  docker-compose run -T \
    -e DATABASE_URL=postgres://poketools:secret@db:5432/poketools \
    -e POSTGRES_HOST=db \
    -e POSTGRES_USER=poketools \
    -e POSTGRES_PASSWORD=secret \
    -e POSTGRES_DB=poketools \
    -v "${CI_PROJECT_DIR}/docker/db:/var/www/db" \
    app bash /var/www/migrate_data.sh

  # Get artifacts
  cp "${CI_PROJECT_DIR}/docker/db/template.generated.pgdump" "${CI_PROJECT_DIR}/"
  docker-compose down
  docker-compose build db
else
  echo "No data changes, skipping data image build"
  docker tag "${IMAGE_BASENAME}/db:${CI_COMMIT_BRANCH}" db
  docker-compose up --detach db
  docker cp "$(docker-compose ps -q db):/initdb.d/template.generated.pgdump" "${CI_PROJECT_DIR}/"
fi

docker tag db "${IMAGE_BASENAME}/db:${BUILD_NUMBER}"
docker tag db "${IMAGE_BASENAME}/db:${CI_COMMIT_BRANCH}"
docker push "${IMAGE_BASENAME}/db:${BUILD_NUMBER}"
docker push "${IMAGE_BASENAME}/db:${CI_COMMIT_BRANCH}"

exit 0
