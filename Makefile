.PHONY: setup install build test lint format k8s-up k8s-down k8s-local-deploy docker-build-url docker-build-redirect db-up db-down db-migrate db-migrate-redirect

setup: install
	@echo "==> Setup completed successfully."

install:
	npm install

build:
	npm run build

test:
	npm run test

lint:
	npm run lint

format:
	npm run format

docker-build-url:
	docker build -t lynk-url-service:latest -f services/url-service/Dockerfile .

docker-build-redirect:
	docker build -t lynk-redirect-service:latest -f services/redirect-service/Dockerfile .

db-up:
	docker compose -f infra/docker/docker-compose.yml up -d postgres redirect-postgres redis

db-down:
	docker compose -f infra/docker/docker-compose.yml down

db-migrate:
	npm run build --workspace=@lynk/shared
	npm run build --workspace=@lynk/url-service
	DATABASE_URL=$${DATABASE_URL:-postgres://lynk:lynk_local_only@localhost:5432/lynk_urls} PUBLIC_BASE_URL=$${PUBLIC_BASE_URL:-http://localhost} npm run db:migrate --workspace=@lynk/url-service

db-migrate-redirect:
	npm run build --workspace=@lynk/shared
	npm run build --workspace=@lynk/redirect-service
	DATABASE_URL=$${REDIRECT_DATABASE_URL:-postgres://lynk:lynk_local_only@localhost:5433/lynk_redirects} REDIS_URL=$${REDIS_URL:-redis://localhost:6379} REDIS_PASSWORD=$${REDIS_PASSWORD:-lynk_local_only} URL_SERVICE_BASE_URL=$${URL_SERVICE_BASE_URL:-http://localhost:3001} npm run db:migrate --workspace=@lynk/redirect-service

k8s-up:
	bash scripts/setup-kind-cluster.sh

k8s-local-deploy:
	bash scripts/deploy-local-kind.sh

k8s-down:
	kind delete cluster --name lynk-cluster

.PHONY: docker-build-auth test-sprint3a
docker-build-auth:
	docker build -t lynk-auth-service:latest -f services/auth-service/Dockerfile .

test-sprint3a:
	bash scripts/test-sprint3a.sh
