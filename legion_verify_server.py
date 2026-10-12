#!/usr/bin/env python3
"""legion-verify — vérifier un serveur MCP en UNE commande, contre l'historique signé du journal LEGION.

  legion_verify_server.py https://serveur/mcp            récupère tools/list en direct, compare au journal
  legion_verify_server.py https://serveur/mcp --id ID    précise l'identifiant du registre (sinon : trouvé par l'empreinte)
  legion_verify_server.py ID                             identifiant seul : l'URL est lue dans le registre MCP officiel
  ... --save preuve.json                                 garde la preuve complète
  legion_verify_server.py --offline preuve.json          HORS LIGNE : revérifie une preuve sauvegardée, sans réseau

Verdict : UNCHANGED (liste en direct = dernière version signée) · CHANGED (différente : diff par outil) ·
UNKNOWN (le journal n'a jamais signé cette liste / ce serveur) · AUTH (le serveur exige une authentification : rien à comparer).
Codes de sortie : 0 UNCHANGED · 1 CHANGED · 3 UNKNOWN ou AUTH · 2 erreur ou preuve invalide.
Aucune note, aucun score : seulement des faits observés et signés. Le journal est l'observation d'UN observateur (LEGION)."""
import argparse, datetime, hashlib, json, os, sys, urllib.error, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import legion_lock as LL  # noqa: E402  (preuves : trousseau épinglé, enregistrement signé, inclusion RFC 9162, tête signée)
T = LL.T

V1 = LL.BASE
V0 = V1.rsplit("/v1", 1)[0] + "/v0" if V1.endswith("/v1") else V1
REGISTRY = os.environ.get("LEGION_VERIFY_REGISTRY", "https://registry.modelcontextprotocol.io/v0")
UA = "legion-verify/0.1 (+https://github.com/Legion33shadow/legion-lock)"
MAX_BYTES = 8 << 20


class Fail(Exception):
    pass


def now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------- client MCP minimal (streamable HTTP) : initialize + tools/list, jamais d'appel d'outil
def _post(url, body, headers, timeout):
    h = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream", "User-Agent": UA}
    h.update(headers)
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=h, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise Fail("réponse du serveur MCP > %d octets" % MAX_BYTES)
        sid = r.headers.get("Mcp-Session-Id")
    txt = raw.decode("utf-8", "replace")
    if not txt.strip():
        return None, sid
    msgs = [l[5:].strip() for l in txt.splitlines() if l.startswith("data:")] or [txt]
    for m in msgs:
        try:
            j = json.loads(m)
        except ValueError:
            continue
        if isinstance(j, dict) and j.get("id") == body.get("id"):
            return j, sid
    return None, sid


def fetch_tools(url, timeout):
    if not url.startswith(("https://", "http://")):
        raise Fail("URL attendue en http(s)://")
    try:
        j, sid = _post(url, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "legion-verify", "version": "0.1"}}}, {}, timeout)
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return {"auth_required": True, "http_status": e.code}
        raise Fail("le serveur MCP répond HTTP %d à initialize" % e.code)
    except (urllib.error.URLError, OSError) as e:
        raise Fail("serveur MCP injoignable (%s)" % type(getattr(e, "reason", e)).__name__)
    if not j or "result" not in j:
        raise Fail("réponse initialize invalide")
    proto = j["result"].get("protocolVersion", "2025-06-18")
    h = {"MCP-Protocol-Version": proto}
    if sid:
        h["Mcp-Session-Id"] = sid
    try:
        _post(url, {"jsonrpc": "2.0", "method": "notifications/initialized"}, h, timeout)
    except Exception:
        pass
    tools, cursor, n = [], None, 2
    for _ in range(50):
        params = {"cursor": cursor} if cursor else {}
        try:
            j, _s = _post(url, {"jsonrpc": "2.0", "id": n, "method": "tools/list", "params": params}, h, timeout)
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                return {"auth_required": True, "http_status": e.code}
            raise Fail("le serveur MCP répond HTTP %d à tools/list" % e.code)
        n += 1
        if not j or "result" not in j:
            raise Fail("réponse tools/list invalide%s" % ((": " + json.dumps(j.get("error"))[:120]) if j and j.get("error") else ""))
        tools += j["result"].get("tools", [])
        cursor = j["result"].get("nextCursor")
        if not cursor:
            break
    return {"auth_required": False, "tools": tools, "server_info": j and None}


