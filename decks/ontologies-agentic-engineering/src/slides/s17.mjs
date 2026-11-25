import { kit } from "../kit.mjs";

const r = (n) => Math.round(n * 100) / 100;
const hex = (cx, cy, R) =>
  [0, 1, 2, 3, 4, 5]
    .map((i) => {
      const a = Math.PI / 6 + (i * Math.PI) / 3;
      return `${i ? "L" : "M"}${r(cx + R * Math.cos(a))} ${r(cy + R * Math.sin(a))}`;
    })
    .join("") + "Z";

// A plain line figure for this slide. Slide 2 draws people in more detail; once that
// drawing is shared this stand-in can be swapped for it.
function figure(k, cx, cy, o) {
  const face = `figure-${cx}`;
  k.raw(`<g data-b="${o.b}" data-a="snap" data-at="${o.at}" data-dur="0.35">`);
  k.raw(
    `<path class="s" d="M${cx - 92} ${cy + 156}V${cy + 128}C${cx - 92} ${cy + 94} ${cx - 54} ${cy + 76} ${cx} ${cy + 76}C${cx + 54} ${cy + 76} ${cx + 92} ${cy + 94} ${cx + 92} ${cy + 128}V${cy + 156}"/>`,
  );
  k.raw(`<circle class="s bgf" cx="${cx}" cy="${cy}" r="58"/>`);
  [-20, 20].forEach((ex) => {
    k.raw(`<g data-idle="wink" data-face="${face}" data-origin="${cx + ex} ${cy - 6}">`);
    k.raw(
      `<circle class="f" cx="${cx + ex}" cy="${cy - 6}" r="5" data-idle="look" data-face="${face}" data-amp="4"/>`,
    );
    k.raw(`</g>`);
  });
  k.raw(`</g>`);
}

export default {
  id: "s17",
  holds: 3,
  eyebrow: "04 / PEOPLE",
  title: ["A shared model is less to hold in your head"],
  body() {
    const k = kit();
    const names = ["home-api", "lolomo-svc", "prod-web-04", "homepage-prod"];
    const slot = (i) => 580 + i * 292;
    const SY = 440;

    // 1. Working memory has about four slots, and the names fill all of them.
    figure(k, 300, 650, { b: 1, at: 0.1 });
    k.path(`M276 674H324`, { b: 1, at: 0.5, dur: 0.15, x: 2 });
    [
      [392, 566, 6],
      [432, 524, 10],
      [482, 478, 14],
    ].forEach(([x, y, rad], i) => k.circ(x, y, rad, { b: 1, at: 0.4 + i * 0.08, dur: 0.15, x: 3 }));
    k.raw(
      `<rect class="s" x="530" y="350" width="1250" height="250" rx="40" data-b="1" data-a="draw" data-at="0.6" data-dur="0.7" data-x="3"/>`,
    );
    [0, 1, 2, 3].forEach((i) => {
      k.rect(slot(i), SY, 268, 104, { b: 1, at: 0.9 + i * 0.07, dur: 0.3, dash: true, x: 3 });
      k.text(slot(i) + 134, SY + 64, names[i], { b: 1, at: 1.0 + i * 0.12, c: "cd", anchor: "middle", x: 2 });
    });
    k.chip(1490, 700, 268, "hs-render", { b: 1, at: 1.5, dash: true, x: 2 });
    k.mk(1490, 700, { b: 1 });
    k.chip(580, 700, 360, "the actual problem", { b: 1, at: 1.6, dash: true, hair: true, c: "m2", x: 2 });
    k.cap("FOUR SLOTS, ALL SPENT ON NAMES", 1, { at: 1.8 });
    k.src("COWAN, 2001: ABOUT FOUR CHUNKS", { at: 1.9, x: 3 });

    // 2. One entry takes one slot. The rest go to the problem.
    k.path(hex(slot(0) + 52, SY + 52, 28), { b: 2, at: 0.3, dur: 0.4, x: 3 });
    k.text(slot(0) + 96, SY + 64, "one entry", { b: 2, at: 0.5, c: "cd", x: 3 });
    k.mk(slot(0) + 52, SY + 52, { b: 2, at: 0, dur: 0.9 });
    ["what changed", "the cause", "the fix"].forEach((thought, i) =>
      k.text(slot(i + 1) + 134, SY + 64, thought, { b: 2, at: 0.8 + i * 0.2, c: "t2s", anchor: "middle", x: 3 }),
    );
    k.path(`M276 668Q300 692 324 668`, { b: 2, at: 1.4, dur: 0.2 });
    k.cap("ONE NAME FREES THE REST FOR THE PROBLEM", 2, { at: 1.6 });

    // 3. The same picture in every head, and in the agent.
    const heads = [300, 900, 1500];
    k.path(hex(900, 360, 46), { b: 3, at: 0.2, dur: 0.5 });
    k.text(966, 370, "SHARED MAP", { b: 3, at: 0.5 });
    k.mk(900, 360, { b: 3, at: 0, dur: 0.9 });
    figure(k, 900, 650, { b: 3, at: 0.5 });
    k.path(`M876 668Q900 692 924 668`, { b: 3, at: 0.9, dur: 0.2 });
    k.bot(1500, 668, 0.7, { b: 3, at: 0.7, moods: [{ face: "happy", b: 3, at: 1.3 }] });
    heads.forEach((x, i) => {
      k.line(900 + (x - 900) * 0.12, 406, x, 486, { b: 3, at: 1.0 + i * 0.12, dur: 0.3 });
      k.path(hex(x, 516, 24), { b: 3, at: 1.25 + i * 0.12, dur: 0.25 });
    });
    k.cap("ONE PICTURE, SHARED BY PEOPLE AND AGENT", 3, { at: 1.9, keep: true });
    return k.svg();
  },
};
