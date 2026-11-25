import { kit } from "../kit.mjs";

export default {
  id: "s07",
  holds: 4,
  eyebrow: "07 / VOCABULARY",
  title: ["Four terms people conflate"],
  body() {
    const k = kit();
    const X = (i) => 120 + i * 430;
    const name = (i, label) => k.text(X(i), 760, label, { b: i + 1, at: 1.0, c: "t1s" });

    // 1. Taxonomy: kinds of things, as a tree.
    {
      const x = X(0);
      k.chip(x + 60, 430, 240, "Customer", { b: 1, at: 0.2 });
      k.line(x + 180, 458, x + 100, 572, { b: 1, at: 0.5, dur: 0.25 });
      k.line(x + 180, 458, x + 300, 572, { b: 1, at: 0.55, dur: 0.25 });
      k.chip(x, 600, 200, "Enterprise", { b: 1, at: 0.7 });
      k.chip(x + 230, 600, 140, "Pro", { b: 1, at: 0.8 });
      k.mk(x + 180, 458, { b: 1 });
      name(0, "Taxonomy");
      k.cap("A TREE OF KINDS", 1, { at: 1.2 });
    }
    // 2. Semantic model: two tables, one agreed number.
    {
      const x = X(1);
      [20, 200].forEach((dx, j) => {
        k.rect(x + dx, 400, 130, 120, { b: 2, at: 0.2 + j * 0.1, dur: 0.4 });
        [0, 1, 2].forEach((row) =>
          k.line(x + dx, 430 + row * 30, x + dx + 130, 430 + row * 30, { b: 2, at: 0.4 + row * 0.05, dur: 0.2, hair: true }),
        );
        k.line(x + dx + 65, 520, x + 175, 572, { b: 2, at: 0.6, dur: 0.25 });
      });
      k.chip(x + 40, 600, 270, "NetRevenue", { b: 2, at: 0.8 });
      k.mk(x + 40, 600, { b: 2, at: 0, dur: 0.9 });
      name(1, "Semantic model");
      k.cap("ONE NAME, ONE NUMBER", 2, { at: 1.2 });
    }
    // 3. Knowledge graph: particular things and the links between them.
    {
      const x = X(2);
      k.sq(x + 30, 440, { b: 3, at: 0.2, size: 40 });
      k.text(x + 64, 450, "ADR_004", { b: 3, at: 0.3, c: "cd" });
      k.arrow(x + 30, 464, x + 30, 580, { b: 3, at: 0.5, dur: 0.3 });
      k.text(x + 52, 530, "supersedes", { b: 3, at: 0.7, c: "m2" });
      k.sq(x + 30, 606, { b: 3, at: 0.8, size: 40 });
      k.text(x + 64, 616, "ADR_001", { b: 3, at: 0.9, c: "cd" });
      k.mk(x + 30, 520, { b: 3, at: 0, dur: 0.9 });
      name(2, "Knowledge graph");
      k.cap("THINGS AND THE LINKS BETWEEN THEM", 3, { at: 1.2 });
    }
    // 4. Ontology: the same links, plus rules about which ones are allowed.
    {
      const x = X(3);
      k.sq(x + 30, 440, { b: 4, at: 0.2, size: 40 });
      k.arrow(x + 56, 440, x + 230, 440, { b: 4, at: 0.4, dur: 0.3 });
      k.sq(x + 258, 440, { b: 4, at: 0.6, size: 40 });
      k.text(x + 144, 412, "ALLOWED", { b: 4, at: 0.7, c: "m2", anchor: "middle" });
      k.line(x + 30, 464, x + 30, 496, { b: 4, at: 0.8, dur: 0.15, dash: true });
      k.shield(x + 30, 528, { b: 4, at: 0.95 });
      k.text(x + 66, 538, "BLOCKED", { b: 4, at: 1.05, c: "m2" });
      k.sq(x + 30, 606, { b: 4, at: 0.9, size: 40, hair: true });
      k.mk(x + 30, 488, { b: 4, at: 0, dur: 0.9 });
      name(3, "Ontology");
      k.cap("THE LINKS, PLUS RULES A MACHINE CHECKS", 4, { at: 1.3, keep: true });
    }
    return k.svg();
  },
};
