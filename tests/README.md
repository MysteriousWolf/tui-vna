# Tests

```bash
uv run pytest              # all tests
uv run pytest -m unit      # fast unit tests only
uv run pytest --cov        # with coverage
./scripts/lint.sh --check  # linting
```

**155 passing, 2 skipped**

Structure mirrors `src/tina/`:

- `config/` - Configuration tests
- `drivers/` - Driver tests
- `utils/` - Utility tests
- `fixtures/` - Mock infrastructure
- Root level - Worker and edge cases
