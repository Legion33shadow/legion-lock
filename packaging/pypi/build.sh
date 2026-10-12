#!/bin/sh
# Construit sdist + wheel de legion-lock dans packaging/pypi/dist, SANS modifier le code :
#   legion_lock.py -> legion_lock/__init__.py ; legion_verify_server.py -> legion_lock/verify_server.py ; vendor/ tel quel.
# (legion_lock.py ajoute HERE/vendor au sys.path : HERE = dossier du paquet installé.)  Ne publie rien.
set -eu
R=$(cd "$(dirname "$0")/../.." && pwd); B="$R/packaging/pypi/_build"
rm -rf "$B" "$R/packaging/pypi/dist"; mkdir -p "$B/legion_lock/vendor"
cp "$R/legion_lock.py" "$B/legion_lock/__init__.py"
cp "$R/legion_verify_server.py" "$B/legion_lock/verify_server.py"
cp "$R/vendor/legion_tlog_verify.py" "$R/vendor/legion_verify_mirror.py" "$B/legion_lock/vendor/"
cp "$R/packaging/pypi/pyproject.toml" "$R/README.md" "$R/LICENSE" "$B/"
python3 -m build --outdir "$R/packaging/pypi/dist" "$B" >/dev/null
rm -rf "$B"; ls -l "$R/packaging/pypi/dist"
