#!/bin/bash
# Run linting and formatting checks

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== Running linting checks ===${NC}\n"

# Parse command line arguments
FIX=false
CHECK_ONLY=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --fix)
            FIX=true
            shift
            ;;
        --check)
            CHECK_ONLY=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--fix] [--check]"
            echo "  --fix    Automatically fix issues"
            echo "  --check  Only check, don't modify files"
            exit 1
            ;;
    esac
done

# Ensure dependencies are installed
echo -e "${YELLOW}Installing lint dependencies...${NC}"
uv pip install --group lint

# Run black
echo -e "\n${YELLOW}Running black (code formatter)...${NC}"
if [ "$FIX" = true ]; then
    uv run black src/ tests/
    echo -e "${GREEN}✓ Code formatted${NC}"
elif [ "$CHECK_ONLY" = true ]; then
    if uv run black --check src/ tests/; then
        echo -e "${GREEN}✓ Code formatting is correct${NC}"
    else
        echo -e "${RED}✗ Code formatting issues found${NC}"
        echo -e "${YELLOW}Run './scripts/lint.sh --fix' to fix${NC}"
        exit 1
    fi
else
    if uv run black --check --diff src/ tests/; then
        echo -e "${GREEN}✓ Code formatting is correct${NC}"
    else
        echo -e "${RED}✗ Code formatting issues found${NC}"
        echo -e "${YELLOW}Run './scripts/lint.sh --fix' to fix${NC}"
        exit 1
    fi
fi

# Run ruff
echo -e "\n${YELLOW}Running ruff (linter)...${NC}"
if [ "$FIX" = true ]; then
    uv run ruff check --fix src/ tests/
    echo -e "${GREEN}✓ Linting issues fixed${NC}"
else
    if uv run ruff check src/ tests/; then
        echo -e "${GREEN}✓ No linting issues${NC}"
    else
        echo -e "${RED}✗ Linting issues found${NC}"
        echo -e "${YELLOW}Run './scripts/lint.sh --fix' to fix${NC}"
        exit 1
    fi
fi

echo -e "\n${GREEN}=== Linting checks completed ===${NC}"