# ---------- empreinte identique à celle du collecteur LEGION (name, description, inputSchema ; JCS ; tri par nom)
def normalize(tools):
    norm = []
    for t in tools:
        if not isinstance(t, dict) or not isinstance(t.get("name"), str):
            raise Fail("outil sans nom texte dans tools/list")
        norm.append({"name": t["name"], "description": t.get("description") or "", "inputSchema": t.get("inputSchema") or {}})
    names = [t["name"] for t in norm]
    if len(set(names)) != len(names):
        raise Fail("noms d'outils dupliqués dans tools/list")
    return sorted(norm, key=lambda t: t["name"])


def fingerprint(norm, algo="v2"):
    c = T.canon_v1 if algo == "v1" else T.canon
    return {"sha256": hashlib.sha256(c(norm)).hexdigest(), "per_tool": {t["name"]: hashlib.sha256(c(t)).hexdigest() for t in norm}}


def resolve_url(server_id, timeout):
    try:
        d = json.loads(urllib.request.urlopen(urllib.request.Request(REGISTRY + "/servers?search=" + urllib.parse.quote(server_id) + "&limit=20",
                                                                     headers={"User-Agent": UA}), timeout=timeout).read())
    except Exception as e:
        raise Fail("registre MCP officiel injoignable (%s)" % type(e).__name__)
    for s in d.get("servers", []):
        srv = s.get("server", s)
        if srv.get("name") == server_id:
            for r in srv.get("remotes", []) or []:
                if r.get("type") in ("streamable-http", "http") and r.get("url"):
                    return r["url"]
            raise Fail("%s : aucune URL distante (streamable-http) dans le registre ; serveur local (stdio) non vérifiable ainsi" % server_id)
    raise Fail("%s : absent du registre MCP officiel" % server_id)


def find_ids(fp_sha):
    try:
        m = LL.get("/lookup/tools/" + fp_sha).get("matches", [])
    except LL.Fail:
        return []
    return sorted({x["server_id"] for x in m})


def history(server_id, keys):
    """Historique signé (toutes les versions observées) ; chaque enregistrement est revérifié (signature)."""
    url = V0 + "/servers/" + urllib.parse.quote(server_id, safe="/@:")
    try:
        d = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=30).read())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise Fail("journal : HTTP %d sur l'historique" % e.code)
    recs = sorted(d.get("records", []), key=lambda r: r["leaf_index"])
    for r in recs:
        if "signature_ed25519" in r and not all(T.check_record(r, keys)[:2]):
            raise Fail("historique : enregistrement %d à signature invalide" % r["leaf_index"])
    return recs


def card(ev, verdict, out):
    p = print if out is None else out.append
    rec, sth = ev["bundle"]["record"], ev["bundle"]["sth"]["tree_head"]
    hist = ev.get("history") or []
    changes = [r for r in hist if (r.get("change") or {}).get("kind") == "changed"]
    first = hist[0]["observed_at"] if hist else rec["observed_at"]
    p("SERVEUR   %s" % ev["server_id"])
    if ev.get("url"):
        p("EN DIRECT %s · %s" % (ev["url"], ("%d outils · lu le %s" % (len(ev["live_tools"]), ev["fetched_at"])) if ev.get("live_tools") is not None else "authentification requise (HTTP %s)" % ev.get("http_status")))
    p("VERDICT   %s" % verdict["line"])
    for l in verdict.get("diff", []):
        p("          " + l)
    p("STABILITÉ observé depuis le %s · %d changement(s) signé(s)%s" % (first[:10], len(changes),
      (" · dernier changement signé le %s" % changes[-1]["observed_at"][:16].replace("T", " ") + " UTC") if changes else ""))
    if ev.get("url"):
        p("AUTH      %s" % ("requise (observé maintenant)" if ev.get("auth_required") else "non requise pour tools/list (observé maintenant)"))
    p("PREUVE    feuille %d ∈ tête signée %d (%s UTC) · enregistrement signé OK · inclusion RFC 9162 OK · tête signée OK · clés depuis la racine %s…"
      % (rec["leaf_index"], sth["tree_size"], sth["timestamp"][:16].replace("T", " "), LL.ROOT_PIN[:16]))
    p("ANCRAGE   Bitcoin : pending (aucun ots verify sur nœud complet)")
    p("LIMITES   un seul observateur (LEGION) ; empreinte = name + description + inputSchema ; un changement apparaît au prochain cycle signé")


