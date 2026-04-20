#!/usr/bin/env bash
#
# Setup script: install uv (if needed), create venv, install package, run orai install.
#
# Usage:
#   ./scripts/setup.sh
#
# Run from the project root directory.

set -euo pipefail

# --- Check we're in the right directory ---

if [ ! -f "pyproject.toml" ]; then
    echo "Error: pyproject.toml not found. Run this script from the project root."
    echo "Current directory: $(pwd)"
    exit 1
fi

install_uv() {
    if command -v uv &>/dev/null; then
        echo "[ok] uv already installed: $(uv --version)"
        return
    fi

    echo "[1/4] Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # Add uv to PATH for the remainder of this script
    export PATH="$HOME/.local/bin:$PATH"

    if ! command -v uv &>/dev/null; then
        echo "Error: uv installation failed."
        echo "Please install manually: curl -LsSf https://astral.sh/uv/install.sh | sh"
        exit 1
    fi
    echo "  uv installed: $(uv --version)"
}

create_venv() {
    echo "[2/4] Creating virtual environment..."
    uv venv
    echo "  venv created at .venv/"
}

install_package() {
    echo "[3/4] Installing package (editable)..."
    uv pip install -e .
    echo "  orai package installed"
}

run_orai_install() {
    echo "[4/4] Running orai install..."
    .venv/bin/orai install
    echo "  orai install complete"
}

# --- Main ---

echo ""
echo "Setting up orai..."
echo "========================================="
echo ""

install_uv
create_venv
install_package
run_orai_install

echo ""
echo "========================================="
echo "  Setup complete!"
echo "========================================="
echo ""
echo "Activate the environment with:"
echo "  source .venv/bin/activate"
echo ""
echo "Or run directly:"
echo "  .venv/bin/orai --help"
echo ""
