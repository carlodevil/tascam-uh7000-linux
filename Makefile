.PHONY: all package test clean

all: package

package:
	./scripts/build-deb.sh

test:
	./scripts/ci-smoke.sh

clean:
	rm -rf .pytest_cache build dist src/*.egg-info