def decide(ev):
    rec = ev["bundle"]["record"]
    signed = rec["tools_fingerprint"]
    if ev.get("auth_required"):
        return {"code": 3, "word": "AUTH", "line": "AUTH — le serveur exige une authentification : liste en direct non comparable ; historique signé ci-dessous"}
    if ev.get("live_tools") is None:
        return {"code": 3, "word": "UNKNOWN", "line": "pas de lecture en direct (identifiant seul sans URL utilisable)"}
    algo = "v1" if signed["algo"].endswith("/v1") else "v2"
    live = fingerprint(ev["live_tools"], algo)
    if live["sha256"] == signed["sha256"]:
        return {"code": 0, "word": "UNCHANGED", "line": "UNCHANGED — liste en direct identique à la version signée le %s (feuille %d) ; aucun changement signé depuis"
                % (rec["observed_at"][:16].replace("T", " ") + " UTC", rec["leaf_index"])}
    old = {n: h for n, h in signed["per_tool_sha256"]}
    added, removed = sorted(set(live["per_tool"]) - set(old)), sorted(set(old) - set(live["per_tool"]))
    mod = sorted(n for n in set(old) & set(live["per_tool"]) if old[n] != live["per_tool"][n])
    diff = ["outil %s : AJOUTÉ" % n for n in added] + ["outil %s : RETIRÉ" % n for n in removed]
    arch = ev.get("signed_tools") or {}
    livemap = {t["name"]: t for t in ev["live_tools"]}
    for n in mod:
        x, y = arch.get(n), livemap[n]
        if not x:
            diff.append("outil %s : définition changée (version signée non archivée)" % n); continue
        if x.get("description") != y.get("description"):
            diff.append("outil %s : description changée" % n)
        if x.get("inputSchema") != y.get("inputSchema"):
            ps = LL.schema_paths(x.get("inputSchema"), y.get("inputSchema"))
            diff.append("outil %s : inputSchema changé (%s)" % (n, ", ".join(ps[:6]) + (" …" if len(ps) > 6 else "")))
    return {"code": 1, "word": "CHANGED", "diff": diff,
            "line": "CHANGED — liste en direct différente de la dernière version signée (le %s, feuille %d). Si c'est récent, le journal "
                    "l'enregistrera au prochain cycle signé." % (rec["observed_at"][:16].replace("T", " ") + " UTC", rec["leaf_index"])}


def verify_offline(path):
    ev = json.load(open(path, encoding="utf-8"))
    keys = LL.keys_from(ev["keyring"])
    LL.check_evidence(ev["bundle"], keys, ev["server_id"])
    for r in ev.get("history") or []:
        if "signature_ed25519" in r and not all(T.check_record(r, keys)[:2]):
            raise Fail("preuve : historique altéré (feuille %d)" % r["leaf_index"])
    if ev.get("live_tools") is not None:
        ev["live_tools"] = normalize(ev["live_tools"])
    if ev.get("signed_tools"):
        lst = sorted(ev["signed_tools"].values(), key=lambda t: t["name"])
        algo = "v1" if ev["bundle"]["record"]["tools_fingerprint"]["algo"].endswith("/v1") else "v2"
        if fingerprint(lst, algo)["sha256"] != ev["bundle"]["record"]["tools_fingerprint"]["sha256"]:
            raise Fail("preuve : définitions archivées altérées")
    return ev


