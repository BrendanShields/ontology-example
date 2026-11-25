import { kit } from "../kit.mjs";

export default {
  id: "s09",
  holds: 5,
  eyebrow: "09 / STANDARDS",
  title: ["Open world, closed world"],
  body() {
    const k = kit();
    // The strip names each standard as its scene starts, as on slide 2.
    [
      [126, "RDF", 1, 2, 70],
      [286, "SPARQL", 2, 3, 122],
      [498, "OWL", 3, 4, 72],
      [660, "SHACL", 4, 5, 104],
    ].forEach(([x, name, b, x2, w]) => {
      k.sq(x, 279, { b, at: 0.05, solid: true, size: 12 });
      k.text(x + 22, 290, name, { b, at: 0.1, c: "t1s" });
      k.brk(x - 22, 250, w + 60, 58, { b, at: 0.2, len: 14, x: x2 });
    });

    // 1. RDF: every fact is three parts.
    const y = 600;
    [
      [300, 300, "ADR_005", "SUBJECT"],
      [760, 400, "supersedes", "PREDICATE"],
      [1320, 300, "ADR_004", "OBJECT"],
    ].forEach(([x, w, label, role], i) => {
      k.chip(x, y, w, label, { b: 1, at: 0.4 + i * 0.3, x: 2 });
      k.text(x + w / 2, y + 84, role, { b: 1, at: 0.6 + i * 0.3, c: "m2", anchor: "middle", x: 2 });
    });
    k.line(600, y, 760, y, { b: 1, at: 0.6, dur: 0.25, x: 2 });
    k.arrow(1160, y, 1320, y, { b: 1, at: 0.9, dur: 0.25, x: 2 });
    k.mk(300, y, { b: 1 });
    k.cap("EVERY FACT IS THREE PARTS", 1, { at: 1.4 });

    // 2. SPARQL: one query follows the links.
    const xs = [520, 960, 1400];
    ["ADR_005", "ADR_004", "ADR_001"].forEach((id, i) => {
      k.sq(xs[i], y, { b: 2, at: 0.5 + i * 0.2, size: 44, x: 4 });
      k.text(xs[i], y + 76, id, { b: 2, at: 0.6 + i * 0.2, c: "cd", anchor: "middle", x: 4 });
      if (i) k.arrow(xs[i - 1] + 30, y, xs[i] - 30, y, { b: 2, at: 0.7 + i * 0.2, dur: 0.3, x: 4 });
    });
    k.text(740, y - 24, "supersedes", { b: 2, at: 1.0, c: "m2", anchor: "middle", x: 4 });
    k.text(1180, y - 24, "supersedes", { b: 2, at: 1.2, c: "m2", anchor: "middle", x: 4 });
    k.chip(700, 430, 520, '"what replaced ADR_001?"', { b: 2, at: 0.3, x: 3 });
    k.mk(xs[0], y, { b: 2, at: 0.9, dur: 1.2, via: `${xs[2]},${y};${xs[1]},${y}` });
    k.cap("ONE QUERY FOLLOWS THE LINKS", 2, { at: 1.9 });

    // 3. OWL: infer what nobody wrote down.
    k.path(`M${xs[0]} ${y - 30}C${xs[0]} 400 ${xs[2]} 400 ${xs[2]} ${y - 30}`, { b: 3, at: 0.1, dur: 0.9, dash: true, x: 4 });
    k.mk(960, 450, { b: 3, at: 0, dur: 0.8 });
    k.brk(934, 424, 52, 52, { b: 3, at: 1.0, len: 14, x: 4 });
    k.text(1006, 428, "INFERRED", { b: 3, at: 1.1, x: 4 });
    k.text(960, 800, "UNSTATED MEANS UNKNOWN", { b: 3, at: 1.3, c: "m2", anchor: "middle", x: 4 });
    k.cap("OWL INFERS WHAT NOBODY WROTE DOWN", 3, { at: 1.6 });

    // 4. SHACL: a record with a gap is refused.
    k.rect(620, 420, 520, 360, { b: 4, at: 0.3, dur: 0.7, x: 5 });
    k.text(652, 480, "DECISION", { b: 4, at: 0.6, c: "m2", x: 5 });
    k.text(652, 540, "ADR_006", { b: 4, at: 0.7, c: "t1", x: 5 });
    [
      [630, "rationale"],
      [710, "date"],
    ].forEach(([ry, field], i) => {
      k.text(652, ry, field, { b: 4, at: 0.85 + i * 0.1, c: "cd", x: 5 });
      k.line(860, ry + 6, 1100, ry + 6, { b: 4, at: 0.9 + i * 0.1, dur: 0.3, dash: true, x: 5 });
    });
    k.mk(1100, 636, { b: 4, at: 0, dur: 1.0 });
    k.shield(1230, 600, { b: 4, at: 1.4, x: 5 });
    k.text(1280, 592, "MISSING MEANS", { b: 4, at: 1.5, c: "m2", x: 5 });
    k.text(1280, 632, "VIOLATION", { b: 4, at: 1.55, c: "m2", x: 5 });
    k.cap("SHACL REFUSES A RECORD WITH GAPS", 4, { at: 1.7 });

    // 5. What Netflix did with the four of them.
    [
      [300, "12", "NAMESPACES"],
      [760, "~49,000", "CATALOG ENTRIES"],
    ].forEach(([x, big, small], i) => {
      k.text(x, 680, big, { b: 5, at: 0.8 + i * 0.25, c: "t0" });
      k.text(x, 734, small, { b: 5, at: 0.9 + i * 0.25, c: "m2" });
    });
    k.chip(300, 440, 240, "Service", { b: 5, at: 0.2, dash: true });
    k.shield(590, 440, { b: 5, at: 0.6 });
    k.mk(564, 440, { b: 5, at: 0.1, dur: 0.8 });
    k.cap('THE NETFLIX MAP: NO GENERIC "SERVICE" TYPE', 5, { at: 1.4, keep: true });
    k.src("NETFLIX TECH BLOG, 16 OCT 2026", { b: 5, at: 1.5 });
    return k.svg();
  },
};
