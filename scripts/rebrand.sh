#!/usr/bin/env bash
#
# Rebrand this package to a custom name.
#
# Usage:
#   ./scripts/rebrand.sh <new_name>
#
# Example:
#   ./scripts/rebrand.sh vinbot
#   ./scripts/rebrand.sh adflex
#
# This script:
#   1. Auto-detects the current package name from pyproject.toml
#   2. Renames src/<old>/ → src/<new>/
#   3. Replaces all references in source code, config, and docs
#   4. Shows a summary of what changed
#
# Run from the project root directory.
# Make sure you have committed all changes before running this script.

set -euo pipefail

# --- Validate input ---

if [ $# -ne 1 ]; then
    echo "Usage: $0 <new_name>"
    echo "Example: $0 adflex"
    exit 1
fi

NEW_NAME="$1"

# Validate: must be a valid Python package name (lowercase, underscores, no dashes)
if ! echo "$NEW_NAME" | grep -qE '^[a-z][a-z0-9_]*$'; then
    echo "Error: Package name must start with a letter and contain only lowercase letters, digits, and underscores."
    echo "Got: $NEW_NAME"
    exit 1
fi

# --- Check we're in the right directory ---

if [ ! -f "pyproject.toml" ]; then
    echo "Error: pyproject.toml not found. Run this script from the project root."
    echo "Current directory: $(pwd)"
    exit 1
fi

# --- Auto-detect current package name ---

# Read the CLI entry point line from pyproject.toml: `name = "cli:app"`
# The package name is whatever is before ".cli:app"
OLD_NAME=$(grep -oP '^\s*\w+\s*=\s*"\K[^.]+(?=\.cli:app")' pyproject.toml || true)

if [ -z "$OLD_NAME" ]; then
    echo "Error: Could not detect current package name from pyproject.toml."
    echo "Expected a line like: mypackage = \"mypackage.cli:app\""
    exit 1
fi

if [ ! -d "src/$OLD_NAME" ]; then
    echo "Error: Source directory src/$OLD_NAME/ not found."
    echo "Detected package name '$OLD_NAME' from pyproject.toml but directory is missing."
    exit 1
fi

if [ "$NEW_NAME" = "$OLD_NAME" ]; then
    echo "Error: New name is the same as the current name ($OLD_NAME)."
    exit 1
fi

echo ""
echo "  Current name:  $OLD_NAME"
echo "  New name:      $NEW_NAME"
echo ""

# --- Check for uncommitted changes ---

if command -v git &>/dev/null && [ -d ".git" ]; then
    if ! git diff --quiet HEAD 2>/dev/null; then
        echo "Warning: You have uncommitted changes."
        read -p "Continue anyway? [y/N] " confirm
        if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
            echo "Aborted."
            exit 1
        fi
    fi
fi

echo "Rebranding: $OLD_NAME → $NEW_NAME"
echo "========================================="
echo ""

# --- Step 1: Rename the source directory ---

echo "[1/4] Renaming src/$OLD_NAME/ → src/$NEW_NAME/"
mv "src/$OLD_NAME" "src/$NEW_NAME"

# --- Step 2: Replace in all source files ---

echo "[2/4] Replacing '$OLD_NAME' → '$NEW_NAME' in source files..."

# Python files
find "src/$NEW_NAME" -type f -name "*.py" -exec sed -i "s/$OLD_NAME/$NEW_NAME/g" {} +

# Jinja2 templates
find "src/$NEW_NAME" -type f -name "*.j2" -exec sed -i "s/$OLD_NAME/$NEW_NAME/g" {} +

# JSON templates
find "src/$NEW_NAME" -type f -name "*.json" -exec sed -i "s/$OLD_NAME/$NEW_NAME/g" {} +

# Markdown files inside src (e.g. Skills.md.j2 templates)
find "src/$NEW_NAME" -type f -name "*.md" -exec sed -i "s/$OLD_NAME/$NEW_NAME/g" {} +

# --- Step 3: Replace in config and project files ---

echo "[3/4] Updating pyproject.toml, README.md, and docs..."

sed -i "s/$OLD_NAME/$NEW_NAME/g" pyproject.toml

if [ -f "README.md" ]; then
    sed -i "s/$OLD_NAME/$NEW_NAME/g" README.md
fi

if [ -d "docs" ]; then
    find docs -type f -name "*.md" -exec sed -i "s/$OLD_NAME/$NEW_NAME/g" {} +
fi

if [ -d "tests" ]; then
    find tests -type f \( -name "*.py" -o -name "*.json" \) -exec sed -i "s/$OLD_NAME/$NEW_NAME/g" {} +
fi

# --- Step 4: Summary ---

echo "[4/4] Done!"
echo ""
echo "========================================="
echo "  Rebranded: $OLD_NAME → $NEW_NAME"
echo "========================================="
echo ""
echo "  Package dir:  src/$NEW_NAME/"
echo "  CLI command:  $NEW_NAME"
echo "  Entry point:  $NEW_NAME = \"$NEW_NAME.cli:app\""
echo ""
echo "Next steps:"
echo ""
echo "  1. Reinstall the package:"
echo "     uv pip install -e ."
echo ""
echo "  2. Install the global alias:"
echo "     .venv/bin/$NEW_NAME install"
echo ""
echo "  3. Verify it works:"
echo "     $NEW_NAME --help"
echo ""
