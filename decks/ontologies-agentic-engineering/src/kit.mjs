// House rules for every slide, set on slides 1 and 2.
// - No eyebrow and no reference strip. A title, short labels, one caption per hold (cap).
// - The orange dot sits on the thing being discussed. It travels along lines, and lines start at it.
// - The agent is the robot: confused when guessing, surprised when blocked, happy when guided.
//   A block is the shield.
// - Show the problem first, then the fix. One idea per hold; the scene before it leaves.
// - Numbers and names on screen are sourced or marked illustrative. Sources live in the notes;
//   a short credit (src) stays only where the slide shows someone else's number or words.
export const esc = (s) =>
  String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

const r = (n) => Math.round(n * 100) / 100;

export function seeded(seed) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

let faceCount = 0;

export function kit() {
  const out = [];
  const cursor = {};

  const anim = (o, type) => {
    const b = o.b ?? 1;
    const at = o.at ?? cursor[b] ?? 0;
    cursor[b] = r(at + (o.gap ?? 0.06));
    let s = `data-b="${b}" data-a="${o.a ?? type}" data-at="${r(at)}"`;
    if (o.dur != null) s += ` data-dur="${o.dur}"`;
    if (o.x != null) s += ` data-x="${o.x}"`;
    return s;
  };
  const stroke = (o) => `s${o.dash ? " dash" : ""}${o.hair ? " hair" : ""}`;

  const k = {
    raw(s) {
      out.push(s);
      return k;
    },
    path(d, o = {}) {
      out.push(`<path class="${stroke(o)}" d="${d}" ${anim(o, "draw")}/>`);
      return k;
    },
    line(x1, y1, x2, y2, o = {}) {
      return k.path(`M${x1} ${y1}L${x2} ${y2}`, o);
    },
    head(x1, y1, x2, y2, o = {}) {
      const a = Math.atan2(y2 - y1, x2 - x1);
      const p = (w) => `${r(x2 - 14 * Math.cos(a + w))} ${r(y2 - 14 * Math.sin(a + w))}`;
      out.push(`<path class="s" d="M${p(0.42)}L${x2} ${y2}L${p(-0.42)}" ${anim(o, "pop")}/>`);
      return k;
    },
    arrow(x1, y1, x2, y2, o = {}) {
      const b = o.b ?? 1;
      const at = o.at ?? cursor[b] ?? 0;
      const dur = o.dur ?? 0.55;
      k.line(x1, y1, x2, y2, { ...o, at, dur });
      return k.head(x1, y1, x2, y2, { b, at: r(at + dur * 0.92), x: o.x });
    },
    rect(x, y, w, h, o = {}) {
      out.push(
        `<rect class="${stroke(o)}" x="${x}" y="${y}" width="${w}" height="${h}" ${anim(o, "draw")}/>`,
      );
      return k;
    },
    circ(cx, cy, rad, o = {}) {
      out.push(`<circle class="${stroke(o)}" cx="${cx}" cy="${cy}" r="${rad}" ${anim(o, "draw")}/>`);
      return k;
    },
    sq(cx, cy, o = {}) {
      const s = o.size ?? 16;
      out.push(
        `<rect class="${o.solid ? "f" : "s"}" x="${cx - s / 2}" y="${cy - s / 2}" width="${s}" height="${s}" ${anim(o, "snap")}/>`,
      );
      return k;
    },
    acc(cx, cy, o = {}) {
      out.push(`<circle class="acc" cx="${cx}" cy="${cy}" r="5" ${anim(o, "pop")}/>`);
      return k;
    },
    brk(x, y, w, h, o = {}) {
      const l = o.len ?? 22;
      const d =
        `M${x} ${y + l}V${y}H${x + l}` +
        `M${x + w - l} ${y}H${x + w}V${y + l}` +
        `M${x + w} ${y + h - l}V${y + h}H${x + w - l}` +
        `M${x + l} ${y + h}H${x}V${y + h - l}`;
      out.push(`<path class="s" d="${d}" ${anim(o, "snap")}/>`);
      return k;
    },
    text(x, y, s, o = {}) {
      const anchor = o.anchor ? ` text-anchor="${o.anchor}"` : "";
      const overlap = o.overlap ? " data-layout-allow-overlap" : "";
      out.push(
        `<text class="${o.c ?? "m1"}" x="${x}" y="${y}"${anchor}${overlap} ${anim(o, "fade")}>${o.html ? s : esc(s)}</text>`,
      );
      return k;
    },
    ring(cx, cy, R, o = {}) {
      const rand = seeded(o.seed ?? 7);
      const dots = [];
      [
        [34, 1],
        [28, 0.79],
      ].forEach(([n, scale], j) => {
        for (let i = 0; i < n; i++) {
          const a = (2 * Math.PI * i) / n + (rand() - 0.5) * 0.07 + j * 0.09;
          const rad = R * scale * (1 + 0.035 * Math.sin(5 * a + j * 1.3)) + (rand() - 0.5) * R * 0.05;
          dots.push([a, cx + rad * Math.cos(a), cy + rad * Math.sin(a)]);
        }
      });
      dots.sort((p, q) => p[0] - q[0]);
      const dotR = r(Math.max(2.2, R * 0.03));
      const circles = dots
        .map(([, x, y]) => `<circle class="f" cx="${r(x)}" cy="${r(y)}" r="${dotR}"/>`)
        .join("");
      out.push(`<g ${anim(o, "dots")}>${circles}</g>`);
      return k;
    },
    grid(cx, cy, size, o = {}) {
      const half = size / 2;
      const cell = size / 3;
      const over = size * 0.09;
      const b = o.b ?? 1;
      let at = o.at ?? cursor[b] ?? 0;
      for (let i = 0; i < 4; i++) {
        const v = r(cx - half + i * cell);
        const h = r(cy - half + i * cell);
        k.line(v, cy - half - over, v, cy + half + over, { b, at: r(at), dur: 0.5, x: o.x });
        k.line(cx - half - over, h, cx + half + over, h, { b, at: r(at + 0.04), dur: 0.5, x: o.x });
        at += 0.07;
      }
      const centre = (col, row) => [r(cx - half + (col + 0.5) * cell), r(cy - half + (row + 0.5) * cell)];
      [
        [0, 2],
        [1, 1],
        [2, 0],
      ].forEach(([col, row], i) => {
        const [x, y] = centre(col, row);
        k.sq(x, y, { b, at: r(at + 0.3 + i * 0.08), size: Math.max(16, size * 0.085), x: o.x });
      });
      return centre;
    },
    gauge(cx, cy, R, o = {}) {
      const b = o.b ?? 1;
      const at = o.at ?? cursor[b] ?? 0;
      const deg = o.deg ?? 55;
      const a = (deg * Math.PI) / 180;
      const tip = [r(cx + R * Math.cos(a)), r(cy - R * Math.sin(a))];
      k.path(`M${cx - R} ${cy}A${R} ${R} 0 0 1 ${cx + R} ${cy}`, { b, at, dur: 0.7, x: o.x });
      k.circ(cx, cy, 6, { b, at: r(at + 0.3), dur: 0.2, x: o.x });
      if (!o.bare) k.line(cx, cy, tip[0], tip[1], { b, at: r(at + 0.45), dur: 0.4, x: o.x });
      if (o.frame !== false) {
        const pad = R * 0.28;
        k.brk(cx - R - pad, cy - R - pad, 2 * (R + pad), R + 2 * pad, {
          b,
          at: r(at + 0.1),
          len: Math.max(18, R * 0.3),
          x: o.x,
        });
      }
      return tip;
    },
    // moods is an ordered list of { face, b, at }: each face replaces the one before it.
    robot(cx, cy, s = 1, o = {}) {
      const b = o.b ?? 1;
      const step = o.step ?? 0.07;
      const moods = o.moods ?? [];
      const X = (v) => r(cx + v * s);
      const Y = (v) => r(cy + (v + 21) * s);
      const L = (v) => r(v * s);
      let n = 0;
      const next = () => r((o.at ?? 0) + n++ * step);
      const enter = (type, dur) => (o.plain ? "" : " " + anim({ b, at: next(), dur }, type));
      const base = { until: moods[0] };
      const span = (i) => ({ from: moods[i], until: moods[i + 1] });
      const comes = (t, extra, type, dur) =>
        t.from ? " " + anim({ b: t.from.b, at: r(t.from.at + extra), dur }, type) : enter(type, dur);
      const goes = (t) => (t.until ? ` data-x="${t.until.b}" data-xat="${t.until.at}"` : "");
      const line = (t, d, extra = 0, dur = 0.2) =>
        out.push(`<path class="s" d="${d}"${comes(t, extra, "draw", dur)}${goes(t)}/>`);
      const rounded = (x, y, w, h, radius) =>
        out.push(
          `<rect class="s" x="${X(x)}" y="${Y(y)}" width="${L(w)}" height="${L(h)}" rx="${L(radius)}"${enter("draw", 0.5)}/>`,
        );
      const ring = (x, y, radius, attrs) =>
        out.push(`<circle class="s" cx="${X(x)}" cy="${Y(y)}" r="${L(radius)}"${attrs ?? enter("draw", 0.25)}/>`);
      // Both eyes of one face share a mind, so they blink and look together.
      const eyes = (t, tempo = "calm") => {
        const face = `face-${++faceCount}`;
        [-34, 34].forEach((ex) => {
          out.push(`<g data-idle="wink" data-face="${face}" data-origin="${X(ex)} ${Y(-66)}"${goes(t)}>`);
          ring(ex, -66, 14, comes(t, 0, "draw", 0.2));
          out.push(
            `<circle class="f" cx="${X(ex)}" cy="${Y(-66)}" r="${L(5)}" data-idle="look" data-face="${face}" data-tempo="${tempo}" data-amp="${L(5)}"${comes(t, 0.1, "pop")}/>`,
          );
          out.push(`</g>`);
        });
      };
      const mark = (t, glyph) =>
        out.push(
          `<text class="t1" x="${X(-112)}" y="${Y(-112)}" text-anchor="end"${comes(t, 0.3, "fade")}${goes(t)}>${glyph}</text>`,
        );
      const faces = {
        confused(t) {
          eyes(t, "fast");
          line(t, `M${X(-21)} ${Y(-30)}q${L(5.25)} ${L(-8)} ${L(10.5)} 0t${L(10.5)} 0t${L(10.5)} 0t${L(10.5)} 0`, 0.05);
          line(t, `M${X(-48)} ${Y(-93)}L${X(-20)} ${Y(-101)}`, 0.1);
          line(t, `M${X(20)} ${Y(-87)}L${X(48)} ${Y(-85)}`, 0.16);
          mark(t, "?");
        },
        blocked(t) {
          eyes(t, "stare");
          [-34, 34].forEach((ex) =>
            line(t, `M${X(ex - 13)} ${Y(-92)}Q${X(ex)} ${Y(-103)} ${X(ex + 13)} ${Y(-92)}`, 0.1, 0.15),
          );
          out.push(
            `<circle class="s" cx="${X(0)}" cy="${Y(-32)}" r="${L(7)}"${comes(t, 0.2, "draw", 0.15)}${goes(t)}/>`,
          );
          mark(t, "!");
        },
        happy(t) {
          [-34, 34].forEach((ex, i) =>
            line(t, `M${X(ex - 14)} ${Y(-60)}Q${X(ex)} ${Y(-82)} ${X(ex + 14)} ${Y(-60)}`, 0.1 + i * 0.05),
          );
          line(t, `M${X(-24)} ${Y(-38)}Q${X(0)} ${Y(-14)} ${X(24)} ${Y(-38)}`, 0.2);
          [-26, 0, 26].forEach((lx, i) =>
            out.push(
              `<circle class="f" cx="${X(lx)}" cy="${Y(70)}" r="${L(3.6)}"${comes(t, 0.25 + i * 0.08, "pop")}${goes(t)}/>`,
            ),
          );
        },
      };

      line({}, `M${X(0)} ${Y(-118)}V${Y(-150)}`);
      ring(0, -161, 11);
      rounded(-80, -118, 160, 110, 22);
      rounded(-93, -80, 13, 34, 0);
      rounded(80, -80, 13, 34, 0);
      eyes(base);
      line(base, `M${X(-20)} ${Y(-30)}H${X(20)}`);
      line({}, `M${X(-14)} ${Y(-8)}V${Y(10)}`, 0, 0.1);
      line({}, `M${X(14)} ${Y(-8)}V${Y(10)}`, 0, 0.1);
      rounded(-100, 10, 200, 120, 18);
      [-1, 1].forEach((side) =>
        out.push(
          `<path class="s" d="M${X(side * 100)} ${Y(42)}H${X(side * 128)}V${Y(104)}" data-idle="sway" data-origin="${X(side * 100)} ${Y(42)}" data-amp="${side * 2.6}" data-phase="${r(faceCount * 1.7 + side)}"${enter("draw", 0.25)}/>`,
        ),
      );
      let lights = "";
      [-26, 0, 26].forEach((lx) => {
        ring(lx, 70, 7.5);
        lights += `<circle class="f" cx="${X(lx)}" cy="${Y(70)}" r="${L(3.6)}" style="opacity: 0"/>`;
      });
      const calm = moods.find((m) => m.face === "happy");
      out.push(
        `<g data-idle="think" data-rest="1.1"${o.plain ? ` data-b="${b}"` : enter("pop")}${goes({ until: calm })}>${lights}</g>`,
      );
      moods.forEach((mood, i) => faces[mood.face](span(i)));
      return { tip: [X(0), Y(-161)], right: X(128), bottom: Y(130) };
    },
    // The one caption for a hold, bottom right. It leaves when the next hold starts unless kept.
    cap(text, b, o = {}) {
      return k.text(1780, 952, text, {
        b,
        at: o.at ?? 1.5,
        anchor: "end",
        x: o.keep ? null : b + 1,
        overlap: true,
      });
    },
    src(text, o = {}) {
      return k.text(120, 952, text, { b: o.b ?? 1, at: o.at ?? 1.2, c: "m2", x: o.x });
    },
    // The robot as one piece: it snaps in whole and can leave whole.
    bot(cx, cy, s, o = {}) {
      const b = o.b ?? 1;
      out.push(`<g ${anim({ b, at: o.at ?? 0, dur: 0.35, x: o.x }, "snap")}>`);
      const shape = k.robot(cx, cy, s, { b, plain: true, moods: o.moods });
      out.push(`</g>`);
      return shape;
    },
    shield(x, y, o = {}) {
      const at = o.at ?? 0;
      out.push(
        `<g ${anim({ b: o.b ?? 1, at, dur: 0.25, x: o.x }, "snap")}${o.xat != null ? ` data-xat="${o.xat}"` : ""}>` +
          `<path class="s bgf" d="M${x} ${y - 24}L${x + 19} ${y - 16}V${y + 2}C${x + 19} ${y + 15} ${x + 10} ${y + 22} ${x} ${y + 27}C${x - 10} ${y + 22} ${x - 19} ${y + 15} ${x - 19} ${y + 2}V${y - 16}Z"/>` +
          `<path class="s" d="M${x - 9} ${y}H${x + 9}"/></g>`,
      );
      return k;
    },
    chip(x, y, w, label, o = {}) {
      out.push(
        `<rect class="${stroke(o)}" x="${x}" y="${y - 28}" width="${w}" height="56" rx="10" ${anim({ ...o, dur: o.dur ?? 0.4 }, "draw")}${o.xat != null ? ` data-xat="${o.xat}"` : ""}/>`,
      );
      return k.text(x + w / 2, y + 10, label, {
        b: o.b,
        at: (o.at ?? 0) + 0.15,
        x: o.x,
        c: o.c ?? "cd",
        anchor: "middle",
      });
    },
    mk(cx, cy, o = {}) {
      out.push(
        `<rect class="mk" x="${cx - 5}" y="${cy - 5}" width="10" height="10" data-b="${o.b ?? 1}" data-at="${o.at ?? 0.1}"${o.snap ? " data-snap" : ""}${o.dur != null ? ` data-dur="${o.dur}"` : ""}${o.via ? ` data-via="${o.via}"` : ""}${o.on ? ` data-on="${o.on}"` : ""}${o.dx != null ? ` data-dx="${o.dx}"` : ""}${o.dy != null ? ` data-dy="${o.dy}"` : ""}${o.s != null ? ` data-s="${o.s}"` : ""}${o.hide ? ` data-hide="${o.hide}"` : ""}/>`,
      );
      return k;
    },
    svg() {
      return out.join("\n");
    },
  };
  return k;
}
