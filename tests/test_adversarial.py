#!/usr/bin/env python3
"""legion-lock face à un journal MENTEUR (proxy local qui altère les réponses du vrai journal) et à des lockfiles falsifiés.
Attendu : jamais « CONFORME » sur une donnée fausse ; code 2 (preuve rejetée) ou 1 (dérive réelle), jamais de trace Python."""
import copy, http.server, json, os, subprocess, sys, tempfile, threading, urllib.request
HERE = os.path.dirname(os.path.abspath(__file__)); CLI = os.path.join(HERE, "..", "legion_lock.py")
REAL = "https://tlog.legion-api.com/tlog/v1"; CACHE = {}; MUT = {"fn": None}
def real(path):
    if path not in CACHE:
        CACHE[path] = urllib.request.urlopen(urllib.request.Request(REAL + path, headers={"User-Agent": "legion-lock-test/0"}), timeout=30).read()
    return CACHE[path]
class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        p = self.path[len("/tlog/v1"):]
        try: b = real(p)
        except Exception: self.send_response(404); self.end_headers(); return
        if MUT["fn"]: b = MUT["fn"](p, b)
        self.send_response(200); self.end_headers(); self.wfile.write(b)
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
ENV = dict(os.environ, LEGION_LOCK_BASE="http://127.0.0.1:%d/tlog/v1" % srv.server_port)
SID = "io.guestgraph/mental-model"; Q = "/servers/io.guestgraph%2Fmental-model/latest"
W = tempfile.mkdtemp(); LOCK = os.path.join(W, "l.json"); RES = []
def run(*args):
    p = subprocess.run([sys.executable, "-I", "-S", CLI, "--lock", LOCK] + list(args), capture_output=True, text=True, env=ENV, timeout=300)
    return p.returncode, (p.stdout + p.stderr).strip(), "Traceback" in p.stderr
def case(name, expect, *args):
    rc, out, tb = run(*args); ok = rc in expect and not tb
    RES.append(ok); print("%s %-58s code=%s %s" % ("OK " if ok else "BUG", name, rc, out.splitlines()[-1][:110] if out else ""))
def jmut(path_match, f):
    def g(p, b):
        if p.startswith(path_match):
            d = json.loads(b); f(d); return json.dumps(d).encode()
        return b
    return g
MUT["fn"] = None; case("épinglage honnête (feuille 16044, tête 17359) via le proxy", {0}, "add", SID, "--at-leaf", "16044", "--at-head", "17359")
base = open(LOCK).read()
case("check honnête : dérive réelle détectée", {1}, "check")
# --- journal menteur
MUT["fn"] = jmut(Q, lambda d: d["record"]["tools_fingerprint"].__setitem__("sha256", json.loads(base)["servers"][SID]["approved"]["tools_sha256"]))
case("journal ment : empreinte courante = l'approuvée (cacher la dérive)", {2}, "check")
MUT["fn"] = jmut(Q, lambda d: d["record"].__setitem__("server_id", "evil/other"))
case("journal ment : server_id changé", {2}, "check")
MUT["fn"] = jmut(Q, lambda d: d["inclusion"]["audit_path"].__setitem__(0, "00" * 32))
case("journal ment : chemin d'inclusion altéré", {2}, "check")
MUT["fn"] = jmut(Q, lambda d: d["sth"]["tree_head"].__setitem__("root_sha256", "11" * 32))
case("journal ment : racine de la tête altérée", {2}, "check")
MUT["fn"] = lambda p, b: (b.replace(b"\"diagram\"", b"\"diagram2\"") if p.startswith("/tools/") else b)
case("archive ment : définitions d'outils altérées", {2}, "check")
MUT["fn"] = jmut("/proof/consistency", lambda d: d["proof"].__setitem__(0, "22" * 32))
case("journal ment : preuve de cohérence altérée (histoire réécrite)", {2}, "check")
def first_line_other_root(p, b):
    if p == "/keyring":
        lines = b.decode().splitlines(); d = json.loads(lines[0]); d["public_key_b64"] = "AAAA" + d["public_key_b64"][4:]
        return ("\n".join([json.dumps(d)] + lines[1:]) + "\n").encode()
    return b
MUT["fn"] = first_line_other_root; case("journal ment : trousseau d'une autre racine", {2}, "check")
MUT["fn"] = None
# --- lockfile falsifié (hors ligne)
for name, f in [("lockfile : enregistrement épinglé altéré", lambda d: d["servers"][SID]["evidence"]["record"].__setitem__("observed_at", "2020-01-01T00:00:00Z")),
                ("lockfile : état approuvé ≠ enregistrement signé", lambda d: d["servers"][SID]["approved"].__setitem__("tools_sha256", "33" * 32)),
                ("lockfile : clé publique d'une sous-clé remplacée", lambda d: d.__setitem__("keyring", "\n".join([l if i != 1 else json.dumps(dict(json.loads(l), public_key_b64="A" + json.loads(l)["public_key_b64"][1:] if json.loads(l)["public_key_b64"][0] != "A" else "B" + json.loads(l)["public_key_b64"][1:])) for i, l in enumerate(d["keyring"].splitlines())]))),
                ("lockfile : auto-signature de la racine altérée (sans effet attendu : racine approuvée par son empreinte)", lambda d: d.__setitem__("keyring", d["keyring"].replace("A", "B", 1))),
                ("lockfile : racine différente", lambda d: d["log"].__setitem__("root_pin_sha256", "44" * 32))]:
    d = json.loads(base); f(d); open(LOCK, "w").write(json.dumps(d)); case(name, {0} if "sans effet attendu" in name else {2}, "verify")
open(LOCK, "w").write(base); case("lockfile intact : verify hors ligne", {0}, "verify")
print("TOTAL %d cas, %d OK, %d BUG" % (len(RES), RES.count(True), RES.count(False)))
srv.shutdown(); sys.exit(0 if all(RES) else 1)
