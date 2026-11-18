# `make check` runs the pin check and every test inside the pinned check
# image. `make contract-test` runs the container contract test on the host,
# because it needs a container engine. CI runs both with ENGINE=docker.
# `make registry-test` runs the promote step against a registry in $(REGISTRY),
# with real skopeo; CI's registry job starts one.
ENGINE ?= podman
REGISTRY ?= localhost:5000
IMAGE  := app-pipeline-check:local
# In a git worktree, .git points into the main repo's git dir: mount it too.
GITDIR := $(shell git rev-parse --path-format=absolute --git-common-dir 2>/dev/null)
GITMNT := $(if $(filter $(CURDIR)/.git,$(GITDIR)),,$(if $(GITDIR),-v "$(GITDIR)":"$(GITDIR)":ro))

.PHONY: check contract-test registry-test

check:
	@$(ENGINE) build -q -t $(IMAGE) -f tools/check-image/Containerfile tools/check-image >/dev/null
	@$(ENGINE) run --rm --security-opt label=disable -v "$(CURDIR)":/repo:ro $(GITMNT) -w /repo $(IMAGE) \
	  sh -c 'python tools/checks/pins.py && python -m unittest discover -s tests && gitleaks git --no-banner --redact .'

contract-test:
	ENGINE=$(ENGINE) python3 -m unittest discover -s tests -p test_contract.py

registry-test:
	REGISTRY=$(REGISTRY) python3 -m unittest discover -s tests -p test_registry.py
