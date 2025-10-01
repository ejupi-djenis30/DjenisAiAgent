# Makefile for DjenisAiAgent
# Note: On Windows, you may need to install Make or use PowerShell alternatives

.PHONY: help install clean test lint format run ui

help:
	@echo "DjenisAiAgent - Available commands:"
	@echo "  make install    - Install dependencies"
	@echo "  make clean      - Clean temporary files and caches"
	@echo "  make test       - Run tests"
	@echo "  make lint       - Run linter"
	@echo "  make format     - Format code"
	@echo "  make run        - Run the agent (CLI)"
	@echo "  make ui         - Run the agent UI"

install:
	pip install -e .
	pip install -r requirements.txt

clean:
	@echo "Cleaning temporary files..."
	@if exist "src\__pycache__" rmdir /s /q "src\__pycache__"
	@if exist "tests\__pycache__" rmdir /s /q "tests\__pycache__"
	@if exist ".pytest_cache" rmdir /s /q ".pytest_cache"
	@if exist "analysis_cache" rmdir /s /q "analysis_cache"
	@if exist "*.egg-info" rmdir /s /q "*.egg-info"
	@if exist "dist" rmdir /s /q "dist"
	@if exist "build" rmdir /s /q "build"
	@echo "Clean complete!"

test:
	pytest tests/ -v

lint:
	@echo "Running linter..."
	flake8 src/ --max-line-length=100 --exclude=__pycache__
	@echo "Linting complete!"

format:
	@echo "Formatting code..."
	black src/ tests/ --line-length=100
	@echo "Formatting complete!"

run:
	python src/main.py

ui:
	python launch_ui.py
