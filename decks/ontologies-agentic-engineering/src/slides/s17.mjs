import { kit } from "../kit.mjs";

const r = (n) => Math.round(n * 100) / 100;
const hex = (cx, cy, R) =>
  [0, 1, 2, 3, 4, 5]
    .map((i) => {
      const a = Math.PI / 6 + (i * Math.PI) / 3;
      return `${i ? "L" : "M"}${r(cx + R * Math.cos(a))} ${r(cy + R * Math.sin(a))}`;
    })
    .join("") + "Z";

export default {
  id: "s17",
  holds: 3,
  eyebrow: "03 / PEOPLE",
  title: ["A shared model is less to hold in your head"],
  body() {
    const k = kit();
    const names = ["home-api", "lolomo-svc", "prod-web-04", "homepage-prod"];
    const slot = (i) => 580 + i * 292;
    const SY = 440;

    // 1. Working memory has about four slots, and the names fill all of them.
    k.person(300, 655, 1.15, "short", {
      b: 1,
      at: 0.1,
      top: "tie",
      faces: [
        { face: { brows: "worried", mouth: "flat" } },
        { b: 2, at: 1.4, face: { brows: "level", mouth: "smile" } },
        { b: 3, at: 1.4, face: { brows: "raised", mouth: "broad" } },
      ],
      gaze: [
        { b: 1, to: [900, 480] },
        { b: 3, to: [900, 360], t: 0.3 },
      ],
    });
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
    k.cap("ONE NAME FREES THE REST FOR THE PROBLEM", 2, { at: 1.6 });

    // 3. The same picture in every head, and in the agent.
    const heads = [300, 900, 1500];
    k.path(hex(900, 360, 46), { b: 3, at: 0.2, dur: 0.5 });
    k.text(966, 370, "SHARED MAP", { b: 3, at: 0.5 });
    k.mk(900, 360, { b: 3, at: 0, dur: 0.9 });
    k.person(900, 655, 1.15, "long", {
      b: 3,
      at: 0.5,
      top: "lapels",
      faces: [{ face: { brows: "raised", mouth: "smile" } }],
      gaze: [{ b: 3, to: [900, 360] }],
    });
    k.bot(1500, 668, 0.7, { b: 3, at: 0.7, moods: [{ face: "happy", b: 3, at: 1.3 }] });
    heads.forEach((x, i) => {
      k.line(900 + (x - 900) * 0.12, 406, x, 486, { b: 3, at: 1.0 + i * 0.12, dur: 0.3 });
      k.path(hex(x, 516, 24), { b: 3, at: 1.25 + i * 0.12, dur: 0.25 });
    });
    k.cap("ONE PICTURE, SHARED BY PEOPLE AND AGENT", 3, { at: 1.9, keep: true });
    return k.svg();
  },
};
