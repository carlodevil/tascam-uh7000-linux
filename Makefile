.PHONY: all package test clean

all: package

package:
	./scripts/build-deb.sh

test:
	./scripts/ci-smoke.sh

clean:
	rm -rf build dist
