.PHONY: build test refresh verify

build:
	python3 -m moat build

test:
	python3 -m unittest

refresh:
	python3 -m moat refresh
	python3 -m moat build

verify:
	python3 -m moat verify
