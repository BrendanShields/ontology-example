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
  id: "s03",
  holds: 5,
  eyebrow: "03 / INTERNAL FRICTION",
  title: ["Netflix's four-hour home screen regression"],
  body() {
    const k = kit();
    const W = 280;
    const H = 100;
    const HX = 1040;
    const HY = 570;
    // tool, the name it uses, card corner, and the point on the card its spoke reaches
    const tools = [
      ["Atlas", "home-api", 640, 360, 920, 460],
      ["Radar", "lolomo-svc", 1140, 340, 1140, 440],
      ["incident.io", "prod-web-04", 1480, 520, 1480, 570],
      ["PagerDuty", "homepage-prod", 1140, 700, 1140, 700],
      ["Spinnaker", "hs-render", 640, 680, 920, 680],
    ];

    // 1. A home screen that got slower.
    k.raw(`<rect class="s" x="120" y="400" width="360" height="250" rx="14" data-b="1" data-a="draw" data-at="0.2" data-dur="0.6" data-x="4"/>`);
    [0, 1, 2].forEach((i) => {
      k.rect(146 + i * 106, 430, 92, 84, { at: 0.5 + i * 0.25, dur: 0.5, dash: true, x: 4 });
      k.rect(146 + i * 106, 536, 92, 84, { at: 0.6 + i * 0.05, dur: 0.3, hair: true, x: 4 });
    });
    k.mk(192, 472, { b: 1 });
    k.text(120, 702, "+1.5 s to load", { at: 1.2, c: "cd", x: 4 });
    k.cap("THE HOME SCREEN GOT SLOWER", 1, { at: 1.4 });
    k.src("NETFLIX TECH BLOG, 16 OCT 2026", { at: 1.5 });

    // 2. Behind it is one service. Five tools each call it something else.
    k.line(480, 525, HX - 62, HY - 8, { b: 2, at: 0, dur: 0.5, dash: true, x: 4 });
    k.path(hex(HX, HY, 58), { b: 2, at: 0.4, dur: 0.6, x: 4 });
    k.mk(HX, HY, { b: 2, at: 0, dur: 0.9 });
    tools.forEach(([tool, name, x, y, sx, sy], i) => {
      const at = 0.8 + i * 0.25;
      k.line(HX + (sx - HX) * 0.2, HY + (sy - HY) * 0.24, sx, sy, { b: 2, at, dur: 0.25, x: 4 });
      k.rect(x, y, W, H, { b: 2, at: at + 0.1, dur: 0.4 });
      k.text(x + 22, y + 42, tool, { b: 2, at: at + 0.2, c: "m2" });
      k.text(x + 22, y + 82, name, { b: 2, at: at + 0.3, c: "cd" });
    });
    k.text(1760, 866, "NAMES ARE ILLUSTRATIVE", { b: 2, at: 2.2, c: "m2", anchor: "end" });
    k.cap("ONE SERVICE, FIVE NAMES FOR IT", 2, { at: 2.3 });

    // 3. Matching those names by hand is where the time went.
    const hop = tools.flatMap(([, , , , sx, sy]) => [`${sx},${sy}`, `${HX},${HY}`]);
    k.mk(tools[4][4], tools[4][5], { b: 3, at: 0, dur: 2.2, via: hop.slice(0, -2).join(";") });
    [0, 1, 2, 3].forEach((i) => {
      k.raw(
        `<rect class="${i < 2 ? "f" : "s"}" x="${120 + i * 92}" y="770" width="80" height="44" data-b="3" data-a="pop" data-at="${r(0.4 + i * 0.4)}" data-x="4"/>`,
      );
    });
    k.text(120, 860, "4 HOURS", { b: 3, at: 2.1, x: 4 });
    k.cap("AN HOUR OR TWO JUST MATCHING NAMES", 3, { at: 2.3 });

    // 4. An agent has none of that history, so it sees five different things.
    tools.forEach(([, , x, y], i) =>
      k.path(hex(x + W + 36, y + 50, 24), { b: 4, at: 0.9 + i * 0.12, dur: 0.3, x: 5 }),
    );
    const bot = k.bot(300, 580, 0.8, {
      b: 4,
      at: 0.4,
      moods: [
        { face: "confused", b: 4, at: 1.5 },
        { face: "happy", b: 5, at: 1.9 },
      ],
    });
    k.mk(bot.tip[0], bot.tip[1], { b: 4, at: 0, dur: 0.9 });
    k.text(300, 762, "AGENT", { b: 4, at: 0.8, anchor: "middle" });
    k.cap("AN AGENT SEES FIVE DIFFERENT THINGS", 4, { at: 1.7 });

    // 5. The fix: write the mapping down once, so every name points at one entry.
    k.path(hex(HX, HY, 58), { b: 5, at: 0.5, dur: 0.6 });
    k.mk(HX, HY, { b: 5, at: 0, dur: 1.0 });
    tools.forEach(([, , , , sx, sy], i) =>
      k.line(HX + (sx - HX) * 0.2, HY + (sy - HY) * 0.24, sx, sy, { b: 5, at: 1.0 + i * 0.12, dur: 0.25 }),
    );
    k.text(HX + 160, HY - 20, "ONE ENTRY", { b: 5, at: 1.6 });
    k.cap("ONE SHARED MAP · ONE QUERY, NOT THREE TOOLS", 5, { at: 2.0, keep: true });
    return k.svg();
  },
};
