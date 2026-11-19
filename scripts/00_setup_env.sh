#!/usr/bin/env bash
# Create the non-root NephroPerturb environment (conda for Python/Node, pip for libs).
set -euo pipefail
CONDA_HOME=${CONDA_HOME:-/public/home/dongb/miniforge3}
ENV_NAME=${ENV_NAME:-nephroperturb}
ENV_DIR="$CONDA_HOME/envs/$ENV_NAME"

if [ ! -d "$ENV_DIR" ]; then
  "$CONDA_HOME/bin/conda" create -y -n "$ENV_NAME" -c conda-forge --override-channels \
    python=3.11 nodejs=20
fi

PIP="$ENV_DIR/bin/pip"
"$PIP" install --quiet --upgrade pip
"$PIP" install --quiet \
  numpy scipy pandas h5py pyarrow numba scikit-learn lightgbm shap rdkit \
  fastapi "uvicorn[standard]" sqlalchemy "pydantic>=2" openai mcp openpyxl pytest tqdm

"$ENV_DIR/bin/python" - <<'PY'
import numpy, pandas, h5py, rdkit
print("python env ok:", numpy.__version__, pandas.__version__,
      h5py.__version__, rdkit.__version__)
PY
