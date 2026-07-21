.PHONY: validate release docs clean

validate:
	python tools/validate_package.py --repo .

release:
	python tools/build_release.py --repo .

check-release:
	python tools/build_release.py --repo . --check

clean:
	rm -rf _build _renders __pycache__ tools/__pycache__
