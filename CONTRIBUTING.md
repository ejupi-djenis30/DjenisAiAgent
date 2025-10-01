# Contributing to DjenisAiAgent

Thank you for your interest in contributing to DjenisAiAgent! This document provides guidelines and instructions for contributing.

## Code of Conduct

Be respectful and constructive in all interactions with the project community.

## How to Contribute

### Reporting Bugs

1. Check if the bug has already been reported in the Issues section
2. If not, create a new issue with:
   - Clear, descriptive title
   - Detailed description of the problem
   - Steps to reproduce
   - Expected vs actual behavior
   - System information (OS version, Python version)
   - Relevant logs or screenshots

### Suggesting Features

1. Check if the feature has already been suggested
2. Create an issue describing:
   - The problem your feature would solve
   - How you envision the feature working
   - Alternative solutions you've considered

### Pull Requests

1. Fork the repository
2. Create a new branch for your feature or bugfix:
   ```bash
   git checkout -b feature/your-feature-name
   ```
3. Make your changes following our coding standards
4. Write or update tests as needed
5. Update documentation as needed
6. Commit your changes with clear, descriptive messages
7. Push to your fork and submit a pull request

## Development Setup

1. Clone the repository:

   ```bash
   git clone https://github.com/ejupi-djenis30/DjenisAiAgent.git
   cd DjenisAiAgent
   ```

2. Create a virtual environment:

   ```bash
   python -m venv venv
   .\venv\Scripts\activate  # On Windows
   ```

3. Install in development mode:

   ```bash
   pip install -e .
   pip install -r requirements.txt
   ```

4. Set up pre-commit hooks (optional but recommended):
   ```bash
   pip install pre-commit
   pre-commit install
   ```

## Coding Standards

### Python Style

- Follow PEP 8 guidelines
- Use type hints where appropriate
- Maximum line length: 100 characters
- Use meaningful variable and function names
- Write docstrings for all public functions, classes, and modules

### Documentation

- Update README.md if adding new features
- Add docstrings to all new functions and classes
- Include inline comments for complex logic
- Update configuration examples if needed

### Testing

- Write unit tests for new functionality
- Ensure all tests pass before submitting PR
- Run tests with: `pytest tests/`
- Aim for good test coverage

### Commit Messages

Follow the conventional commits format:

```
type(scope): brief description

Detailed explanation if needed

Fixes #issue-number
```

Types:

- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting, etc.)
- `refactor`: Code refactoring
- `test`: Adding or updating tests
- `chore`: Maintenance tasks

## Project Structure

```
DjenisAiAgent/
├── src/                    # Source code
│   ├── abstractions/       # Abstract interfaces
│   ├── gemini/             # Gemini AI integration
│   ├── memory/             # Memory components
│   ├── perception/         # Screen analysis
│   ├── planning/           # Task planning
│   ├── tools/              # Action tools
│   └── ui/                 # User interface
├── tests/                  # Test files
├── config/                 # Configuration
├── data/                   # Runtime data (gitignored)
└── docs/                   # Additional documentation
```

## Questions?

If you have questions, feel free to:

- Open an issue for discussion
- Reach out to the maintainers

Thank you for contributing to DjenisAiAgent!
