.PHONY: setup install build test lint format k8s-up k8s-down docker-build-url

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
	docker build -t lynk-url-service:latest ./services/url-service

k8s-up:
	bash scripts/setup-kind-cluster.sh

k8s-down:
	kind delete cluster --name lynk-cluster
