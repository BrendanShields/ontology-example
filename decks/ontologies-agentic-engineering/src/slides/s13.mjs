import { kit } from "../kit.mjs";

export default {
  id: "s13",
  holds: 4,
  eyebrow: "13 / PROGRESSIVE CONTEXT",
  title: ["Progressive disclosure and", "the silent SPARQL failure"],
  body() {
    const k = kit();
    const bot = k.bot(300, 640, 0.75, {
      at: 0.1,
      moods: [
        { face: "confused", b: 1, at: 1.5 },
        { face: "happy", b: 2, at: 1.5 },
        { face: "confused", b: 3, at: 1.5 },
        { face: "happy", b: 4, at: 1.6 },
      ],
    });
    k.text(300, 810, "AGENT", { at: 0.4, anchor: "middle" });

    // 1. Twelve namespaces is too much to load.
    const cellAt = (i) => [700 + (i % 4) * 96, 520 + Math.floor(i / 4) * 96];
    const pick = 5;
    for (let i = 0; i < 12; i++) {
      const [x, y] = cellAt(i);
      k.sq(x, y, { b: 1, at: 0.5 + i * 0.04, size: 64, x: 3 });
    }
    k.mk(bot.tip[0], bot.tip[1], { b: 1 });
    k.text(668, 836, "12 NAMESPACES · 30 PACKAGES", { b: 1, at: 1.1, c: "m2", x: 3 });
    k.cap("TOO MUCH TO LOAD AT ONCE", 1, { at: 1.6 });

    // 2. A router picks the one slice the task needs.
    const [px, py] = cellAt(pick);
    k.mk(px, py, { b: 2, at: 0, dur: 0.9 });
    k.brk(px - 44, py - 44, 88, 88, { b: 2, at: 0.8, len: 18, x: 3 });
    k.text(px, py - 148, "billing", { b: 2, at: 0.9, c: "cd", anchor: "middle", x: 3 });
    k.arrow(px + 44, py, 1180, py, { b: 2, at: 1.0, dur: 0.4, x: 3 });
    ["packages/billing/CLAUDE.md", "/change-business-rule", "billing namespace"].forEach((item, i) =>
      k.text(1210, py - 42 + i * 52, item, { b: 2, at: 1.2 + i * 0.12, c: "cd", x: 3 }),
    );
    k.cap("A ROUTER LOADS ONLY WHAT THE TASK NEEDS", 2, { at: 1.7 });

    // 3. A guessed query fails quietly.
    k.chip(660, 560, 440, "guessed predicate", { b: 3, at: 0.5, x: 4 });
    k.arrow(1110, 560, 1230, 560, { b: 3, at: 0.9, dur: 0.3, dash: true, x: 4 });
    k.brk(1250, 470, 500, 180, { b: 3, at: 1.1, len: 26, x: 4 });
    k.mk(1280, 554, { b: 3, at: 0.3, dur: 1.0 });
    k.text(1316, 574, "0 rows", { b: 3, at: 1.25, c: "t0s", x: 4 });
    k.text(1316, 620, "NO ERROR", { b: 3, at: 1.35, c: "m2", x: 4 });
    k.cap("A GUESSED QUERY RETURNS NOTHING, QUIETLY", 3, { at: 1.7 });
    k.src("OPENMETADATA / COLLATE ONTOLOGY MCP", { b: 3, at: 1.8 });

    // 4. Describe first, then query.
    k.chip(660, 470, 440, "ontology_describe()", { b: 4, at: 0.2 });
    k.line(880, 498, 880, 532, { b: 4, at: 0.55, dur: 0.15 });
    k.chip(660, 560, 440, "real predicate", { b: 4, at: 0.6 });
    k.arrow(1110, 560, 1230, 560, { b: 4, at: 0.9, dur: 0.3 });
    k.rect(1250, 470, 500, 180, { b: 4, at: 1.1, dur: 0.6 });
    [0, 1, 2].forEach((i) => k.line(1290, 520 + i * 40, 1710 - i * 90, 520 + i * 40, { b: 4, at: 1.4 + i * 0.08, dur: 0.25 }));
    k.mk(1270, 520, { b: 4, at: 0, dur: 1.0 });
    k.cap("DESCRIBE FIRST, THEN QUERY · FIVE TOOLS", 4, { at: 1.7, keep: true });
    return k.svg();
  },
};