def main(argv=None):
    ap = argparse.ArgumentParser(prog="legion-verify", description=__doc__.split("\n")[0])
    ap.add_argument("target", nargs="?", help="URL du serveur MCP (https://…/mcp) ou identifiant du registre")
    ap.add_argument("--id", help="identifiant du registre MCP (si l'URL ne suffit pas à le trouver)")
    ap.add_argument("--save", help="écrire la preuve complète (JSON) pour une revérification hors ligne")
    ap.add_argument("--offline", help="revérifier une preuve sauvegardée, sans réseau")
    ap.add_argument("--timeout", type=float, default=20.0)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    try:
        if a.offline:
            ev = verify_offline(a.offline); v = decide(ev)
            v["line"] += " [revérifié HORS LIGNE depuis %s ; lecture en direct du %s]" % (os.path.basename(a.offline), ev.get("fetched_at", "?"))
        else:
            if not a.target:
                ap.error("URL ou identifiant requis (ou --offline FICHIER)")
            url, sid = (a.target, a.id) if a.target.startswith(("http://", "https://")) else (None, a.target)
            if url is None:
                url = resolve_url(sid, a.timeout)
            live = fetch_tools(url, a.timeout)
            norm = normalize(live["tools"]) if not live["auth_required"] else None
            if sid is None:
                ids = find_ids(fingerprint(norm)["sha256"]) if norm is not None else []
                if not ids:
                    msg = "UNKNOWN — cette liste d'outils n'a jamais été signée par le journal" if norm is not None else "UNKNOWN — authentification requise et aucun --id"
                    print("EN DIRECT %s · %s\nVERDICT   %s. Donnez l'identifiant du registre avec --id pour comparer à son historique."
                          % (url, "%d outils" % len(norm) if norm is not None else "auth requise", msg))
                    return 3
                if len(ids) > 1:
                    print("EN DIRECT %s · %d outils\nVERDICT   liste identique à la version signée de %d serveurs du journal (%s) : précisez --id"
                          % (url, len(norm), len(ids), ", ".join(ids[:5]) + (" …" if len(ids) > 5 else "")))
                    return 3
                sid = ids[0]
            kr = LL.get("/keyring", raw=True); keys = LL.keys_from(kr)
            try:
                b = LL.get("/servers/%s/latest" % urllib.parse.quote(sid, safe=""))
            except LL.Fail as e:
                if "404" in str(e):
                    print("SERVEUR   %s\nVERDICT   UNKNOWN — ce serveur n'a aucun enregistrement signé dans le journal (rien n'est inventé)" % sid)
                    return 3
                raise
            bundle = {"record": b["record"], "inclusion": b["inclusion"], "sth": b["sth"]}
            LL.check_evidence(bundle, keys, sid)
            arch = LL.tools_from_archive(b["record"]["tools_fingerprint"])
            ev = {"schema": "legion-verify-evidence/0.1", "server_id": sid, "url": url, "fetched_at": now(),
                  "auth_required": live["auth_required"], "http_status": live.get("http_status"),
                  "live_tools": norm, "bundle": bundle, "keyring": kr, "history": history(sid, keys),
                  "signed_tools": arch, "newer_uncovered_records": b.get("newer_uncovered_records", 0)}
            v = decide(ev)
            if a.save:
                json.dump(ev, open(a.save, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        if a.json:
            print(json.dumps({"verdict": v["word"], "line": v["line"], "diff": v.get("diff", []), "server_id": ev["server_id"]}, ensure_ascii=False, indent=1))
        else:
            card(ev, v, None)
            if ev.get("newer_uncovered_records"):
                print("NOTE      %d observation(s) plus récente(s) pas encore dans une tête signée" % ev["newer_uncovered_records"])
        return v["code"]
    except (Fail, LL.Fail) as e:
        print("ÉCHEC : %s" % e, file=sys.stderr); return 2
    except (ValueError, KeyError, TypeError) as e:
        print("ÉCHEC : donnée invalide (%s: %s)" % (type(e).__name__, str(e)[:160]), file=sys.stderr); return 2


if __name__ == "__main__":
    sys.exit(main())
