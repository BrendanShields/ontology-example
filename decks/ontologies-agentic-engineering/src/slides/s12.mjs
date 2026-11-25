import { kit } from "../kit.mjs";

export default {
  id: "s12",
  holds: 4,
  eyebrow: "13 / RUNTIME LOOP",
  title: ["Two gates check every write before it happens"],
  body() {
    const k = kit();
    const y = 610;
    const from = 340;
    const stop = 1254;
    const gate = (x, b, at, tag, name) => {
      k.line(x, y - 90, x, y + 90, { b, at, dur: 0.3 });
      k.text(x, y - 150, tag, { b, at: at + 0.1, c: "m2", anchor: "middle" });
      k.text(x, y - 108, name, { b, at: at + 0.15, c: "t1s", anchor: "middle" });
    };

    // 1. The agent proposes. Types are checked and the result is computed with no side effects.
    k.bot(220, y, 0.55, {
      at: 0,
      moods: [
        { face: "blocked", b: 2, at: 0.9 },
        { face: "happy", b: 3, at: 1.7 },
      ],
    });
    k.text(220, y + 132, "AGENT", { at: 0.3, anchor: "middle" });
    k.mk(from, y, { b: 1 });
    k.line(from + 16, y, 540, y, { at: 0.5, dur: 0.3 });
    gate(560, 1, 0.75, "GATE 1", "Pydantic");
    k.line(580, y, 700, y, { at: 0.95, dur: 0.2 });
    k.brk(720, y - 80, 400, 160, { at: 1.1, len: 26 });
    k.text(920, y - 14, "dry_run()", { at: 1.2, c: "cd", anchor: "middle" });
    k.text(920, y + 46, "NO SIDE EFFECTS", { at: 1.3, c: "m2", anchor: "middle" });
    gate(1300, 1, 1.4, "GATE 2", "OWL / SHACL");
    k.cap("TYPES CHECKED · NOTHING WRITTEN YET", 1, { at: 1.6 });
    k.src("AFTER FRANK COYLE, 2026", { at: 1.7 });

    // 2. Gate 2 refuses the result and sends the reason back.
    k.mk(stop, y, { b: 2, at: 0, dur: 0.9, via: `1140,${y}` });
    k.line(1140, y, stop - 12, y, { b: 2, at: 0.45, dur: 0.4 });
    k.shield(1300, y, { b: 2, at: 0.85, x: 3, xat: 0.9 });
    k.path(`M${stop} ${y + 14}V${y + 200}H${from}V${y + 14}`, { b: 2, at: 1.2, dur: 1.2, dash: true });
    k.text(797, y + 248, "REJECTED, WITH THE REASON", { b: 2, at: 1.9, anchor: "middle" });
    k.cap("GATE 2 CATCHES A DOUBLE REFUND", 2, { at: 2.0 });

    // 3. The repaired proposal goes through and is staged.
    k.mk(1740, y, { b: 3, at: 0.1, dur: 1.6, via: `${stop},${y + 200};${from},${y + 200};${from},${y};${stop},${y}` });
    k.arrow(1320, y, 1760, y, { b: 3, at: 1.25, dur: 0.45 });
    k.text(1760, y - 28, "PASS · STAGED", { b: 3, at: 1.75, anchor: "end" });
    k.cap("THE REPAIRED PROPOSAL PASSES", 3, { at: 1.9 });

    // 4. A fast decision model watches the whole loop.
    k.line(120, 340, 1800, 340, { b: 4, at: 0, dur: 0.9, dash: true });
    k.text(120, 306, "DECISION MODEL", { b: 4, at: 0.4 });
    k.mk(560, 340, { b: 4, at: 0, dur: 1.0 });
    k.brk(534, 314, 52, 52, { b: 4, at: 1.0, len: 14 });
    k.text(604, 306, "RISK", { b: 4, at: 1.1, c: "m2" });
    k.brk(1274, 314, 52, 52, { b: 4, at: 1.15, len: 14 });
    k.acc(1300, 340, { b: 4, at: 1.25 });
    k.text(1344, 306, "DRIFT", { b: 4, at: 1.3, c: "m2" });
    k.cap("A FAST MODEL WATCHES RISK AND DRIFT", 4, { at: 1.5, keep: true });
    return k.svg();
  },
};
