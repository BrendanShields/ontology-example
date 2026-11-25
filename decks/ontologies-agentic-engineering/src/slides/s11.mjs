import { kit } from "../kit.mjs";

export default {
  id: "s11",
  holds: 3,
  eyebrow: "11 / PSTACK + ONTOLOGY",
  title: ["The inverted pyramid, and where the why lives"],
  body() {
    const k = kit();
    k.src("LAUREN TAN, AI ENGINEER 2026", { at: 1.4 });

    // 1. What one reviewer handles now: 3 a day became 300, 1 in 200 is reverted, comments are gone.
    [0, 1, 2].forEach((i) => k.rect(200, 628 - i * 14, 110, 10, { b: 1, at: 0.2 + i * 0.05, dur: 0.2, x: 2 }));
    k.text(255, 690, "3", { b: 1, at: 0.4, c: "t1", anchor: "middle", x: 2 });
    k.arrow(336, 560, 400, 560, { b: 1, at: 0.5, dur: 0.2, x: 2 });
    k.raw(
      `<g data-b="1" data-a="dots" data-at="0.6" data-dur="0.012" data-x="2">` +
        Array.from({ length: 30 }, (_, i) => `<rect class="s" x="430" y="${628 - i * 8}" width="110" height="5"/>`).join("") +
        `</g>`,
    );
    k.text(485, 690, "300", { b: 1, at: 1.0, c: "t1", anchor: "middle", x: 2 });
    k.text(200, 740, "REVIEWED A DAY", { b: 1, at: 1.1, c: "m2", x: 2 });

    k.raw(
      `<g data-b="1" data-a="dots" data-at="0.7" data-dur="0.002" data-x="2">` +
        Array.from({ length: 200 }, (_, i) => `<rect class="s hair" x="${760 + (i % 20) * 19}" y="${440 + Math.floor(i / 20) * 19}" width="12" height="12"/>`).join("") +
        `</g>`,
    );
    k.mk(760 + 13 * 19 + 6, 440 + 6 * 19 + 6, { b: 1 });
    k.text(760, 690, "1 in 200", { b: 1, at: 1.1, c: "t1", x: 2 });
    k.text(760, 740, "REVERTED", { b: 1, at: 1.2, c: "m2", x: 2 });

    k.rect(1340, 410, 220, 230, { b: 1, at: 1.0, dur: 0.5, x: 2 });
    [0, 1, 2, 3, 4, 5, 6].forEach((i) =>
      k.line(1364, 444 + i * 28, 1364 + [150, 110, 170, 90, 140, 120, 160][i], 444 + i * 28, {
        b: 1,
        at: 1.2 + i * 0.04,
        dur: 0.2,
        hair: i !== 1 && i !== 5,
        dash: i !== 1 && i !== 5,
        x: 2,
      }),
    );
    k.text(1340, 690, "98%", { b: 1, at: 1.5, c: "t1", x: 2 });
    k.text(1340, 740, "FEWER COMMENTS", { b: 1, at: 1.6, c: "m2", x: 2 });
    k.cap("ONE REVIEWER, A HUNDRED TIMES THE VOLUME", 1, { at: 1.7 });

    // 2. Where the trust comes from.
    const cx = 520;
    const top = 380;
    const bandH = 92;
    const widths = [800, 660, 520, 380, 240, 100];
    const labels = ["CODEBASE + API DESIGN", "STATIC ANALYSIS", "VERIFICATION", "PROSE + SKILLS", "REVIEW"];
    k.mk(cx - widths[0] / 2, top, { b: 2, at: 0, dur: 0.8 });
    labels.forEach((label, i) => {
      const y1 = top + i * bandH;
      const y2 = y1 + bandH;
      const a = widths[i] / 2;
      const c = widths[i + 1] / 2;
      const at = 0.3 + i * 0.24;
      if (i === 0) k.line(cx - a, y1, cx + a, y1, { b: 2, at, dur: 0.4 });
      k.path(`M${cx - a} ${y1}L${cx - c} ${y2}H${cx + c}L${cx + a} ${y1}`, { b: 2, at: at + 0.1, dur: 0.45 });
      k.text(cx, y1 + 58, label, { b: 2, at: at + 0.3, anchor: "middle" });
    });
    k.cap("TRUST STARTS AT THE WIDEST BAND", 2, { at: 1.9 });

    // 3. With no comments, the why needs a home.
    k.arrow(800, 564, 1170, 564, { b: 3, at: 0, dur: 0.7, dash: true });
    k.brk(1200, 444, 240, 240, { b: 3, at: 0.6, len: 30 });
    k.mk(1440, 444, { b: 3, at: 0, dur: 0.9 });
    k.path("M1226 546H1262L1274 562H1322V634H1226Z", { b: 3, at: 0.75, dur: 0.5 });
    k.rect(1344, 514, 76, 120, { b: 3, at: 0.9, dur: 0.5 });
    [544, 574, 604].forEach((y, i) => {
      k.path(`M1354 ${y}l5 5l8 -10`, { b: 3, at: 1.1 + i * 0.08, dur: 0.15 });
      k.line(1376, y, 1410, y, { b: 3, at: 1.15 + i * 0.08, dur: 0.15 });
    });
    k.text(1200, 756, "Git-versioned ontology", { b: 3, at: 1.3, c: "t1" });
    k.text(1200, 808, "RULES AND DECISIONS, REVIEWED", { b: 3, at: 1.45, c: "m2" });
    k.cap("WITH NO COMMENTS, THE WHY NEEDS A HOME", 3, { at: 1.7, keep: true });
    return k.svg();
  },
};
