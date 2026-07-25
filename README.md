# FolderScribe

A supervised, physical file organizer for Ubuntu 24.04.

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### Run checks

```bash
pytest
ruff check .
ruff format --check .
mypy src
```

### Run the CLI

```bash
folderscribe
```
