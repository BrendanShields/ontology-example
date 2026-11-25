import { kit } from "../kit.mjs";

const tops = [360, 520, 680];
const takes = [
  "<strong>One shared model</strong> for people and agents, kept in Git with its rules.",
  "<strong>Two gates and a fast model</strong> put checks around a model that guesses.",
  "<strong>Progressive disclosure</strong> keeps context small and reviews checkable.",
];

export default {
  id: "s16",
  holds: 3,
  eyebrow: "17 / DISCUSSION",
  title: ["Recap and discussion"],
  css: `      .take {
        position: absolute;
        left: 170px;
        width: 900px;
        font-size: 44px;
        line-height: 1.25;
        letter-spacing: -0.012em;
        text-wrap: balance;
      }
      .take strong {
        font-weight: 600;
      }`,
  body() {
    const k = kit();
    const bot = k.bot(1480, 600, 0.95, { at: 0.2, moods: [{ face: "happy", b: 3, at: 1.2 }] });
    tops.forEach((top, i) => {
      if (i < 2) k.mk(125, top + 28, { b: i + 1, at: 0 });
      k.circ(125, top + 28, 6, { b: i + 2 > 3 ? 3 : i + 2, at: i === 2 ? 0.2 : 0.5, dur: 0.2 });
    });
    // The dot ends where it began: on the agent.
    k.mk(bot.tip[0], bot.tip[1], { b: 3, at: 0.2, dur: 1.0 });
    k.cap("QUESTIONS · PUSHBACK · WHERE WOULD THIS BREAK?", 3, { at: 1.5, keep: true });
    return k.svg();
  },
  html() {
    return takes
      .map(
        (take, i) =>
          `<p class="take" style="top: ${tops[i]}px" data-b="${i + 1}" data-a="fade" data-at="${i === 0 ? 0.2 : 0.3}">${take}</p>`,
      )
      .join("\n");
  },
};
