# Contributing to fastapi-refine

Thank you for your interest in contributing to fastapi-refine! This document provides guidelines for contributing.

## Development Setup

1. Clone the repository:
```bash
git clone https://github.com/koch3092/fastapi-refine.git
cd fastapi-refine
```

2. Install dependencies with uv:
```bash
# Install uv if you haven't already
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create virtual environment and install dependencies
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
uv pip install -e ".[dev]"
```

## Code Quality

Before submitting a pull request, ensure your code passes all checks:

```bash
# Format code
ruff format .

# Run linter
ruff check .

# Run type checker
mypy .

# Run tests (when available)
pytest
```

## Development Workflow

1. Create a new branch for your feature or fix:
```bash
git checkout -b feature/your-feature-name
```

2. Make your changes and commit with descriptive messages:
```bash
git commit -m "Add feature: description of feature"
```

3. Push to your fork and submit a pull request:
```bash
git push origin feature/your-feature-name
```

## Pull Request Guidelines

- Keep pull requests focused on a single feature or fix
- Include tests for new functionality
- Update documentation as needed
- Follow the existing code style
- Write clear commit messages
- Update CHANGELOG.md with your changes

## Code Style

- Follow PEP 8 guidelines
- Use type hints for all function parameters and return values
- Write docstrings for all public APIs
- Keep functions small and focused
- Use meaningful variable names

## Testing

When tests are added to the project, please ensure:
- All existing tests pass
- New features include appropriate tests
- Tests are clear and well-documented

## Reporting Issues

When reporting issues, please include:
- Python version
- fastapi-refine version
- Minimal reproducible example
- Expected behavior vs actual behavior
- Any relevant error messages or stack traces

## Questions?

Feel free to open an issue for any questions about contributing!
