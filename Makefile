.PHONY: all package clean

all: package

package:
	./scripts/build-deb.sh

clean:
	rm -rf build dist
