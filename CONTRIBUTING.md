# E:\Code\Python\weatherbot\CONTRIBUTING.md
# Contributing to Weatherbot

Thank you for your interest in contributing to Weatherbot! This document
provides guidelines and information for contributors.

## Development Setup

1. **Fork and clone the repository**:
   ```bash
   git clone https://github.com/nathanramoscfa/weatherbot.git
   cd weatherbot
   ```

2. **Create a virtual environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install development dependencies**:
   ```bash
   pip install -e .[dev]
   ```

4. **Install pre-commit hooks**:
   ```bash
   pre-commit install
   ```

## Code Style

This project follows PEP 8 and uses several tools to maintain code quality:

- **Black**: Code formatting
- **Ruff**: Linting and import sorting
- **MyPy**: Type checking
- **Pre-commit**: Automated checks

### Running Quality Checks

```bash
# Format code
black src/ tests/

# Lint code
ruff check src/ tests/

# Type check
mypy src/weatherbot

# Run all checks
make format
make lint
```

## Testing

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=weatherbot

# Run specific test file
pytest tests/test_specific.py
```

### Writing Tests

- Place tests in the `tests/` directory
- Use descriptive test names starting with `test_`
- Follow the AAA pattern: Arrange, Act, Assert
- Use fixtures for common setup

## Pull Request Process

1. **Create a feature branch**:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes** following the coding standards

3. **Add tests** for new functionality

4. **Update documentation** if needed

5. **Run all checks**:
   ```bash
   make test
   make lint
   make format
   ```

6. **Commit your changes**:
   ```bash
   git add .
   git commit -m "Add: brief description of changes"
   ```

7. **Push and create a pull request**

## Commit Message Format

Use conventional commit format:

- `feat:` New features
- `fix:` Bug fixes
- `docs:` Documentation changes
- `style:` Code style changes
- `refactor:` Code refactoring
- `test:` Test additions/changes
- `chore:` Maintenance tasks

## Reporting Issues

When reporting issues, please include:

- Python version
- Operating system
- Steps to reproduce
- Expected vs actual behavior
- Error messages/logs

## Code of Conduct

Please be respectful and constructive in all interactions.
