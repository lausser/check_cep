.PHONY: help image test-image test-local test-all test-clean teaser package-lock

PLAYWRIGHT_VERSION ?= v1.58.2

help:
	@echo "Available targets:"
	@echo "  image                             Build production image (localhost/check_cep:latest + :$(PLAYWRIGHT_VERSION))"
	@echo "  test-image                        Build check_cep:test image"
	@echo "  test-local                        Run tests without external services (fast)"
	@echo "  test-all                          Run full suite (requires podman-compose stack)"
	@echo "  test-clean                        Tear down the podman-compose stack"
	@echo "  teaser                            Generate docs/teaser.gif from a real test run"
	@echo "  package-lock                      Regenerate src/container/package-lock.json from package.json"
	@echo ""
	@echo "Override Playwright version: make image PLAYWRIGHT_VERSION=v1.60.0"

image:
	podman build \
		--build-arg PLAYWRIGHT_VERSION=$(PLAYWRIGHT_VERSION) \
		-t localhost/check_cep:$(PLAYWRIGHT_VERSION) \
		-t localhost/check_cep:latest \
		src/container/

test-image:
	podman build \
		--build-arg PLAYWRIGHT_VERSION=$(PLAYWRIGHT_VERSION) \
		-t check_cep:test \
		src/container/

test-local: test-image
	SKIP_INTEGRATION=1 pytest tests/integration/ -v

test-all: test-image
	pytest tests/integration/ -v

test-clean:
	podman-compose -f tests/compose/docker-compose.yml down

teaser: test-image
	bash scripts/generate-teaser.sh

package-lock:
	npm install --package-lock-only --prefix src/container
