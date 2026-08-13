// Unix-CTF replay renderer: draws the wasm-normalized frame stream to a single
// fixed canvas stage, with a scrubber + play transport. One camera, no scroll.
(function () {
  "use strict";

  var LW = 1000, LH = 620;                 // fixed logical stage size
  var COL = {
    ink: "#0a0e14", panel: "#121722", panel2: "#0e131c",
    line: "#1e2530", line2: "#2a3342",
    text: "#dbe2ec", muted: "#79879b", dim: "#48566a", gold: "#f5c542",
  };
  var MONO = 'ui-monospace,"JetBrains Mono","SF Mono",Menlo,Consolas,monospace';

  var cv, ctx, dpr = 1;
  var R = null;          // normalized replay
  var idx = 0;          // current frame index
  var playing = false, timer = null, speed = 1;
  var els = {};

  function mix(hex, other, t) {           // t: 0..1 fraction of `other`
    function p(h){ return [parseInt(h.slice(1,3),16),parseInt(h.slice(3,5),16),parseInt(h.slice(5,7),16)]; }
    var a = p(hex), b = p(other);
    return "rgb(" + a.map(function(v,i){ return Math.round(v*(1-t)+b[i]*t); }).join(",") + ")";
  }
  function rr(x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
  }
  function clip(s, font, maxw) {
    ctx.font = font;
    if (ctx.measureText(s).width <= maxw) return s;
    while (s.length > 1 && ctx.measureText(s + "…").width > maxw) s = s.slice(0, -1);
    return s + "…";
  }

  function setup() {
    cv = document.getElementById("stage");
    ctx = cv.getContext("2d");
    els.play = document.getElementById("play");
    els.scrub = document.getElementById("scrub");
    els.pos = document.getElementById("pos");
    els.speed = document.getElementById("speed");
    els.seeds = document.getElementById("seeds");

    els.play.onclick = function () { playing ? pause() : play(); };
    els.speed.onclick = function () { speed = speed >= 4 ? 1 : speed * 2; els.speed.textContent = speed + "×"; if (playing) { pause(); play(); } };
    els.scrub.oninput = function (e) { pause(); idx = +e.target.value; render(); };
    window.addEventListener("resize", fit);
  }

  function fit() {
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    var cssW = cv.clientWidth || LW;
    cv.width = Math.round(cssW * dpr);
    cv.height = Math.round(cssW * (LH / LW) * dpr);
    render();
  }

  function attach(norm) {
    R = norm; idx = 0;
    els.scrub.min = 0; els.scrub.max = R.frames.length; els.scrub.value = 0;
    fit();
  }

  function seedButtons(list, current, onPick) {
    els.seeds.innerHTML = "";
    list.forEach(function (s) {
      var b = document.createElement("button");
      b.textContent = "#" + s;
      b.className = "seedbtn" + (String(s) === String(current) ? " on" : "");
      b.onclick = function () { onPick(s); };
      els.seeds.appendChild(b);
    });
  }

  // ---- transport ----
  function play() {
    if (idx >= R.frames.length) { idx = 0; }
    playing = true; els.play.textContent = "❚❚";
    timer = setInterval(function () {
      if (idx >= R.frames.length) { pause(); return; }
      idx++; render();
      if (idx >= R.frames.length) pause();
    }, 1000 / speed);
  }
  function pause() { playing = false; els.play.textContent = "▶"; if (timer) { clearInterval(timer); timer = null; } }

  // ---- draw ----
  function render() {
    if (!R || !ctx) return;
    els.scrub.value = idx;
    var done = idx >= R.frames.length;
    var fr = R.frames[Math.min(idx, R.frames.length) - 1] || null;
    var tick = fr ? fr.t : 0;
    els.pos.textContent = tick + " / " + R.turnBudget;

    ctx.setTransform(dpr * (cv.width / (LW * dpr)), 0, 0, dpr * (cv.height / (LH * dpr)), 0, 0);
    // background
    ctx.fillStyle = COL.ink; ctx.fillRect(0, 0, LW, LH);
    var g = ctx.createRadialGradient(LW * 0.72, -60, 40, LW * 0.72, -60, 700);
    g.addColorStop(0, "rgba(30,45,66,0.55)"); g.addColorStop(1, "rgba(0,0,0,0)");
    ctx.fillStyle = g; ctx.fillRect(0, 0, LW, LH);

    drawHeader(tick);
    drawBoard(fr);
    drawLanes(fr, tick);
    if (done) drawEnd();
  }

  function drawHeader(tick) {
    ctx.textBaseline = "alphabetic";
    ctx.fillStyle = COL.text;
    ctx.font = "700 24px " + MONO;
    ctx.fillText("UNIX-CTF", 24, 40);
    ctx.fillStyle = COL.gold; ctx.fillText("·", 24 + ctx.measureText("UNIX-CTF").width + 8, 40);
    ctx.fillStyle = COL.text; ctx.fillText("RACE REPLAY", 24 + ctx.measureText("UNIX-CTF · ").width + 8, 40);

    ctx.font = "12px " + MONO; ctx.fillStyle = COL.muted;
    var sub = R.role.toUpperCase() + "  ·  " + R.hostname + "  ·  seed " + R.seed + "  ·  " + R.nFlags + " flags";
    ctx.fillText(sub, 24, 58);

    // tick clock, right aligned
    ctx.textAlign = "right";
    ctx.font = "11px " + MONO; ctx.fillStyle = COL.muted;
    ctx.fillText("TICK", LW - 24, 24);
    ctx.font = "700 30px " + MONO; ctx.fillStyle = COL.text;
    var t2 = String(tick).padStart(2, "0");
    ctx.fillText(t2, LW - 78, 52);
    ctx.font = "700 20px " + MONO; ctx.fillStyle = COL.dim;
    ctx.fillText("/ " + R.turnBudget, LW - 24, 52);
    ctx.textAlign = "left";
    // progress meter
    var mw = 220, mx = LW - 24 - mw, my = 62;
    ctx.fillStyle = COL.line; rr(mx, my, mw, 4, 2); ctx.fill();
    ctx.fillStyle = COL.gold; rr(mx, my, mw * (tick / R.turnBudget), 4, 2); ctx.fill();
  }

  function drawBoard(fr) {
    var x0 = 24, y0 = 84, w = LW - 48, n = R.nFlags;
    var gap = 8, cw = (w - gap * (n - 1)) / n, ch = 84;
    ctx.font = "10px " + MONO;
    for (var i = 0; i < n; i++) {
      var x = x0 + i * (cw + gap), y = y0;
      var owner = fr ? fr.owners[i] : -1;
      var claimedNow = fr && owner >= 0 && R.frames[idx - 1] && fr.moves.some(function (m) { return m.claims.indexOf(i) >= 0; });
      var c = owner >= 0 ? R.agents[owner].color : COL.line2;
      ctx.fillStyle = owner >= 0 ? mix(COL.panel2, c, 0.16) : COL.panel2;
      rr(x, y, cw, ch, 4); ctx.fill();
      ctx.lineWidth = claimedNow ? 2 : 1;
      ctx.strokeStyle = owner >= 0 ? mix(COL.line, c, 0.6) : COL.line;
      rr(x, y, cw, ch, 4); ctx.stroke();
      if (claimedNow) { ctx.save(); ctx.shadowColor = c; ctx.shadowBlur = 18; rr(x, y, cw, ch, 4); ctx.stroke(); ctx.restore(); }

      // family label
      ctx.fillStyle = owner >= 0 ? COL.text : COL.muted;
      ctx.font = "9.5px " + MONO;
      wrapLabel(R.flags[i].family.replace(/_/g, " ").toUpperCase(), x + 9, y + 17, cw - 18, 11);

      if (owner >= 0) {
        ctx.fillStyle = c; ctx.font = "700 9px " + MONO;
        ctx.fillText(R.agents[owner].name.toUpperCase(), x + 9, y + ch - 22);
        ctx.fillStyle = COL.gold; ctx.font = "9px " + MONO;
        ctx.fillText(clip(R.flags[i].token || "captured", "9px " + MONO, cw - 18), x + 9, y + ch - 9);
      } else {
        ctx.fillStyle = COL.dim; ctx.font = "10px " + MONO;
        ctx.fillText("▢ sealed", x + 9, y + ch - 10);
      }
    }
  }
  function wrapLabel(s, x, y, maxw, lh) {
    var words = s.split(" "), line = "", yy = y;
    for (var i = 0; i < words.length; i++) {
      var test = line ? line + " " + words[i] : words[i];
      if (ctx.measureText(test).width > maxw && line) { ctx.fillText(line, x, yy); line = words[i]; yy += lh; }
      else line = test;
    }
    ctx.fillText(line, x, yy);
  }

  function drawLanes(fr, tick) {
    var x0 = 24, y0 = 188, w = LW - 48, n = R.agents.length;
    var gap = 10, lh = (LH - y0 - 24 - gap * (n - 1)) / n;
    for (var a = 0; a < n; a++) {
      var y = y0 + a * (lh + gap);
      var c = R.agents[a].color;
      var score = fr ? fr.scores[a] : 0;
      var mv = fr ? fr.moves[a] : null;
      var captured = mv && mv.claims.length > 0;

      // card
      ctx.fillStyle = mix(COL.panel, c, 0.05); rr(x0, y, w, lh, 5); ctx.fill();
      ctx.strokeStyle = COL.line; ctx.lineWidth = 1; rr(x0, y, w, lh, 5); ctx.stroke();
      // left accent
      ctx.fillStyle = c; rr(x0, y, 3, lh, 2); ctx.fill();
      if (captured) { ctx.save(); ctx.shadowColor = c; ctx.shadowBlur = 22; ctx.strokeStyle = mix(COL.line, c, 0.7); rr(x0, y, w, lh, 5); ctx.stroke(); ctx.restore(); }

      var px = x0 + 18, py = y + 26;
      // name + dot
      ctx.fillStyle = c; ctx.beginPath(); ctx.arc(px + 4, py - 5, 5, 0, 7); ctx.fill();
      ctx.fillStyle = COL.text; ctx.font = "700 16px " + MONO;
      ctx.fillText(R.agents[a].name, px + 16, py);
      // score right
      ctx.textAlign = "right";
      ctx.fillStyle = c; ctx.font = "700 26px " + MONO;
      ctx.fillText(String(score), x0 + w - 60, py + 6);
      ctx.fillStyle = COL.muted; ctx.font = "15px " + MONO;
      ctx.fillText("/ " + R.nFlags, x0 + w - 18, py + 6);
      ctx.textAlign = "left";

      // progress track with n gates
      var tx = px + 16, tw = w - 220, ty = y + 40, th = 6;
      ctx.fillStyle = COL.line; rr(tx, ty, tw, th, 3); ctx.fill();
      ctx.fillStyle = mix(COL.panel, c, 0.85); rr(tx, ty, tw * (score / R.nFlags), th, 3); ctx.fill();
      for (var k = 1; k < R.nFlags; k++) {
        var gx = tx + tw * (k / R.nFlags);
        ctx.fillStyle = COL.panel2; ctx.fillRect(gx - 0.5, ty - 1, 1, th + 2);
      }
      // marker
      var mxp = tx + tw * (score / R.nFlags);
      ctx.fillStyle = c; ctx.beginPath(); ctx.arc(mxp, ty + th / 2, 5, 0, 7); ctx.fill();

      // command ticker
      var cy = y + 66;
      ctx.fillStyle = COL.dim; ctx.font = "11px " + MONO;
      ctx.fillText("~/" + (mv && mv.cwd && mv.cwd !== "." ? mv.cwd : ""), px, cy);
      if (mv) {
        ctx.fillStyle = c; ctx.font = "700 12.5px " + MONO; ctx.fillText("$", px, cy + 20);
        ctx.fillStyle = COL.text; ctx.font = "12.5px " + MONO;
        ctx.fillText(clip(mv.cmd, "12.5px " + MONO, w - 60), px + 16, cy + 20);
        if (captured) {
          ctx.fillStyle = c; ctx.font = "700 11.5px " + MONO;
          var fams = mv.claims.map(function (ci) { return R.flags[ci].family.replace(/_/g, " "); }).join(", ");
          ctx.fillText("✓ captured " + fams, px, cy + 40);
        } else {
          ctx.fillStyle = COL.muted; ctx.font = "11.5px " + MONO;
          var out = (mv.out || "").split("\n")[0] || "— no flag —";
          ctx.fillText(clip(out, "11.5px " + MONO, w - 60), px, cy + 40);
        }
      } else {
        ctx.fillStyle = COL.dim; ctx.font = "italic 12px " + MONO;
        ctx.fillText("awaiting start", px, cy + 20);
      }
    }
  }

  function drawEnd() {
    var std = R.agents.map(function (a, i) { return { name: a.name, color: a.color, s: R.frames[R.frames.length - 1].scores[i] }; })
      .sort(function (x, y) { return y.s - x.s; });
    var win = std[0];
    ctx.fillStyle = "rgba(8,11,18,0.72)"; ctx.fillRect(0, 0, LW, LH);
    ctx.textAlign = "center";
    ctx.fillStyle = COL.muted; ctx.font = "12px " + MONO;
    ctx.fillText("RUN COMPLETE", LW / 2, LH / 2 - 70);
    ctx.fillStyle = win.color; ctx.font = "700 40px " + MONO;
    ctx.fillText(win.name + " wins", LW / 2, LH / 2 - 24);
    ctx.font = "16px " + MONO;
    var gap = 150, startx = LW / 2 - gap;
    std.forEach(function (a, i) {
      ctx.fillStyle = a.color; ctx.font = "700 15px " + MONO;
      ctx.fillText(a.name, startx + i * gap, LH / 2 + 26);
      ctx.fillStyle = COL.text; ctx.font = "700 26px " + MONO;
      ctx.fillText(a.s + "/" + R.nFlags, startx + i * gap, LH / 2 + 58);
    });
    ctx.textAlign = "left";
  }

  window.UnixctfViewer = { setup: setup, attach: attach, seedButtons: seedButtons };
})();
