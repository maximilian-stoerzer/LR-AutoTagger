VERSION := $(shell grep '^version' backend/pyproject.toml | head -1 | sed 's/.*"\(.*\)"/\1/')

.PHONY: all clean release-plugin release-backend

all: release-plugin release-backend

clean:
	rm -rf release

release-plugin:
	@bash scripts/build-plugin.sh $(VERSION)

release-backend:
	@bash scripts/build-backend.sh $(VERSION)
