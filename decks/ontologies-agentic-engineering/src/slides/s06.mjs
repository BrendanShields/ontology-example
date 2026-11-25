import { kit } from "../kit.mjs";

export default {
  id: "s06",
  holds: 4,
  eyebrow: "10 / HISTORY",
  title: ["Why symbolic AI stalled in the 1980s", "and why it works now"],
  body() {
    const k = kit();
    const era = (x, y, year, name, b, at) => {
      k.text(x, y, year, { b, at, c: "t1" });
      k.text(x, y + 44, name, { b, at: at + 0.1, c: "t2" });
    };

    // 1. Knowledge written down as rules.
    k.grid(260, 440, 96, { at: 0.2 });
    k.line(160, 600, 700, 600, { at: 0.3, dur: 0.9 });
    k.line(260, 586, 260, 614, { at: 0.6, dur: 0.15 });
    k.mk(260, 600, { b: 1 });
    era(260, 676, "1956", "Dartmouth", 1, 0.8);
    k.cap("KNOWLEDGE WRITTEN DOWN AS RULES", 1, { at: 1.2 });

    // 2. Hand-coding the whole world does not scale.
    k.line(700, 600, 700, 740, { b: 2, at: 0, dur: 0.5 });
    k.line(686, 740, 714, 740, { b: 2, at: 0.45, dur: 0.15 });
    k.mk(700, 740, { b: 2, at: 0.05 });
    k.text(672, 704, "1980s", { b: 2, at: 0.5, c: "t1", anchor: "end" });
    k.text(672, 748, "Expert systems", { b: 2, at: 0.6, c: "t2", anchor: "end" });
    k.cap("HAND-CODING THE WHOLE WORLD DID NOT SCALE", 2, { at: 0.9 });

    // 3. Neural nets scale, and they guess.
    k.path("M700 740C900 740 940 560 1100 560L1320 560", { b: 3, at: 0, dur: 1.1, dash: true });
    k.mk(1100, 560, { b: 3, at: 0, dur: 0.9 });
    k.bot(1100, 430, 0.42, { b: 3, at: 0.9, moods: [{ face: "confused", b: 3, at: 1.3 }] });
    era(1100, 640, "2012–2024", "Neural scale", 3, 1.1);
    k.cap("NEURAL NETS SCALE, AND THEY GUESS", 3, { at: 1.6 });

    // 4. A small set of rules around a big model.
    k.line(1320, 560, 1780, 560, { b: 4, at: 0, dur: 0.6, dash: true });
    k.line(1320, 620, 1780, 620, { b: 4, at: 0.1, dur: 0.6 });
    k.mk(1560, 590, { b: 4, at: 0, dur: 0.8 });
    k.brk(1516, 534, 88, 112, { b: 4, at: 0.9 });
    k.bot(1500, 430, 0.42, { b: 4, at: 1.0, moods: [{ face: "happy", b: 4, at: 1.4 }] });
    k.grid(1660, 430, 80, { b: 4, at: 1.1 });
    era(1420, 700, "2026", "Neurosymbolic", 4, 1.3);
    k.cap("A FEW HARD RULES AROUND A BIG MODEL", 4, { at: 1.8, keep: true });
    return k.svg();
  },
};
