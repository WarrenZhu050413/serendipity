# serendipity Makefile - uv-based automation

.DEFAULT_GOAL := help
.PHONY: help install dev test lint format clean uninstall build publish

help:
	@echo "serendipity - Personal Serendipity Engine"
	@echo ""
	@echo "Available commands:"
	@echo "  make install    Install globally (production, rebuilds each time)"
	@echo "  make dev        Install in editable mode (changes instant)"
	@echo "  make test       Run tests with coverage"
	@echo "  make lint       Run ruff linting"
	@echo "  make format     Format code with ruff"
	@echo "  make clean      Remove build artifacts"
	@echo "  make uninstall  Remove global installation"
	@echo "  make build      Build package for PyPI"
	@echo "  make publish    Publish to PyPI (requires ~/.pypirc)"
	@echo ""
	@echo "Development workflow:"
	@echo "  1. make dev     # Install editable (once)"
	@echo "  2. Edit code    # Changes take effect immediately"
	@echo "  3. make test    # Run tests"
	@echo "  4. make install # When ready for production"

# Production install: clean build, no editable
install: clean
	@echo "Installing serendipity (production mode)..."
	uv cache clean --force
	uv tool install --force .
	@echo "Installed! Run: serendipity --help"

# Development install: editable mode, changes instant
dev: clean
	@echo "Installing serendipity (editable mode)..."
	uv cache clean --force
	uv tool install --force --editable .
	@echo "Installed in editable mode!"
	@echo "   Changes to Python files take effect immediately."

test:
	@echo "Running tests..."
	uv run pytest --cov=serendipity --cov-report=term-missing -v
	@echo "Tests complete"

lint:
	@echo "Linting..."
	uv run ruff check .

format:
	@echo "Formatting..."
	uv run ruff format .

clean:
	@echo "Cleaning build artifacts..."
	rm -rf build/ dist/ *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@echo "Clean"

uninstall:
	@echo "Uninstalling serendipity..."
	uv tool uninstall serendipity || true
	@echo "Uninstalled"

# PyPI publishing
build:
	@echo "Building for PyPI..."
	rm -rf dist/
	uv build
	@echo "Built! Files in dist/"

publish: build
	@echo "Publishing to PyPI..."
	twine upload dist/*
	@echo "Published to PyPI!"
	@echo "   Install with: pip install serendipity"
