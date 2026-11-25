import { kit, seeded } from "../kit.mjs";

const r = (n) => Math.round(n * 100) / 100;

// The robot hangs from the dot of the headline's "i". TIP is roughly where that dot
// is; the engine measures the real spot, pins the robot to it, and later moves the
// pair so the dot lands exactly on ORIGIN, where every path starts.
const TIP = [958, 490];
const BOT = [TIP[0], TIP[1] + 140];
const ORIGIN = [430, 540];
const START = ORIGIN[0] + 16;
const CY = ORIGIN[1];
const GUARD = [1240, 540];
const DOT = 16.7;

const ends = [
  [1010, 236],
  [1392, 204],
  [1716, 312],
  [1196, 438],
  [1560, 486],
  [1744, 628],
  [1330, 668],
  [1052, 812],
  [1628, 846],
];

function specks() {
  const rand = seeded(23);
  let marks = "";
  for (let i = 0; i < 48; i++) {
    const x = r(690 + rand() * 1060);
    const y = r(200 + rand() * 680);
    const kind = Math.floor(rand() * 3);
    const turn = r(rand() * 180);
    if (ends.some(([ex, ey]) => Math.hypot(ex - x, ey - y) < 34)) continue;
    if (kind === 0) marks += `<circle class="f" cx="${x}" cy="${y}" r="2.6"/>`;
    else if (kind === 1) {
      marks += `<path class="s" d="M${x - 8} ${y}H${x + 8}" transform="rotate(${turn} ${x} ${y})"/>`;
    } else {
      marks += `<rect class="s" x="${x - 5}" y="${y - 5}" width="10" height="10" transform="rotate(${turn} ${x} ${y})"/>`;
    }
  }
  return `<g data-b="3" data-a="dots" data-at="0.45" data-dur="0.012" data-x="4">${marks}</g>`;
}

