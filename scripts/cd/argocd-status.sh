#!/usr/bin/env bash
set -euo pipefail
# Keep the five-argument SSM interface; Python owns the global bounded wait.
exec /usr/bin/python3 "$(dirname "$(readlink -f "$0")")/argocd-status.py" "$@"
