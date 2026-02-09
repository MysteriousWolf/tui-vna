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
VERBOSE=""
MARKERS=""
SPECIFIC_TEST=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --no-cov)
            COVERAGE=false
            shift
            ;;
        -v|--verbose)
            VERBOSE="-v"
            shift
            ;;
        -vv)
            VERBOSE="-vv -s"
            shift
            ;;
        --unit)
            MARKERS="-m unit"
            shift
            ;;
        --integration)
            MARKERS="-m integration"
            shift
            ;;
        --slow)
            MARKERS="-m slow"
            shift
            ;;
        --fast)
            MARKERS="-m 'not slow'"
            shift
            ;;
        *)
            SPECIFIC_TEST="$1"
            shift
            ;;
    esac
done

# Build pytest command
CMD="uv run pytest"

if [ "$COVERAGE" = true ]; then
    CMD="$CMD --cov=src/tina --cov-report=term-missing --cov-report=html"
else
    CMD="$CMD --no-cov"
fi

if [ -n "$VERBOSE" ]; then
    CMD="$CMD $VERBOSE"
fi

if [ -n "$MARKERS" ]; then
    CMD="$CMD $MARKERS"
fi

if [ -n "$SPECIFIC_TEST" ]; then
    CMD="$CMD $SPECIFIC_TEST"
fi

# Run tests
echo -e "${YELLOW}Command: $CMD${NC}\n"
eval $CMD

# Show coverage report location
if [ "$COVERAGE" = true ]; then
    echo -e "\n${GREEN}Coverage report generated: htmlcov/index.html${NC}"
fi

echo -e "\n${GREEN}=== Tests completed ===${NC}"
