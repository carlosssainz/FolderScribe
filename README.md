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

## Documentation

The documentation site lives in `docs/` and is built with Fumadocs (Next.js).

```bash
cd docs
npm install
npm run dev
```

Open http://localhost:3000 in your browser.

### Build

```bash
cd docs
npm run build
npm run start
```
