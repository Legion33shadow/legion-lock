#!/bin/sh
# Hook git brut (sans le framework pre-commit) : cp pre-commit.sh .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit
if git diff --cached --name-only | grep -Eq '(^|/)(\.mcp-tools\.lock\.json|\.mcp\.json)$'; then
  python3 -I -S tools/legion-lock/legion_lock.py check || { echo "mcp-tools-lock : dérive ou preuve invalide — commit refusé" >&2; exit 1; }
fi