export default {
  id: "s01",
  bare: true,
  holds: 5,
  eyebrow: "01 / OVERVIEW",
  title: ["Neurosymbolic engineering"],
  css: `      .c-title {
        position: absolute;
        left: 0;
        right: 0;
        top: 468px;
        text-align: center;
        font-size: 116px;
        font-weight: 600;
        line-height: 1.05;
        letter-spacing: -0.035em;
      }
      .tittle {
        display: inline-block;
        position: relative;
        width: 0;
        height: 0;
        vertical-align: baseline;
      }
      #s01-tittle {
        position: absolute;
        left: 0.059em;
        bottom: 0.6205em;
        width: 0.144em;
        height: 0.144em;
      }
      .c-sub {
        position: absolute;
        left: 0;
        right: 0;
        top: 628px;
        text-align: center;
        font-family: "JetBrains Mono", monospace;
        font-size: 28px;
        letter-spacing: 0.08em;
        color: #73736d;
      }`,
  body() {
    const k = kit();
    const [gx, gy] = GUARD;
    k.mk(0, 0, { b: 1, on: "#s01-tittle" });

    k.raw(`<g data-dock="#s01-tittle" data-dock-x="${TIP[0]}" data-dock-y="${TIP[1]}">`);
    k.raw(`<g data-shift-b="3" data-shift-from="#s01-tittle" data-shift-to="${ORIGIN.join(",")}">`);
    k.raw(`<g data-b="2" data-a="zoom" data-at="0.15" data-dur="1" data-origin="${TIP[0]} ${TIP[1]}">`);
    k.robot(BOT[0], BOT[1], 1, {
      b: 2,
      plain: true,
      moods: [
        { face: "confused", b: 3, at: 0.5 },
        { face: "blocked", b: 4, at: 2.05 },
        { face: "happy", b: 5, at: 1.9 },
      ],
    });
    k.raw(`</g>`);
    k.text(BOT[0], BOT[1] + 212, "PROBABILISTIC AGENT", { b: 2, at: 0.95, anchor: "middle" });
    k.raw(`</g></g>`);

    k.mk(ORIGIN[0], ORIGIN[1], { b: 3, at: 0, dur: 0.9, s: DOT });
    k.raw(specks());
    const rand = seeded(41);
    let picks = "";
    ends.forEach(([x, y], i) => {
      const at = r(0.9 + i * 0.06);
      const c1 = `${START + 240} ${r(CY + (y - CY) * 0.05 + (rand() - 0.5) * 80)}`;
      const c2 = `${x - 240} ${r(y + (rand() - 0.5) * 180)}`;
      k.path(`M${START} ${CY}C${c1} ${c2} ${x - 11} ${y}`, { b: 3, at, dur: 0.8, dash: true, x: 4 });
      k.circ(x, y, 10, { b: 3, at: r(at + 0.72), dur: 0.2, x: 4 });
      picks += `<circle class="f" cx="${x}" cy="${y}" r="5" style="opacity: 0"/>`;
    });
    k.raw(`<g data-idle="hop" data-b="3" data-a="pop" data-at="2.1" data-x="4">${picks}</g>`);
    k.text(1780, 952, "UNSTRUCTURED INPUT · MANY POSSIBLE PATHS", {
      b: 3,
      at: 1.9,
      anchor: "end",
      x: 4,
      overlap: true,
    });

    for (let i = 0; i < 7; i++) {
      k.line(760 + i * 160, 196, 760 + i * 160, 884, { b: 4, at: r(i * 0.05), dur: 0.6, hair: true });
    }
    for (let i = 0; i < 5; i++) {
      k.line(736, 220 + i * 160, 1744, 220 + i * 160, { b: 4, at: r(0.1 + i * 0.05), dur: 0.7, hair: true });
    }
    [
      [760, 220],
      [1240, 220],
      [1720, 380],
      [1400, 540],
      [920, 700],
      [1240, 860],
      [1080, 540],
      [1080, 380],
      [1560, 380],
      [1560, 700],
    ].forEach(([x, y], i) => k.sq(x, y, { b: 4, at: r(0.6 + i * 0.04) }));

    // The dot heads straight down the shortcut and the guard stops it.
    const stop = gx - 46;
    k.mk(stop, gy, { b: 4, at: 1.0, dur: 1.1, s: DOT, via: `1080,${gy}` });
    k.line(START, CY, 1080, CY, { b: 4, at: 1.0, dur: 0.92 });
    k.line(1088, gy, stop, gy, { b: 4, at: 1.8, dur: 0.3, dash: true });
    k.line(gx - 30, gy - 14, gx - 30, gy + 14, { b: 4, at: 2.0, dur: 0.1 });
    k.raw(
      `<path class="s bgf" d="M${gx} ${gy - 24}L${gx + 19} ${gy - 16}V${gy + 2}C${gx + 19} ${gy + 15} ${gx + 10} ${gy + 22} ${gx} ${gy + 27}C${gx - 10} ${gy + 22} ${gx - 19} ${gy + 15} ${gx - 19} ${gy + 2}V${gy - 16}Z" data-b="4" data-a="snap" data-at="1.95"/>`,
    );
    k.line(gx - 9, gy, gx + 9, gy, { b: 4, at: 2.1, dur: 0.1 });
    k.text(gx, gy - 56, "GUARD", { b: 4, at: 2.15, anchor: "middle" });
    k.text(1780, 952, "ONTOLOGY GUARD · WRONG PATH BLOCKED", {
      b: 4,
      at: 2.2,
      anchor: "end",
      x: 5,
      overlap: true,
    });

    // It backs up to the junction and takes the one permitted route.
    k.mk(1720, 700, {
      b: 5,
      at: 0.1,
      dur: 1.7,
      s: DOT,
      via: `1080,${gy};1080,380;1560,380;1560,700`,
    });
    k.path(`M1080 ${gy - 8}V380H1560V700H1707`, { b: 5, at: 0.42, dur: 1.38 });
    k.sq(1720, 700, { b: 5, at: 1.8, size: 26 });
    k.brk(1690, 670, 60, 60, { b: 5, at: 1.88, len: 14 });
    k.text(1780, 952, "DETERMINISTIC ONTOLOGY · ONE PERMITTED PATH", {
      b: 5,
      at: 2.1,
      anchor: "end",
      overlap: true,
    });
    return k.svg();
  },
  html() {
    return [
      `<h1 class="c-title" aria-label="Neurosymbolic engineering" data-x="2" data-xa="zoom" data-on="#s01-tittle">Neurosymbol<span class="tittle"><i id="s01-tittle"></i></span>ıc engineering</h1>`,
      `<p class="c-sub" data-x="2">ONTOLOGIES AND AGENTIC ENGINEERING</p>`,
    ].join("\n");
  },
};
