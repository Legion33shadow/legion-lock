#!/bin/sh
# Assemble py/ depuis la racine du dépôt puis `npm pack` (tarball local). Ne publie rien.
set -eu
H=$(cd "$(dirname "$0")" && pwd); R=$(cd "$H/../.." && pwd)
rm -rf "$H/py"; mkdir -p "$H/py/vendor"
cp "$R/legion_lock.py" "$R/legion_verify_server.py" "$H/py/"
cp "$R/vendor/legion_tlog_verify.py" "$R/vendor/legion_verify_mirror.py" "$H/py/vendor/"
cp "$R/README.md" "$R/LICENSE" "$H/"
cd "$H" && npm pack --silent
