// Lance le script Python embarqué (py/) avec python3 ; aucun code de vérification en JavaScript.
const { spawnSync } = require("child_process");
const path = require("path");
module.exports = (script) => {
  const py = process.env.PYTHON || "python3";
  const r = spawnSync(py, ["-I", path.join(__dirname, "..", "py", script), ...process.argv.slice(2)], { stdio: "inherit" });
  if (r.error) { console.error("legion-lock : python3 (3.8+) introuvable sur PATH (" + r.error.code + ")"); process.exit(2); }
  process.exit(r.status === null ? 2 : r.status);
};
