import { kit } from "../kit.mjs";

export default {
  id: "s05",
  holds: 4,
  eyebrow: "04 / EVIDENCE",
  title: ["Where prompt dumps and vector search stop working"],
  body() {
    const k = kit();
    const X = 700;
    const lead = (b, text, x) => k.text(X, 392, text, { b, at: 0.5, c: "t1s", x });

    const bot = k.bot(330, 620, 0.8, {
      at: 0.1,
      moods: [
        { face: "confused", b: 1, at: 1.5 },
        { face: "happy", b: 2, at: 1.3 },
      ],
    });
    k.text(330, 800, "AGENT", { at: 0.4, anchor: "middle" });

    // 1. Everything pasted into the prompt.
    lead(1, "Paste the whole ontology into the prompt", 2);
    for (let i = 4; i >= 0; i--) {
      k.rect(X + i * 16, 470 + i * 14, 190, 240, { b: 1, at: 0.6 + (4 - i) * 0.08, dur: 0.4, x: 2 });
    }
    k.arrow(X - 20, 620, bot.right + 30, 620, { b: 1, at: 1.1, dur: 0.35, dash: true, x: 2 });
    k.mk(1040, 610, { b: 1 });
    k.text(1070, 636, "−15.0 pts", { b: 1, at: 1.3, c: "t0", x: 2 });
    k.text(1070, 690, "CLAUDE SONNET 5 · DDR-BENCH", { b: 1, at: 1.45, c: "m2", x: 2 });
    k.cap("FIVE OF SIX MODELS GOT WORSE", 1, { at: 1.6 });
    k.src("EVOONTOLOGY, ARXIV:2609.15779", { at: 1.7, x: 3 });

    // 2. The same ontology, fetched on demand.
    lead(2, "Let it look things up with tools", 3);
    [0, 1, 2, 3, 4].forEach((i) => k.sq(X + 30 + i * 62, 620, { b: 2, at: 0.6 + i * 0.07, size: 40, x: 3 }));
    k.line(X - 20, 620, bot.right + 30, 620, { b: 2, at: 0.9, dur: 0.35, dash: true, x: 3 });
    k.mk(1040, 610, { b: 2, at: 0 });
    k.text(1070, 636, "90.9–93.5%", { b: 2, at: 1.1, c: "t0", x: 3, overlap: true });
    k.text(1070, 690, "GPT-5.5 · GPT-5.6-SOL · OPUS 4.8", { b: 2, at: 1.25, c: "m2", x: 3, overlap: true });
    k.text(1070, 732, "CLAUDE SONNET 5 REACHED 81.3%", { b: 2, at: 1.35, c: "m2", x: 3 });
    k.cap("THE SAME ONTOLOGY, FETCHED ON DEMAND", 2, { at: 1.5 });

    // 3. A question about structure.
    lead(3, '"Which decision replaced ADR_001?"', 4);
    k.text(X, 500, "Vector store", { b: 3, at: 0.7, c: "t2", x: 4 });
    k.rect(X, 522, 130, 36, { b: 3, at: 0.8, dur: 0.4, dash: true, x: 4 });
    k.text(X + 154, 552, "6–27%", { b: 3, at: 0.95, c: "t1", x: 4 });
    k.text(X, 660, "Typed graph with rules", { b: 3, at: 1.1, c: "t2", x: 4 });
    k.rect(X, 682, 475, 36, { b: 3, at: 1.2, dur: 0.6, x: 4 });
    k.mk(X + 475, 700, { b: 3, at: 0.4, dur: 1.2 });
    k.text(X + 501, 712, "98–100%", { b: 3, at: 1.6, c: "t1", x: 4 });
    k.cap("A TYPED GRAPH ANSWERS WHAT REPLACED WHAT", 3, { at: 1.7 });
    k.src("MOOSEDEV, ARXIV:2608.13662", { b: 3, at: 1.8, x: 4 });

    // 4. The honest boundary.
    lead(4, "Simple lookup? Plain search still wins");
    k.circ(X + 70, 600, 60, { b: 4, at: 0.6, dur: 0.5 });
    k.line(X + 113, 643, X + 170, 700, { b: 4, at: 0.9, dur: 0.25 });
    k.mk(X + 70, 600, { b: 4, at: 0.2, dur: 0.9 });
    k.text(1070, 636, "83.2%", { b: 4, at: 1.1, c: "t0", overlap: true });
    k.text(1070, 690, "EVIDENCE RECALL · RAG WITH RERANKING", { b: 4, at: 1.25, c: "m2", overlap: true });
    k.cap("KEEP GREP AND VECTOR SEARCH WHERE THEY FIT", 4, { at: 1.5, keep: true });
    k.src("GRAPHRAG-BENCH, ARXIV:2506.05690", { b: 4, at: 1.6 });
    return k.svg();
  },
};
