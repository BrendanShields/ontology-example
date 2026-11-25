import { kit } from "../kit.mjs";

export default {
  id: "s10",
  holds: 4,
  eyebrow: "09 / ACTIONS",
  title: ["Nouns are not enough"],
  body() {
    const k = kit();
    const W = 500;
    const H = 132;
    const X = 120;
    const tops = [340, 506, 672];
    const node = (i, b, name, tag, code) => {
      const y = tops[i];
      k.brk(X, y, W, H, { b, at: 0.1, len: 24 });
      k.mk(X + W, y, { b, at: 0, dur: 0.7 });
      k.text(X + 28, y + 56, name, { b, at: 0.25, c: "t1" });
      k.text(X + W - 28, y + 54, tag, { b, at: 0.35, c: "m2", anchor: "end" });
      k.text(X + 28, y + 104, code, { b, at: 0.45, c: "cd" });
    };

    const bot = k.bot(1560, 730, 0.6, {
      at: 0.6,
      moods: [
        { face: "confused", b: 1, at: 1.1 },
        { face: "happy", b: 4, at: 2.0 },
      ],
    });
    node(0, 1, "Data", "NOUNS", "Customer · RefundRequest");
    k.cap("NOUNS ALONE GIVE AN AGENT NOTHING TO DO", 1, { at: 1.2 });

    node(1, 2, "Logic", "RULES", "evaluate_refund()");
    k.path(`M${X + 330} ${tops[1] + 94}l8 9l16 -20`, { b: 2, at: 0.8, dur: 0.2 });
    k.cap("RULES RUN AS CODE, NEVER AS A GUESS", 2, { at: 0.9 });

    node(2, 3, "Actions", "VERBS", "issue_refund");
    k.shield(X + 46, tops[2] + H + 52, { b: 3, at: 0.7 });
    k.text(X + 86, tops[2] + H + 62, "IRREVERSIBLE", { b: 3, at: 0.85, c: "m2" });
    k.cap("EACH ACTION SAYS IF IT CAN BE UNDONE", 3, { at: 1.0 });

    // 4. All three compile into one typed interface, and every caller uses it.
    const jx = 760;
    const jy = 572;
    tops.forEach((y, i) => k.path(`M${X + W} ${y + H / 2}H${jx}V${jy}`, { b: 4, at: i * 0.08, dur: 0.5, x: null }));
    k.mk(jx, jy, { b: 4, at: 0, dur: 0.6 });
    k.arrow(jx + 12, jy, 880, jy, { b: 4, at: 0.6, dur: 0.25 });
    k.rect(880, jy - 90, 360, 180, { b: 4, at: 0.8, dur: 0.6 });
    k.text(1060, jy + 14, "Typed SDK", { b: 4, at: 1.1, c: "t1", anchor: "middle" });
    [
      [jy - 170, "API"],
      [jy - 60, "WORKER"],
    ].forEach(([y, label], i) => {
      k.path(`M1240 ${jy}H1300V${y}H1380`, { b: 4, at: 1.3 + i * 0.1, dur: 0.3 });
      k.chip(1380, y, 220, label, { b: 4, at: 1.5 + i * 0.1, c: "m1" });
    });
    k.path(`M1240 ${jy}H1300V730H${bot.right - 154 - 20}`, { b: 4, at: 1.5, dur: 0.3 });
    k.cap("ONE TYPED INTERFACE FOR EVERY CALLER", 4, { at: 2.0, keep: true });
    k.src("IDEA: PALANTIR ONTOLOGY", { b: 4, at: 2.1 });
    return k.svg();
  },
};
