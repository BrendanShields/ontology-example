import { kit } from "../kit.mjs";

export default {
  id: "s04",
  holds: 4,
  eyebrow: "04 / THREE LAYERS",
  title: ["Three layers for three kinds of work"],
  body() {
    const k = kit();
    const col = { rules: 400, quick: 960, model: 1520 };
    const rows = [716, 786, 856];
    const asks = ["route this task?", "is this risky?", "refund within limit?"];
    const W = 400;
    const ask = (x, row, label, o) => k.chip(x - W / 2, rows[row], W, label, o);

    // 1. One model answers everything.
    const bot = k.bot(col.model, 440, 0.62, {
      at: 0.1,
      moods: [
        { face: "confused", b: 1, at: 1.5 },
        { face: "happy", b: 4, at: 0.9 },
      ],
    });
    k.mk(bot.tip[0], bot.tip[1], { b: 1 });
    k.text(col.model, 616, "Generative LLM", { at: 0.5, c: "t1", anchor: "middle" });
    asks.forEach((label, i) => ask(col.model, i, label, { b: 1, at: 0.8 + i * 0.2, x: i < 2 ? 2 : 3 }));
    k.cap("ONE MODEL ANSWERS EVERY QUESTION", 1, { at: 1.6 });

    // 2. Quick calls move to a decision model.
    k.line(1240, 340, 1240, 890, { b: 2, at: 0, dur: 0.6, hair: true });
    const tip = k.gauge(col.quick, 500, 96, { b: 2, at: 0.2 });
    k.mk(tip[0], tip[1], { b: 2, at: 0, dur: 0.9 });
    k.text(col.quick, 616, "Decision model", { b: 2, at: 0.9, c: "t1", anchor: "middle" });
    [0, 1].forEach((i) => ask(col.quick, i, asks[i], { b: 2, at: 1.1 + i * 0.2 }));
    k.text(col.quick, rows[2] + 10, "UP TO ~400× CHEAPER", { b: 2, at: 1.6, c: "m2", anchor: "middle" });
    k.cap("QUICK CALLS GO TO A FAST, TYPED MODEL", 2, { at: 1.7 });
    k.src("VENDOR FIGURE (TYPESAFE)", { b: 2, at: 1.8, x: 3 });

    // 3. Hard limits move to rules.
    k.line(680, 340, 680, 890, { b: 3, at: 0, dur: 0.6, hair: true });
    const cell = k.grid(col.rules, 460, 170, { b: 3, at: 0.2 });
    const [mx, my] = cell(2, 0);
    k.mk(mx, my, { b: 3, at: 0, dur: 0.9 });
    k.text(col.rules, 616, "Symbolic rules", { b: 3, at: 0.9, c: "t1", anchor: "middle" });
    ask(col.rules, 0, asks[2], { b: 3, at: 1.1 });
    k.text(col.rules, rows[1] + 10, "EXACT, EVERY TIME", { b: 3, at: 1.5, c: "m2", anchor: "middle" });
    k.cap("HARD LIMITS GO TO RULES THAT CANNOT GUESS", 3, { at: 1.6 });

    // 4. The model keeps the open-ended work.
    k.mk(bot.tip[0], bot.tip[1], { b: 4, at: 0, dur: 1.0 });
    ask(col.model, 0, "write the change", { b: 4, at: 0.6 });
    k.text(col.model, rows[1] + 10, "OPEN-ENDED WORK ONLY", { b: 4, at: 1.1, c: "m2", anchor: "middle" });
    k.cap("CHEAP BY DEFAULT, FRONTIER ON EXCEPTION", 4, { at: 1.4, keep: true });
    k.src("PHRASE: JAYA GUPTA, VIA LANGCHAIN", { b: 4, at: 1.5 });
    return k.svg();
  },
};
