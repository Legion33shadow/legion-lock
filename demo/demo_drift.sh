#!/bin/bash
# DÉMO REPRODUCTIBLE — dérive RÉELLE tirée du journal public (aucune donnée fabriquée).
# On « approuve » l'état d'un serveur AVANT un changement qu'il a réellement fait, puis `check` doit ÉCHOUER et nommer la dérive.
#  - io.guestgraph/mental-model : outil `diagram` modifié (feuille 16044 -> 17659)
#  - ai.daystruct.api/daystruct : outil `plan_project_development` ajouté (feuille 121 -> 14516)
# Ed25519 en Python pur (-S : `cryptography` ignoré), pour montrer la voie sans dépendance.
L="python3 -I -S $(cd "$(dirname "$0")/.." && pwd)/legion_lock.py"
W=$(mktemp -d); cd "$W"; set -x
ls -A
$L add io.guestgraph/mental-model --at-leaf 16044
$L add ai.daystruct.api/daystruct --at-leaf 121
$L check
echo "EXIT_CHECK=$?"
unshare -rn $L verify
echo "EXIT_VERIFY_HORS_RESEAU=$?"
python3 -c "import json;d=json.load(open('.mcp-tools.lock.json'));d['servers']['io.guestgraph/mental-model']['approved']['tools']['diagram']='0'*64;json.dump(d,open('.mcp-tools.lock.json','w'))"
$L verify
echo "EXIT_VERIFY_LOCKFILE_FALSIFIE=$?"
rm .mcp-tools.lock.json
$L add io.guestgraph/mental-model
$L check
echo "EXIT_CHECK_ETAT_COURANT_APPROUVE=$?"
set +x; echo "dossier : $W"
