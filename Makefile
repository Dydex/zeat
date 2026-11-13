.PHONY: build test refresh verify

build:
	python3 -m zeat build

test:
	python3 -m unittest

refresh:
	python3 -m zeat refresh
	python3 -m zeat build

verify:
	python3 -m zeat verify
