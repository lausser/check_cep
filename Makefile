.PHONY: help check-versions image test-image image-ai test-image-ai test-local test-all test-clean teaser package-lock _copy-skills

# Single source of the Playwright version and base digest (spec 024).
include src/container/versions.env
CEP_VERSION := $(shell cat VERSION)
VCS_REF := $(shell git rev-parse HEAD)$(if $(shell git status --porcelain),-dirty)
BUILD_DATE := $(shell date -u +%Y-%m-%dT%H:%M:%SZ)
OPENCODE_VERSION ?= 1.18.4

BUILD_ARGS = \
	--build-arg PLAYWRIGHT_VERSION=$(PLAYWRIGHT_VERSION) \
	--build-arg PLAYWRIGHT_BASE_DIGEST=$(PLAYWRIGHT_BASE_DIGEST) \
	--build-arg CEP_VERSION=$(CEP_VERSION) \
	--build-arg VCS_REF=$(VCS_REF) \
	--build-arg BUILD_DATE=$(BUILD_DATE)

help:
	@echo "Available targets:"
	@echo "  image                             Build lean production image (no AI tools) (localhost/check_cep:latest, :$(CEP_VERSION), :v$(PLAYWRIGHT_VERSION))"
	@echo "  test-image                        Build lean test image (no AI tools)"
	@echo "  image-ai                          Build AI-enhanced production image (opencode, playwright-cli, skills) (localhost/check_cep:ai-latest + :ai-v$(PLAYWRIGHT_VERSION))"
	@echo "  test-image-ai                     Build AI-enhanced test image (check_cep:test-ai)"
	@echo "  check-versions                    Check VERSION/CEP_VERSION and the Playwright pins agree (runs before every image build)"
	@echo "  test-local                        Run tests without external services (fast)"
	@echo "  test-all                          Run full suite (requires podman-compose stack)"
	@echo "  test-clean                        Tear down the podman-compose stack"
	@echo "  teaser                            Generate docs/teaser.gif from a real test run"
	@echo "  package-lock                      Regenerate src/container/package-lock.json from package.json"
	@echo ""
	@echo "Release $(CEP_VERSION), Playwright $(PLAYWRIGHT_VERSION) (src/container/versions.env; upgrade procedure in RELEASING.md)"
	@echo "Override opencode CLI version: make image-ai OPENCODE_VERSION=1.18.4"

check-versions:
	python3 scripts/check-versions.py

image: check-versions
	podman build \
		$(BUILD_ARGS) \
		--target base \
		-t localhost/check_cep:v$(PLAYWRIGHT_VERSION) \
		-t localhost/check_cep:$(CEP_VERSION) \
		-t localhost/check_cep:latest \
		src/container/

test-image: check-versions
	podman build \
		$(BUILD_ARGS) \
		--target base \
		-t check_cep:test \
		src/container/

image-ai: check-versions _copy-skills
	podman build \
		$(BUILD_ARGS) \
		--build-arg OPENCODE_VERSION=$(OPENCODE_VERSION) \
		-t localhost/check_cep:ai-v$(PLAYWRIGHT_VERSION) \
		-t localhost/check_cep:ai-latest \
		src/container/; \
	ret=$$?; rm -rf src/container/.agents-skills; exit $$ret

test-image-ai: check-versions _copy-skills
	podman build \
		$(BUILD_ARGS) \
		--build-arg OPENCODE_VERSION=$(OPENCODE_VERSION) \
		-t check_cep:test-ai \
		src/container/; \
	ret=$$?; rm -rf src/container/.agents-skills; exit $$ret

_copy-skills:
	rm -rf src/container/.agents-skills
	cp -rL .agents/skills src/container/.agents-skills

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
