#!/bin/bash
# Run tests with various options

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== Running tina test suite ===${NC}\n"

# Parse command line arguments
COVERAGE=true
VERBOSE_ARGS=()
MARKER_ARGS=()
SPECIFIC_TEST_ARGS=()

while [[ $# -gt 0 ]]; do
    case $1 in
        --no-cov)
            COVERAGE=false
            shift
            ;;
        -v|--verbose)
            VERBOSE_ARGS=(-v)
            shift
            ;;
        -vv)
            VERBOSE_ARGS=(-vv -s)
            shift
            ;;
        --unit)
            MARKER_ARGS=(-m unit)
            shift
            ;;
        --integration)
            MARKER_ARGS=(-m integration)
            shift
            ;;
        --slow)
            MARKER_ARGS=(-m slow)
            shift
            ;;
        --fast)
            MARKER_ARGS=(-m 'not slow')
            shift
            ;;
        *)
            SPECIFIC_TEST_ARGS+=("$1")
            shift
            ;;
    esac
done

# Build pytest command
CMD=(uv run pytest)

if [ "$COVERAGE" = true ]; then
    CMD+=(--cov=src/tina --cov-report=term-missing --cov-report=html --cov-fail-under=10)
else
    CMD+=(--no-cov)
fi

if [ ${#VERBOSE_ARGS[@]} -gt 0 ]; then
    CMD+=("${VERBOSE_ARGS[@]}")
fi

if [ ${#MARKER_ARGS[@]} -gt 0 ]; then
    CMD+=("${MARKER_ARGS[@]}")
fi

if [ ${#SPECIFIC_TEST_ARGS[@]} -gt 0 ]; then
    CMD+=("${SPECIFIC_TEST_ARGS[@]}")
fi

# Run tests
echo -e "${YELLOW}Command: $(printf '%q ' "${CMD[@]}")${NC}\n"
"${CMD[@]}"

# Show coverage report location
if [ "$COVERAGE" = true ]; then
    echo -e "\n${GREEN}Coverage report generated: htmlcov/index.html${NC}"
fi

echo -e "\n${GREEN}=== Tests completed ===${NC}"
