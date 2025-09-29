#!/usr/bin/env bash
# build_bayhunter.sh
# Usage:
#   ./build_bayhunter.sh                 # uses env "bay" and current dir as source
#   ./build_bayhunter.sh myenv /path/to/BayHunter

set -Eeuo pipefail

ENV_NAME="${1:-bay}"
SRC_DIR="${2:-$(pwd)}"

echo "=== BayHunter build script ==="
echo "Env name : ${ENV_NAME}"
echo "Source   : ${SRC_DIR}"
echo

# --- helpers ---
abort() { echo "ERROR: $*" >&2; exit 1; }

need_cmd() { command -v "$1" >/dev/null 2>&1; }

install_build_tools() {
  echo "Checking for system compilers..."
  local missing=()

  for cmd in gcc g++ gfortran make; do
    if ! need_cmd "$cmd"; then
      missing+=("$cmd")
    fi
  done

  if [ "${#missing[@]}" -eq 0 ]; then
    echo "✅ Found gcc, g++, gfortran, and make."
    return
  fi

  echo "⚠ Missing tools: ${missing[*]}"
  if [ -f /etc/debian_version ]; then
    echo "Attempting to install via apt-get (requires sudo)..."
    sudo apt-get update
    sudo apt-get install -y build-essential gfortran
  else
    echo "Non-Debian system detected. Please install compilers manually."
    abort "Missing required build tools: ${missing[*]}"
  fi
}

# --- prerequisite check ---
need_cmd conda || abort "conda not found. Please install Miniconda/Anaconda."
need_cmd python || abort "python not found."

# --- ensure compilers exist ---
install_build_tools

# --- enable conda activate in scripts ---
CONDA_BASE="$(conda info --base)"
# shellcheck source=/dev/null
source "${CONDA_BASE}/etc/profile.d/conda.sh"

# --- create env if missing ---
if conda env list | awk '{print $1}' | grep -qx "${ENV_NAME}"; then
  echo "Conda env '${ENV_NAME}' already exists."
else
  echo "Creating conda env '${ENV_NAME}' (python=3.8.12)..."
  conda create -y -n "${ENV_NAME}" python=3.8.12
fi

echo "Activating env '${ENV_NAME}'..."
conda activate "${ENV_NAME}"

# --- show basic info ---
echo "Python: $(python --version 2>&1)"
echo "Pip   : $(pip --version 2>&1)"
echo

# --- install pinned deps ---
echo "Installing pinned Python dependencies..."
pip install \
  numpy==1.21.4 \
  cython==0.29.25 \
  matplotlib==3.5.1 \
  scipy==1.5.3 \
  pypdf2==2.10.5 \
  pyzmq==25.1.0 \
  configobj==5.0.8

# --- build tool pins ---
echo "Pinning build tools compatible with numpy.distutils..."
pip install "setuptools<60" "wheel<0.41"

# Force stdlib distutils instead of setuptools' removed shim
export SETUPTOOLS_USE_DISTUTILS=stdlib

# --- clean possible previous builds for a fresh compile ---
echo "Cleaning previous build artifacts (if any)..."
python - <<'PY'
import shutil, pathlib as p, sys
root = p.Path(sys.argv[1]).resolve()
for d in [root/"build", root/"dist"]:
    shutil.rmtree(d, ignore_errors=True)
for eg in root.glob("*.egg-info"):
    shutil.rmtree(eg, ignore_errors=True)
PY
"${SRC_DIR}"

# --- build & install ---
echo "Installing BayHunter from source with --no-build-isolation..."
pip install --no-build-isolation "${SRC_DIR}"

echo
echo "=== Final package list ==="
pip list

echo
echo "✅ Done. BayHunter should be installed in env '${ENV_NAME}'."
