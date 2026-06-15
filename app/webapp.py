"""Flask web UI + JSON API for controlling the Terraria server."""
from flask import Flask, Response, jsonify, request

import config
from monitor import parse_players

INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Terraria Control</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body { margin: 0; font-family: system-ui, sans-serif; background: #11151c; color: #e6e9ef; }
  header { padding: 12px 18px; background: #1b2230; display: flex; gap: 16px; align-items: center; flex-wrap: wrap; }
  header h1 { font-size: 18px; margin: 0; }
  .pill { font-size: 12px; padding: 2px 8px; border-radius: 10px; background: #2a3344; }
  .pill.ok { background: #1f6f3f; } .pill.bad { background: #8a2b2b; }
  main { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; padding: 16px; }
  section { background: #161b25; border: 1px solid #232c3b; border-radius: 8px; padding: 12px; }
  section h2 { margin: 0 0 10px; font-size: 14px; text-transform: uppercase; letter-spacing: .04em; color: #9fb0c9; }
  #console { grid-column: 1 / 3; }
  pre#log { background: #0c0f15; padding: 10px; border-radius: 6px; height: 280px; overflow-y: auto;
            margin: 0 0 10px; font-size: 12.5px; line-height: 1.45; white-space: pre-wrap; }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid #232c3b; }
  input, button { font: inherit; }
  input[type=text] { background: #0c0f15; border: 1px solid #2a3344; color: #e6e9ef; padding: 7px 9px; border-radius: 6px; }
  .row { display: flex; gap: 8px; flex-wrap: wrap; }
  .row input[type=text] { flex: 1; min-width: 120px; }
  button { background: #2a3344; color: #e6e9ef; border: 1px solid #38465c; padding: 7px 12px; border-radius: 6px; cursor: pointer; }
  button:hover { background: #344056; }
  button.warn { background: #6b3a18; border-color: #84491f; }
  button.danger { background: #7a2530; border-color: #99303d; }
  .muted { color: #7e8aa0; font-size: 12px; }
  .hint { font-size: 11px; color: #7e8aa0; }
  @media (max-width: 820px) { main { grid-template-columns: 1fr; } #console { grid-column: auto; } }
</style>
</head>
<body>
<header>
  <h1>Terraria Control</h1>
  <span class="pill" id="st-container"></span>
  <span class="pill" id="st-docker"></span>
  <span class="pill" id="st-screen"></span>
  <span class="pill" id="st-fw"></span>
  <span class="muted" id="st-error"></span>
</header>
<main>
  <section id="console">
    <h2>Console</h2>
    <pre id="log">Loading…</pre>
    <form class="row" id="cmd-form">
      <input type="text" id="cmd" placeholder="Type a command, e.g. help, playing, say hello" autocomplete="off">
      <button type="submit">Send</button>
      <button type="button" data-cmd="help">help</button>
      <button type="button" data-cmd="playing">playing</button>
      <button type="button" data-cmd="time">time</button>
    </form>
    <p class="hint">Commands are sent straight to the server console. Output appears in the log above.</p>
  </section>

  <section>
    <h2>Players online <button type="button" id="refresh-players">Refresh</button></h2>
    <table id="players"><thead><tr><th>Name</th><th>IP</th><th>Since</th><th></th></tr></thead><tbody></tbody></table>
  </section>

  <section>
    <h2>Blacklisted IPs (dropped)</h2>
    <table id="blacklist"><thead><tr><th>IP</th><th>Reason</th><th></th></tr></thead><tbody></tbody></table>
    <form class="row" id="bl-form" style="margin-top:10px">
      <input type="text" id="bl-ip" placeholder="IP address">
      <input type="text" id="bl-reason" placeholder="reason (optional)">
      <button type="submit" class="danger">Blacklist</button>
    </form>
  </section>

  <section>
    <h2>Whitelisted IPs (never auto-blacklisted)</h2>
    <table id="whitelist"><thead><tr><th>IP</th><th>Note</th><th></th></tr></thead><tbody></tbody></table>
    <form class="row" id="wl-form" style="margin-top:10px">
      <input type="text" id="wl-ip" placeholder="IP address">
      <input type="text" id="wl-note" placeholder="note (optional)">
      <button type="submit">Whitelist</button>
    </form>
  </section>
</main>
<script>
const $ = (s) => document.querySelector(s);
async function api(path, body) {
  const opt = { method: body ? "POST" : "GET", headers: { "Content-Type": "application/json" } };
  if (body) opt.body = JSON.stringify(body);
  const r = await fetch(path, opt);
  return r.json();
}
function pill(id, text, ok) {
  const el = $(id); el.textContent = text;
  el.className = "pill" + (ok === true ? " ok" : ok === false ? " bad" : "");
}
function render(s) {
  pill("#st-container", "container: " + s.status.container);
  pill("#st-docker", "docker: " + s.status.docker, s.status.docker === "connected");
  pill("#st-screen", "console: " + (s.status.screen ? s.status.screen : "not found"), !!s.status.screen);
  pill("#st-fw", "firewall: " + s.status.firewall, s.status.firewall === "ready" ? true : s.status.firewall === "error" ? false : null);
  $("#st-error").textContent = s.status.last_error || "";

  const log = $("#log"); const atBottom = log.scrollTop + log.clientHeight >= log.scrollHeight - 20;
  log.textContent = s.console.join("\n");
  if (atBottom) log.scrollTop = log.scrollHeight;

  $("#players tbody").innerHTML = s.players.map(p =>
    `<tr><td>${esc(p.name)}</td><td>${esc(p.ip || "?")}</td><td>${esc(p.joined_at || "")}</td>
     <td><button class="warn" onclick="kick('${esc(p.name)}')">kick</button>
         <button class="danger" onclick="ban('${esc(p.name)}')">ban</button></td></tr>`).join("")
    || `<tr><td colspan="4" class="muted">No players online</td></tr>`;

  $("#blacklist tbody").innerHTML = s.blacklist.map(b =>
    `<tr><td>${esc(b.ip)}</td><td>${esc(b.reason || "")}</td>
     <td><button onclick="unbl('${esc(b.ip)}')">remove</button></td></tr>`).join("")
    || `<tr><td colspan="3" class="muted">Empty</td></tr>`;

  $("#whitelist tbody").innerHTML = s.whitelist.map(w =>
    `<tr><td>${esc(w.ip)}</td><td>${esc(w.note || "")}</td>
     <td><button onclick="unwl('${esc(w.ip)}')">remove</button></td></tr>`).join("")
    || `<tr><td colspan="3" class="muted">Empty</td></tr>`;
}
function esc(s) { return String(s).replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c])); }

async function refresh() { try { render(await api("/api/state")); } catch (e) {} }
async function kick(n) { if (confirm("Kick " + n + "?")) { await api("/api/kick", { name: n }); refresh(); } }
async function ban(n) { if (confirm("Ban " + n + "? (Terraria ban)")) { await api("/api/ban", { name: n }); refresh(); } }
async function unbl(ip) { await api("/api/blacklist/remove", { ip }); refresh(); }
async function unwl(ip) { await api("/api/whitelist/remove", { ip }); refresh(); }

$("#cmd-form").addEventListener("submit", async (e) => {
  e.preventDefault(); const v = $("#cmd").value.trim(); if (!v) return;
  $("#cmd").value = ""; await api("/api/command", { command: v }); setTimeout(refresh, 400);
});
document.querySelectorAll("[data-cmd]").forEach(b =>
  b.addEventListener("click", async () => { await api("/api/command", { command: b.dataset.cmd }); setTimeout(refresh, 400); }));
$("#refresh-players").addEventListener("click", async () => { await api("/api/players/refresh", {}); refresh(); });
$("#bl-form").addEventListener("submit", async (e) => {
  e.preventDefault(); await api("/api/blacklist", { ip: $("#bl-ip").value.trim(), reason: $("#bl-reason").value.trim() });
  $("#bl-ip").value = ""; $("#bl-reason").value = ""; refresh(); });
$("#wl-form").addEventListener("submit", async (e) => {
  e.preventDefault(); await api("/api/whitelist", { ip: $("#wl-ip").value.trim(), note: $("#wl-note").value.trim() });
  $("#wl-ip").value = ""; $("#wl-note").value = ""; refresh(); });

refresh(); setInterval(refresh, 3000);
</script>
</body>
</html>"""


def _check_auth() -> bool:
    if not config.WEB_PASSWORD:
        return True
    auth = request.authorization
    return bool(auth and auth.username == config.WEB_USER and auth.password == config.WEB_PASSWORD)


def create_app(store, control, firewall) -> Flask:
    app = Flask(__name__)

    @app.before_request
    def _require_auth():
        if request.path == "/healthz" or _check_auth():
            return None
        return Response(
            "Authentication required", 401,
            {"WWW-Authenticate": 'Basic realm="Terraria Control"'},
        )

    def _ip(data):
        ip = (data.get("ip") or "").strip()
        if not ip:
            raise ValueError("ip is required")
        return ip

    @app.get("/healthz")
    def healthz():
        return "ok", 200

    @app.get("/")
    def index():
        return INDEX_HTML

    @app.get("/api/state")
    def state():
        return jsonify(store.snapshot())

    @app.post("/api/command")
    def command():
        cmd = (request.get_json(silent=True) or {}).get("command", "")
        try:
            output = control.run_capture(cmd)
            return jsonify(ok=True, output=output)
        except Exception as error:  # noqa: BLE001
            return jsonify(ok=False, error=str(error)), 400

    @app.post("/api/kick")
    def kick():
        name = (request.get_json(silent=True) or {}).get("name", "").strip()
        if not name:
            return jsonify(ok=False, error="name required"), 400
        try:
            control.send_command(f"kick {name}")
            return jsonify(ok=True)
        except Exception as error:  # noqa: BLE001
            return jsonify(ok=False, error=str(error)), 400

    @app.post("/api/ban")
    def ban():
        name = (request.get_json(silent=True) or {}).get("name", "").strip()
        if not name:
            return jsonify(ok=False, error="name required"), 400
        try:
            control.send_command(f"ban {name}")
            return jsonify(ok=True)
        except Exception as error:  # noqa: BLE001
            return jsonify(ok=False, error=str(error)), 400

    @app.post("/api/players/refresh")
    def players_refresh():
        try:
            lines = control.run_capture("playing")
            store.replace_players(parse_players(lines))
            return jsonify(ok=True)
        except Exception as error:  # noqa: BLE001
            return jsonify(ok=False, error=str(error)), 400

    @app.post("/api/blacklist")
    def blacklist_add():
        data = request.get_json(silent=True) or {}
        try:
            ip = _ip(data)
        except ValueError as error:
            return jsonify(ok=False, error=str(error)), 400
        store.blacklist_add(ip, data.get("reason", "manual"), auto=False)
        firewall.add(ip)
        return jsonify(ok=True)

    @app.post("/api/blacklist/remove")
    def blacklist_remove():
        data = request.get_json(silent=True) or {}
        try:
            ip = _ip(data)
        except ValueError as error:
            return jsonify(ok=False, error=str(error)), 400
        store.blacklist_remove(ip)
        firewall.remove(ip)
        return jsonify(ok=True)

    @app.post("/api/whitelist")
    def whitelist_add():
        data = request.get_json(silent=True) or {}
        try:
            ip = _ip(data)
        except ValueError as error:
            return jsonify(ok=False, error=str(error)), 400
        store.whitelist_add(ip, data.get("note", ""))
        # Whitelisting trumps any existing blacklist entry.
        if store.blacklist_remove(ip):
            firewall.remove(ip)
        return jsonify(ok=True)

    @app.post("/api/whitelist/remove")
    def whitelist_remove():
        data = request.get_json(silent=True) or {}
        try:
            ip = _ip(data)
        except ValueError as error:
            return jsonify(ok=False, error=str(error)), 400
        store.whitelist_remove(ip)
        return jsonify(ok=True)

    return app
