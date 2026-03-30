.PHONY: help image test-image image-ai test-image-ai test-local test-all test-clean teaser package-lock _copy-skills

PLAYWRIGHT_VERSION ?= v1.58.2

help:
	@echo "Available targets:"
	@echo "  image                             Build lean production image (no AI tools) (localhost/check_cep:latest + :$(PLAYWRIGHT_VERSION))"
	@echo "  test-image                        Build lean test image (no AI tools)"
	@echo "  image-ai                          Build AI-enhanced production image (Gemini, playwright-cli, skills) (localhost/check_cep:ai-latest + :ai-$(PLAYWRIGHT_VERSION))"
	@echo "  test-image-ai                     Build AI-enhanced test image (check_cep:test-ai)"
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
		--target base \
		-t localhost/check_cep:$(PLAYWRIGHT_VERSION) \
		-t localhost/check_cep:latest \
		src/container/

test-image:
	podman build \
		--build-arg PLAYWRIGHT_VERSION=$(PLAYWRIGHT_VERSION) \
		--target base \
		-t check_cep:test \
		src/container/

image-ai: _copy-skills
	podman build \
		--build-arg PLAYWRIGHT_VERSION=$(PLAYWRIGHT_VERSION) \
		-t localhost/check_cep:ai-$(PLAYWRIGHT_VERSION) \
		-t localhost/check_cep:ai-latest \
		src/container/; \
	ret=$$?; rm -rf src/container/.agents-skills; exit $$ret

test-image-ai: _copy-skills
	podman build \
		--build-arg PLAYWRIGHT_VERSION=$(PLAYWRIGHT_VERSION) \
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
