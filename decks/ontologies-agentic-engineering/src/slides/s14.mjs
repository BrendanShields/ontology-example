import { kit } from "../kit.mjs";

// name, caption, code lines, and whether a guard blocks the first line
const stages = [
  ["GROUND", "LOAD THE DECISION THAT IS IN FORCE", ["get_active_decisions()", "ADR_004 · ADR_001 is superseded"]],
  ["SPEC", "EDIT THE SCHEMA, NOT GENERATED CODE", ["billing.py · PreToolUse DENY", "billing.yaml → SDK · shapes · docs"], true],
  ["CODE", "A STRAY COMMENT FAILS THE CHECK", ["inline comment · no-comments exit 2", "refunds.py, comment removed"], true],
  ["VERIFY", "FUZZ THE BOUNDARY, NOT ONE EXAMPLE", ["Hypothesis × 1,000 (PlanTier, amount)", "$1,000.00 passes · $1,000.01 fails"]],
  ["STAGE ADR", "THE DECISION IS STAGED, NOT MERGED", ["Stop hook → propose_decision", "ADR_005 supersedes ADR_004"]],
  ["REVIEW", "A PERSON REVIEWS EVIDENCE, NOT 400 LINES", []],
];

export default {
  id: "s14",
  holds: 6,
  eyebrow: "14 / WALKTHROUGH",
  title: ["One change, end to end"],
  body() {
    const k = kit();
    const y = 480;
    const xs = stages.map((_, i) => 200 + i * 288);
    const PX = 560;

    k.text(120, 346, "REQUEST", { at: 0, c: "m2" });
    k.text(270, 346, '"Allow ENTERPRISE auto-refunds up to $1,000, keeping PRO at $500."', { at: 0.1, c: "t2" });
    k.line(xs[0], y, xs[5], y, { at: 0.2, dur: 0.8, hair: true });
    stages.forEach(([name], i) => {
      k.sq(xs[i], y, { at: 0.5 + i * 0.07 });
      if (i === 0) return;
      k.text(xs[i], y - 40, `0${i + 1} ${name}`, {
        at: 0.55 + i * 0.07,
        c: "m2",
        anchor: "middle",
        x: i + 1,
        overlap: true,
      });
    });
    k.bot(300, 730, 0.62, {
      at: 0.9,
      moods: [
        { face: "blocked", b: 2, at: 0.6 },
        { face: "happy", b: 4, at: 0.6 },
      ],
    });

    stages.forEach(([name, caption, lines, guarded], i) => {
      const b = i + 1;
      const base = i === 0 ? 1.05 : 0;
      const x = i < 5 ? b + 1 : null;
      if (i > 0) k.line(xs[i - 1] + 8, y, xs[i] - 8, y, { b, at: 0, dur: 0.45 });
      k.mk(xs[i], y, { b, at: 0 });
      k.text(xs[i], y - 40, `0${b} ${name}`, { b, at: base + 0.2, c: "m2k", anchor: "middle", overlap: true });
      if (guarded) k.shield(PX - 44, 690, { b, at: base + 0.35, x });
      lines.forEach((line, j) => k.text(PX, 700 + j * 60, line, { b, at: base + 0.4 + j * 0.25, c: "cd", x }));
      k.cap(caption, b, { at: base + 0.9, keep: i === 5 });
    });

    // 6. The reviewer opens one file.
    k.rect(PX, 620, 560, 262, { b: 6, at: 0.3, dur: 0.7 });
    k.text(PX + 32, 676, "PR_EVIDENCE.md", { b: 6, at: 0.6, c: "cd" });
    k.line(PX + 32, 696, PX + 528, 696, { b: 6, at: 0.7, dur: 0.3, hair: true });
    ["statechart", "Hypothesis result", "SPARQL query", "staged ADR diff"].forEach((item, j) => {
      const ry = 738 + j * 40;
      k.path(`M${PX + 34} ${ry - 8}l6 6l10 -13`, { b: 6, at: 0.85 + j * 0.12, dur: 0.15 });
      k.text(PX + 70, ry, item, { b: 6, at: 0.9 + j * 0.12, c: "t2s" });
    });
    return k.svg();
  },
};
