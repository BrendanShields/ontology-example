import { kit } from "../kit.mjs";

export default {
  id: "s08",
  holds: 4,
  eyebrow: "07 / INFERENCE",
  title: ["Deriving what was never written down"],
  body() {
    const k = kit();
    const y = 580;
    const node = (x, name, b, at) => {
      k.circ(x, y, 62, { b, at, dur: 0.5 });
      k.text(x, y + 12, name, { b, at: at + 0.25, c: "t1s", anchor: "middle" });
    };
    const edge = (x1, x2, b, at) => {
      k.arrow(x1, y, x2, y, { b, at, dur: 0.6 });
      k.text((x1 + x2) / 2, y - 26, "father of", { b, at: at + 0.3, c: "cd", anchor: "middle" });
    };

    // 1 and 2. Two facts someone stored.
    node(460, "Sam", 1, 0);
    edge(522, 898, 1, 0.3);
    node(960, "Tom", 1, 0.7);
    k.mk(710, y, { b: 1 });
    k.cap("ONE STORED FACT", 1, { at: 1.2 });

    edge(1022, 1398, 2, 0);
    node(1460, "Leo", 2, 0.4);
    k.mk(1210, y, { b: 2, at: 0, dur: 0.8 });
    k.cap("A SECOND STORED FACT", 2, { at: 1.0 });

    // 3. The fact nobody stored.
    k.path("M460 518C460 250 1460 250 1460 518", { b: 3, at: 0, dur: 1.0, dash: true });
    k.mk(960, 317, { b: 3, at: 0, dur: 0.9 });
    k.brk(934, 291, 52, 52, { b: 3, at: 1.05, len: 14 });
    k.text(1006, 296, "INFERRED", { b: 3, at: 1.15 });
    k.text(1166, 296, "grandfather of", { b: 3, at: 1.25, c: "cd" });
    k.cap("NOBODY STORED THIS ONE. IT IS DERIVED.", 3, { at: 1.6 });

    // 4. The same rules on engineering records.
    k.line(120, 760, 1800, 760, { b: 4, at: 0, dur: 0.8, hair: true });
    k.mk(132, 846, { b: 4, at: 0, dur: 0.9 });
    k.text(160, 812, "SUPERSEDES, CHAINED", { b: 4, at: 0.5, c: "m2" });
    k.text(160, 858, "ADR_005 → ADR_004 → ADR_001", { b: 4, at: 0.6, c: "cd" });
    k.text(720, 812, "NEVER BOTH", { b: 4, at: 0.8, c: "m2" });
    k.text(720, 858, "Customer ≠ SupportRep", { b: 4, at: 0.9, c: "cd" });
    k.text(1190, 812, "CLOSED SET", { b: 4, at: 1.1, c: "m2" });
    k.text(1190, 858, "paid | shipped | refunded", { b: 4, at: 1.2, c: "cd" });
    k.cap("THE SAME RULES, ON ENGINEERING RECORDS", 4, { at: 1.5, keep: true });
    return k.svg();
  },
};
