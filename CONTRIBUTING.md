# Contributing to SweetSuite

This document provides guidelines for contributing to the project.

## How can I contribute?

### Reporting bugs

Before creating bug reports, please check existing issues to avoid duplicates. When creating a bug report, include as many details as possible:

- **Use a clear and descriptive title.**
- **Describe the exact steps to reproduce the problem.**
- **Provide specific examples** (sample files, screenshots, etc.).
- **Describe the behavior you observed** and what you expected to see.
- **Include details about your environment**:
  - OS version (Windows, macOS, Linux)
  - SweetSuite version
  - When running via the `.bat` file: Python version and package versions.

### Suggesting enhancements

Enhancement suggestions are welcome! Please provide:

- **A clear and descriptive title.**
- **A detailed description of the proposed functionality.**
- **Explain why this enhancement would be useful.**
- **List any alternative solutions or features you've considered.**

### Pull requests

1. **Fork the repository** and create your branch from `main`.
2. **Follow the existing code style** and conventions.
3. **Add tests** if you're adding new functionality.
4. **Update documentation** to reflect your changes.
5. **Ensure all tests pass** before submitting.
6. **Write clear commit messages** describing what and why.

#### Pull request process

1. Update the README.md with details of changes if needed.
2. Update the CHANGELOG.md following the existing format.
3. The PR will be merged once reviewed and approved.

## Development setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/stainawarijar/SweetSuite.git
   cd SweetSuite
   ```

2. **Create a virtual environment**
   ```bash
   py -3.14 -m venv venv
   venv\Scripts\activate  # On Windows (CMD)
   # or
   source venv/Scripts/activate  # On Windows (Git Bash / MinGW)
   # or
   source venv/bin/activate  # On macOS/Linux
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Run the application**
   ```bash
   py -3.14 main.py
   ```

## Coding Conventions

- Follow [PEP 8](https://pep8.org/) style guidelines for Python code.
- Use meaningful variable and function names.
- Add docstrings to functions and classes.
- Keep functions focused and concise.
- Add comments for complex logic.

## Testing

- Add tests for new features in the `tests/` directory.
- Ensure existing tests pass before submitting a pull request.
- Aim for good test coverage of new code.

## Questions?

Feel free to open an issue with your question or reach out to the maintainers.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
