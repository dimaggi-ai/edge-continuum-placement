.PHONY: test matrix fleet physics figures install validation

test: validation
	python3 -m unittest discover -s tests -v

validation:
	python3 validation.py

matrix:
	python3 -m continuum.cli matrix

fleet:
	python3 -m continuum.cli fleet

physics:
	python3 -m continuum.cli physics --rate 400 --km 600 --buffer-mb 64

figures:
	python3 run.py

install:
	pip install -e ".[figures]"
