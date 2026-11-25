import { kit } from "../kit.mjs";

export default {
  id: "s15",
  holds: 5,
  eyebrow: "15 / TRADE-OFFS + ROLLOUT",
  title: ["Where this goes wrong, and how to start"],
  body() {
    const k = kit();
    const X = (i) => 120 + i * 430;
    const cy = 430;
    const column = (i, name, line, cap) => {
      const b = i + 1;
      k.text(X(i), 560, name, { b, at: 0.7, c: "t1s" });
      k.text(X(i), 604, line, { b, at: 0.8, c: "m2" });
      k.cap(cap, b, { at: 1.2 });
    };

    // 1. Modeling everything first.
    for (let i = 0; i < 6; i++) {
      k.line(X(0) + i * 28, cy - 76, X(0) + i * 28, cy + 76, { b: 1, at: 0.2 + i * 0.04, dur: 0.3 });
      k.line(X(0) - 6, cy - 70 + i * 28, X(0) + 146, cy - 70 + i * 28, { b: 1, at: 0.25 + i * 0.04, dur: 0.3 });
    }
    k.mk(X(0) + 70, cy, { b: 1 });
    column(0, "Taxonomy committees", "MODEL IT ALL UP FRONT", "OVER-MODELING REPEATS THE 1980S");

    // 2. A graph nobody feeds.
    [
      [0, -40],
      [90, 30],
      [160, -50],
      [40, 60],
      [200, 50],
    ].forEach(([dx, dy], i) => k.sq(X(1) + 20 + dx, cy + dy, { b: 2, at: 0.3 + i * 0.07 }));
    k.line(X(1) + 30, cy - 36, X(1) + 100, cy + 24, { b: 2, at: 0.7, dur: 0.25 });
    k.mk(X(1) + 180, cy - 50, { b: 2, at: 0, dur: 0.8 });
    column(1, "Thin capture", "A GRAPH NOBODY FEEDS", "35 OF 38 MISSES: THE THINNEST GRAPH");
    k.src("MOOSEDEV, ARXIV:2608.13662", { b: 2, at: 1.3, x: 3 });

    // 3. An agent merging its own edits.
    k.bot(X(2) + 60, cy, 0.4, { b: 3, at: 0.2, moods: [{ face: "happy", b: 3, at: 0.6 }] });
    k.arrow(X(2) + 130, cy, X(2) + 250, cy, { b: 3, at: 0.7, dur: 0.3, dash: true });
    k.grid(X(2) + 310, cy, 84, { b: 3, at: 0.9 });
    k.mk(X(2) + 190, cy, { b: 3, at: 0, dur: 0.8 });
    column(2, "Auto-merged truth", "NO GUARD, NO REVIEW", "ONE UNREVIEWED EDIT REACHES EVERY AGENT");

    // 4. A graph where search would do.
    k.circ(X(3) + 60, cy - 10, 50, { b: 4, at: 0.3, dur: 0.5 });
    k.line(X(3) + 96, cy + 26, X(3) + 146, cy + 76, { b: 4, at: 0.6, dur: 0.25 });
    k.mk(X(3) + 60, cy - 10, { b: 4, at: 0, dur: 0.8 });
    column(3, "Wrong tool", "KEEP GREP FOR LOOKUP", "SEARCH STILL WINS SIMPLE LOOKUP");

    // 5. How to start.
    const y = 770;
    k.line(120, y, 1800, y, { b: 5, at: 0, dur: 0.9 });
    [
      [120, "WEEK 1", "10 to 20 classes, one domain"],
      [700, "MONTH 1", "Tools and evidence"],
      [1280, "QUARTER 1", "Actions and fast checks"],
    ].forEach(([x, when, what], i) => {
      const at = 0.5 + i * 0.3;
      k.line(x, y - 14, x, y + 14, { b: 5, at, dur: 0.15 });
      k.text(x, y - 34, when, { b: 5, at: at + 0.1 });
      k.text(x, y + 62, what, { b: 5, at: at + 0.2, c: "t1s" });
    });
    k.mk(120, y, { b: 5, at: 0, dur: 0.9 });
    k.cap("START SMALL, IN ONE DOMAIN THAT HURTS", 5, { at: 1.6, keep: true });
    return k.svg();
  },
};
