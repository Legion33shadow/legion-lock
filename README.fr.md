# legion-lock — épingler les outils de vos serveurs MCP, et savoir quand ils changent

Un serveur MCP peut changer la description ou le schéma de ses outils après que vous les avez approuvés. Or un modèle lit
ces descriptions comme des instructions. `legion-lock` épingle l'état approuvé de chaque serveur dans `.mcp-tools.lock.json`.
`check` échoue dès que le serveur a changé, et dit précisément quoi : outil ajouté, retiré, description changée, chemins du
schéma modifiés.

Les empreintes viennent du journal de transparence public LEGION (`https://tlog.legion-api.com/tlog/v1`). Chacune est
signée, incluse dans un arbre de Merkle append-only et vérifiée contre une clé racine que vous épinglez. Le lockfile garde
les preuves : `verify` les revérifie sans réseau.

## Épingler en 3 commandes
```bash
python3 legion_lock.py add io.guestgraph/mental-model   # épingle l'état actuel (preuve vérifiée) dans .mcp-tools.lock.json
python3 legion_lock.py check                            # 0 = conforme · 1 = DÉRIVE (diff par outil) · 2 = preuve invalide
python3 legion_lock.py verify                           # hors ligne : revérifie les preuves du lockfile
```
L'identifiant est celui du registre MCP officiel. Pour approuver une version antérieure : `add ID --at-leaf N`. Pour la
prouver contre une tête signée précise : `--at-head S`.

Prérequis : Python 3.8+. Aucune dépendance : `cryptography` est utilisé s'il est installé, sinon Ed25519 en Python pur.
Fichiers : `legion_lock.py`, plus `vendor/legion_tlog_verify.py` et `vendor/legion_verify_mirror.py`, les deux vérifieurs
publics de LEGION.

## Démo (dérive réelle, journal public)
`demo/demo_drift.sh` épingle deux serveurs à un état ANTÉRIEUR à un changement qu'ils ont réellement fait, puis lance `check` :
`io.guestgraph/mental-model` (outil `diagram` : description et 2 chemins du schéma modifiés, feuille 16044 → 17659) et
`ai.daystruct.api/daystruct` (outil `plan_project_development` ajouté, feuille 121 → 14516). Résultat attendu : code 1 et la
dérive nommée ; `verify` hors réseau = 0 ; lockfile édité à la main = 2. Transcript : `demo/transcript_drift_*.txt`.
Tests adversariaux (journal menteur, archive truquée, histoire réécrite, lockfile falsifié) : `tests/test_adversarial.py`, 15/15.

## Ce que `check` vérifie, dans l'ordre
1. Le trousseau du journal part bien de l'empreinte racine épinglée `a7c6a35b…`.
2. Votre épinglage et l'état actuel sont tous deux des enregistrements signés, inclus dans des têtes signées (RFC 9162).
3. La tête actuelle étend celle de votre épinglage (preuve de cohérence). Sinon : historique réécrit, fourche ou retour en
   arrière, et code 2.
4. L'empreinte actuelle est-elle l'empreinte approuvée ? Sinon, `check` récupère les définitions archivées des deux
   versions. Il ne les accepte que si elles redonnent les empreintes signées, puis nomme la dérive champ par champ.

## Limites (à lire)
- C'est **l'observation signée d'un seul observateur** (LEGION). Elle ne dit pas ce que le serveur montre à d'autres clients.
- Seuls `name`, `description` et `inputSchema` sont dans l'empreinte. Un changement limité à `annotations`, `outputSchema`
  ou `title` n'est pas vu.
- Délai : un changement n'apparaît qu'après le prochain relevé de LEGION, puis la tête signée suivante (un à trois cycles
  signés par jour, mesuré du 9 au 11/10/2026). `check --strict` échoue aussi quand une observation plus récente n'est pas
  encore signée.
- Les serveurs qui exigent une authentification ne sont pas observés.
- Les ancrages Bitcoin du journal sont `pending` (aucun `ots verify` sur un nœud complet). `legion-lock` ne s'appuie pas dessus.

## Intégrations (`integrations/`)
- `github/mcp-tools-lock.yml` : à chaque pull request et chaque jour, `verify` puis `check`. Le job échoue s'il y a une dérive.
- `pre-commit/pre-commit.sh` (hook git brut).
- `claude-code/settings.json` + `legion_lock_hook.sh` : hook `PreToolUse` sur `mcp__.*`. Claude Code bloque l'appel
  d'outil MCP si un serveur épinglé a dérivé. Résultat mis en cache 10 min.
