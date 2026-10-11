#!/bin/bash
# Hook Claude Code (PreToolUse, matcher "mcp__.*") : avant tout appel d'outil MCP, vérifie que les serveurs épinglés n'ont
# pas dérivé. Résultat mis en cache LEGION_LOCK_TTL secondes (défaut 600) pour ne pas interroger le journal à chaque appel.
# Code 2 = Claude Code BLOQUE l'appel et reçoit le message ci-dessous.
cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0
[ -f .mcp-tools.lock.json ] || exit 0
C=.mcp-tools.lock.cache; TTL=${LEGION_LOCK_TTL:-600}
if [ -f "$C" ] && [ $(( $(date +%s) - $(stat -c %Y "$C" 2>/dev/null || stat -f %m "$C") )) -lt "$TTL" ]; then
  [ "$(head -c 2 "$C")" = "OK" ] && exit 0
  tail -n +2 "$C" >&2; exit 2
fi
OUT=$(python3 -I -S tools/legion-lock/legion_lock.py check 2>&1); RC=$?
if [ $RC -eq 0 ]; then echo "OK" > "$C"; exit 0; fi
{ echo "KO"; echo "legion-lock : appel MCP bloqué — les outils d'un serveur épinglé ont changé ou la preuve est invalide :"; echo "$OUT"; } > "$C"
tail -n +2 "$C" >&2; exit 2
