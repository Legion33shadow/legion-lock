# `.mcp-tools.lock.json` — format `mcp-tools-lock/0.1`

Un JSON trié (`sort_keys`), indenté, prévu pour être commité et relu en revue.

```json
{
 "format": "mcp-tools-lock/0.1",
 "log": {"base": "https://tlog.legion-api.com/tlog/v1", "origin": "tlog.legion-api.com/mcp/v0",
         "root_pin_sha256": "a7c6a35b1c2c81d589a30c2ad628679bdea9da4139d49aa3c42cdde6e1c65036"},
 "keyring": "<trousseau JSONL du journal, chaîné, chaque entrée approuvée par la racine>",
 "servers": {
  "<server_id du registre MCP>": {
   "approved": {
    "tools_sha256": "<empreinte de la liste approuvée>",
    "algo": "sha256(JCS-RFC8785(sorted[{name,description,inputSchema}]))/v2",
    "tool_count": 14,
    "tools": {"<nom d'outil>": "<sha256(JCS({name,description,inputSchema}))>"}
   },
   "evidence": {"record": {"…": "enregistrement signé"}, "inclusion": {"leaf_index": 0, "tree_size": 0, "audit_path": []},
                "sth": {"tree_head": {"…": "tête"}, "signature_ed25519": "…"}},
   "pinned_from": {"leaf_index": 16044, "observed_at": "…", "tree_size": 17359},
   "pinned_at": "<horodatage UTC de l'épinglage>"
  }
 }
}
```

Règles :
- `approved` doit être exactement l'empreinte de l'enregistrement signé contenu dans `evidence.record`. `verify` le
  contrôle : un `approved` édité à la main est refusé.
- Empreinte d'un outil : `sha256(JCS({name, description, inputSchema}))`. Empreinte de la liste :
  `sha256(JCS(liste triée par name))`. Les vieux enregistrements (`…/v1`) utilisent l'ancienne canonicalisation.
  `check` recalcule l'algorithme de chacune des deux versions et signale « contenu identique » quand seul l'algorithme
  diffère.
- Ancre de confiance : `root_pin_sha256`. Le trousseau n'est accepté que si sa première entrée a cette empreinte.
- Aucun secret n'y figure : seulement des données publiques signées.
