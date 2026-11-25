import { kit } from "../kit.mjs";

const r = (n) => Math.round(n * 100) / 100;

const attrs = (o, type) =>
  `data-b="${o.b}" data-a="${type}" data-at="${r(o.at)}"` +
  (o.dur != null ? ` data-dur="${o.dur}"` : "") +
  (o.x != null ? ` data-x="${o.x}"` : "");

const CY = 600;
// With no caption or reference line below, the scenes sit lower to balance the frame.
// The first scene is taller, so it drops less.
const DROP = { people: 36, rest: 56 };

export default {
  id: "s02",
  holds: 13,
  eyebrow: "05 / EVERYDAY ONTOLOGIES",
  title: ["You already use ontologies"],
  body() {
    const k = kit();
    const person = (kRef, cx, cy, s, look, o) => kRef.person(cx, cy, s, look, o);

    // The strip under the title names each idea as its scene starts, so the last hold shows all
    // three. The one in play is underlined.
    const strip = [
      [126, "Social graphs", 1, 6, 236],
      [457, "Disambiguation", 6, 10, 272],
      [823, "Regulated domains", 10, null, 316],
    ];
    strip.forEach(([x, name, b, x2, w]) => {
      k.sq(x, 279, { b, at: 0.05, solid: true, size: 12 });
      k.text(x + 22, 290, name, { b, at: 0.1, c: "t1s" });
      k.line(x + 22, 304, x + w, 304, { b, at: 0.2, dur: 0.3, x: x2 });
    });

    let drop = DROP.people;
    const mk = (x, y, o = {}) => {
      const via = o.via ? o.via.map(([vx, vy]) => `${r(vx)},${r(vy + drop)}`).join(";") : undefined;
      return k.mk(x, y + drop, { ...o, via });
    };
    // Where along a route (as fractions of its length) the stretch between two of its points lies.
    const stretch = (route, i, j) => {
      const len = [0];
      for (let n = 1; n < route.length; n++) {
        len.push(len[n - 1] + Math.hypot(route[n][0] - route[n - 1][0], route[n][1] - route[n - 1][1]));
      }
      return `${r(len[i] / len[len.length - 1])},${r(len[j] / len[len.length - 1])}`;
    };

    // 1 to 5. Maya. Then Tom, whom she knows. Then Priya, whom Tom knows. The dot walks from
    // Maya to Priya straight through Tom, and the app suggests Priya.
    k.raw(`<g transform="translate(0 ${drop})">`);
    {
      const x = 6;
      const s = 1.3;
      const NAME = CY + 214;
      const TAG = CY + 256;
      const shock = { brows: "high", mouth: "gasp", eyes: "wide", mark: "shock" };
      const arc = [
        [1360, 526],
        [1360, 322],
        [560, 322],
        [560, 490],
      ];
      const along = (t) =>
        [0, 1].map(
          (i) =>
            (1 - t) ** 3 * arc[0][i] +
            3 * (1 - t) ** 2 * t * arc[1][i] +
            3 * (1 - t) * t ** 2 * arc[2][i] +
            t ** 3 * arc[3][i],
        );

      // Two nested groups move people aside as each newcomer arrives: Maya for Tom (2),
      // the pair for Priya (3). Coordinates inside a group are the ones it has before it moves.
      k.line(1024, CY, 1286, CY, { b: 3, at: 1.6, dur: 0.6, x });
      k.raw(`<g data-shift-b="3" data-shift-x="-200" data-shift-y="0">`);
      k.line(824, CY, 1096, CY, { b: 2, at: 1.45, dur: 0.6, x });

      // On hold 4 the deck's own dot hides and this stand-in runs straight through Tom: drawn
      // before him, it goes in at one ear, hides behind his head, and comes out beside Priya.
      k.raw(`<g data-shift-b="4" data-shift-x="390" data-shift-y="0" data-shift-at="0.25" data-shift-dur="1.35">`);
      k.raw(`<circle class="acc" cx="1096" cy="${CY}" r="5" ${attrs({ b: 4, at: 0.1, x: 5 }, "pop")}/>`);
      k.raw(`</g>`);

      k.raw(`<g data-shift-b="2" data-shift-x="-200" data-shift-y="0">`);
      person(k, 960, CY, s, "bun", {
        b: 1,
        at: 0.1,
        x,
        top: "band",
        faces: [
          { face: { mouth: "smile" } },
          { b: 2, at: 2.3, face: { mouth: "grin" } },
          { b: 4, at: 0.55, face: shock },
          { b: 4, at: 1.75, face: { mouth: "smile" } },
        ],
        gaze: [
          { b: 1, to: [960, 478] },
          { b: 2, to: [1096, CY], pos: [760, CY], t: 1.5 },
          { b: 5, to: [560, 490], pos: [560, CY], t: 0.5 },
        ],
      });
      k.text(960, NAME, "Maya", { b: 1, at: 0.5, x, c: "t1s", anchor: "middle" });
      k.text(960, TAG, "Person", { b: 5, at: 1.6, x, c: "m2", anchor: "middle" });
      k.raw(`</g>`);
      mk(960, 478, { b: 1 });

      // 2. Maya steps aside and Tom arrives. The dot rides along above her, then curls round
      // the left of her head, goes in at one ear and out at the other, and runs the new line to Tom.
      const lap = [
        [760, 478],
        [724, 486],
        [698, 512],
        [686, 550],
        [690, 584],
        [704, CY],
        [816, CY],
        [1096, CY],
      ];
      mk(lap[0][0], lap[0][1], { b: 2, at: 0, dur: 0.9 });
      mk(lap[7][0], lap[7][1], { b: 2, at: 0.95, dur: 1.25, via: lap.slice(1, 7), hide: stretch(lap, 5, 6) });
      person(k, 1160, CY, s, "short", {
        b: 2,
        at: 0.8,
        x,
        top: "tie",
        faces: [
          { face: { brows: "cocked", mouth: "smirk" } },
          { b: 2, at: 2.35, face: { brows: "cocked", mouth: "side" } },
          { b: 4, at: 0.45, face: shock },
          { b: 4, at: 1.3, face: { brows: "uneven", mouth: "wavy", mark: "what" } },
          { b: 4, at: 2.2, face: { brows: "cocked", mouth: "smirk" } },
        ],
        gaze: [
          { b: 2, to: [1096, CY] },
          { b: 3, to: [1286, CY], pos: [960, CY], t: 1.0 },
          { b: 4, to: [896, CY], pos: [960, CY], t: 0.15 },
          { b: 4, to: [1286, CY], pos: [960, CY], t: 1.15 },
          { b: 5, to: [560, 490], pos: [960, CY], t: 0.3 },
        ],
      });
      k.text(1160, NAME, "Tom", { b: 2, at: 1.1, x, c: "t1s", anchor: "middle" });
      k.text(960, CY - 20, "knows", { b: 2, at: 2.1, x, c: "m2k", anchor: "middle" });
      k.text(1160, TAG, "Person", { b: 5, at: 1.7, x, c: "m2", anchor: "middle" });
      k.raw(`</g>`);

      // 3. The pair steps aside and Priya arrives.
      mk(896, CY, { b: 3, at: 0, dur: 0.9 });
      person(k, 1360, CY, s, "long", {
        b: 3,
        at: 0.8,
        x,
        top: "lapels",
        faces: [
          { face: { brows: "raised", mouth: "smile" } },
          { b: 3, at: 2.25, face: { brows: "raised", mouth: "broad" } },
          { b: 4, at: 0.65, face: shock },
          { b: 4, at: 1.75, face: { brows: "raised", mouth: "broad" } },
        ],
        gaze: [
          { b: 3, to: [1024, CY] },
          { b: 5, to: [560, 490], t: 0.2 },
        ],
      });
      k.text(1360, NAME, "Priya", { b: 3, at: 1.2, x, c: "t1s", anchor: "middle" });
      k.text(1160, CY - 20, "knows", { b: 3, at: 2.1, x, c: "m2k", anchor: "middle" });
      k.text(1360, TAG, "Person", { b: 5, at: 1.8, x, c: "m2", anchor: "middle" });

      // 4. The deck's dot hides while the stand-in runs through Tom, then returns beside Priya.
      mk(896, CY, { b: 4, at: 0.1, dur: 0.04, s: 0 });
      mk(1286, CY, { b: 4, at: 1.5, dur: 0.04, s: 0 });
      mk(1286, CY, { b: 4, at: 1.6, dur: 0.05 });

      // 5. The suggestion travels back over Tom's head, from Priya to Maya.
      k.path(`M${arc[0].join(" ")}C${arc[1].join(" ")} ${arc[2].join(" ")} ${arc[3].join(" ")}`, {
        b: 5,
        at: 0.2,
        dur: 1.2,
        dash: true,
        x,
      });
      mk(arc[3][0], arc[3][1], {
        b: 5,
        at: 0.1,
        dur: 1.35,
        via: [0, 0.15, 0.3, 0.45, 0.6, 0.75, 0.9].map(along),
      });
      k.text(960, 440, "PEOPLE YOU MAY KNOW", { b: 5, at: 1.5, x, c: "m1", anchor: "middle" });
    }
    k.raw(`</g>`);

    drop = DROP.rest;
    k.raw(`<g transform="translate(0 ${drop})">`);

    const HOME = [960, 540];
    const DESK = [330, 540];
    const ROWS = [440, 600, 760];
    const icon = (o, parts) =>
      k.raw(
        `<g ${attrs(o, "snap")}>` +
          parts
            .map((d) => `<path class="s" style="stroke-width: 2; stroke-linecap: round; stroke-linejoin: round" d="${d}"/>`)
            .join("") +
          `</g>`,
      );
    // What a system reads into a loose word is its own guess, so it is drawn dashed and
    // labelled. The typed facts it is checked against are drawn solid.
    const guess = (b, at, x, from, text, tx = from[0]) => {
      k.line(from[0], from[1], from[0], from[1] + 26, { b, at, dur: 0.2, dash: true, x });
      k.text(tx, from[1] + 58, text, { b, at: at + 0.2, x, c: "cd", anchor: "middle" });
      k.text(tx, from[1] + 94, "THE ENGINE'S GUESS", { b, at: at + 0.35, x, c: "m2", anchor: "middle" });
    };

    // 6 to 9. Tom asks for Mercury. There are three. Each has its own ID and typed facts,
    // and only one of them is something you can play.
    {
      const x = 10;
      const things = [
        ["Q308", "instance of", "planet"],
        ["Q925", "instance of", "chemical element"],
        ["Q15869", "occupation", "singer"],
      ];
      const FORK = [790, 600];

      // 6. Tom, centred, asking.
      k.raw(`<g data-shift-b="7" data-shift-x="${DESK[0] - HOME[0]}" data-shift-y="0">`);
      person(k, HOME[0], HOME[1], 1.3, "short", {
        b: 6,
        at: 0.35,
        x,
        top: "tie",
        faces: [
          { face: { brows: "cocked", mouth: "smirk" } },
          { b: 7, at: 2.2, face: { brows: "uneven", mouth: "flat" } },
          { b: 8, at: 2.1, face: { brows: "cocked", mouth: "smirk" } },
          { b: 9, at: 1.5, face: { brows: "raised", mouth: "side" } },
        ],
        gaze: [
          { b: 6, to: [1300, 380] },
          { b: 7, to: FORK, pos: DESK, t: 1.0 },
          { b: 8, to: [1330, ROWS[2]], pos: DESK, t: 1.2 },
          { b: 9, to: [1560, 600], pos: DESK, t: 0.9 },
        ],
      });
      k.text(HOME[0], HOME[1] + 214, "Tom", { b: 6, at: 0.7, x, c: "t1s", anchor: "middle" });
      k.path(
        `M1058 330H1342a18 18 0 0 1 18 18V388a18 18 0 0 1-18 18H1112L1032 450L1080 406H1058a18 18 0 0 1-18-18V348a18 18 0 0 1 18-18Z`,
        { b: 6, at: 0.9, dur: 0.6, x },
      );
      k.text(1090, 380, "Play Mercury", { b: 6, at: 1.4, x, c: "t1s" });
      k.raw(`</g>`);
      mk(1066, 369, { b: 6, at: 0 });

      // 7. He steps aside. One word, three things.
      mk(1066 + DESK[0] - HOME[0], 369, { b: 7, at: 0, dur: 0.9 });
      k.text(620, 614, "Mercury", { b: 7, at: 1.0, x, c: "t1" });
      k.text(620, 664, "which one?", { b: 7, at: 2.3, x: 8, c: "m2" });
      things.forEach(([id, prop, value], i) => {
        const y = ROWS[i];
        const keep = i === 2 ? x : 9;
        k.line(FORK[0], FORK[1], 868, y, { b: 7, at: 1.3 + i * 0.12, dur: 0.4, dash: true, x: keep });

        // 8. Each one has its own identifier and says what it is.
        k.text(940, y + 9, id, { b: 8, at: 0.25 + i * 0.12, x: keep, c: "cd" });
        k.line(1056, y, 1086, y, { b: 8, at: 0.4 + i * 0.12, dur: 0.15, hair: true, x: keep });
        k.text(1098, y + 9, prop, { b: 8, at: 0.45 + i * 0.12, x: keep, c: "m2" });
        k.line(1304, y, 1334, y, { b: 8, at: 0.6 + i * 0.12, dur: 0.15, hair: true, x: keep });
        k.text(1348, y + 9, value, { b: 8, at: 0.65 + i * 0.12, x: keep, c: "cd" });
        if (i !== 2) k.line(1340, y, 1356 + value.length * 16.8, y, { b: 8, at: 2.0, dur: 0.2, x: keep });
      });
      k.circ(900, ROWS[0], 18, { b: 7, at: 1.75, dur: 0.25, x: 9 });
      k.raw(
        `<ellipse class="s" cx="900" cy="${ROWS[0]}" rx="30" ry="8" transform="rotate(-20 900 ${ROWS[0]})" ${attrs({ b: 7, at: 1.85, x: 9 }, "snap")}/>`,
      );
      k.sq(900, ROWS[1], { b: 7, at: 1.9, size: 44, x: 9 });
      k.text(900, ROWS[1] + 10, "Hg", { b: 7, at: 1.95, x: 9, c: "cd", anchor: "middle" });
      k.raw(`<circle class="f" cx="893" cy="${ROWS[2] + 12}" r="9" ${attrs({ b: 7, at: 2.05, x }, "pop")}/>`);
      k.path(`M901.5 ${ROWS[2] + 12}V${ROWS[2] - 24}q16 4 16 20`, { b: 7, at: 2.08, dur: 0.2, x });

      // What "play" asks for is the assistant's reading. The facts decide which Mercury fits it.
      guess(8, 1.1, x, [492, 410], "needs a musician", 580);
      k.line(FORK[0], FORK[1], 868, ROWS[2], { b: 8, at: 1.6, dur: 0.4, x });
      mk(868, ROWS[2], { b: 8, at: 1.2, dur: 0.9, via: [FORK] });

      // 9. The other two drop away and the music starts.
      k.rect(1490, 500, 310, 200, { b: 9, at: 0.6, dur: 0.5, x });
      k.text(1514, 548, "NOW PLAYING", { b: 9, at: 0.9, x, c: "m2" });
      k.text(1514, 602, "Freddie Mercury", { b: 9, at: 1.0, x, c: "t1s" });
      [0, 1, 2, 3, 4, 5, 6].forEach((n) => {
        const h = [14, 30, 20, 38, 24, 34, 12][n];
        k.line(1548 + n * 16, 672, 1548 + n * 16, 672 - h, { b: 9, at: 1.3 + n * 0.05, dur: 0.2, x });
      });
      mk(1514, 656, { b: 9, at: 0.6, dur: 0.6 });
    }

    // 10 to 13. Sam has a heart attack. Three clinicians write it three ways, one concept ID
    // counts it once, and that concept's parents put him on the heart clinic's list.
    {
      const notes = [
        ["GP", "heart attack"],
        ["EMERGENCY", "MI"],
        ["CARDIOLOGY", "myocardial infarction"],
      ];
      const CONCEPT = [1262, 600];

      // 10. Sam, centred, unwell.
      k.raw(`<g data-shift-b="11" data-shift-x="${DESK[0] - HOME[0]}" data-shift-y="0">`);
      person(k, HOME[0], HOME[1], 1.3, "older", {
        b: 10,
        at: 0.35,
        faces: [
          { face: { brows: "worried", mouth: "flat" } },
          { b: 12, at: 1.2, face: { brows: "level", mouth: "flat" } },
          { b: 13, at: 2.3, face: { brows: "level", mouth: "smile" } },
        ],
        gaze: [
          { b: 10, to: [1190, 470] },
          { b: 11, to: [1196, 600], pos: DESK, t: 1.6 },
          { b: 13, to: [1262, 340], pos: DESK, t: 1.0 },
        ],
      });
      k.text(HOME[0], HOME[1] + 214, "Sam", { b: 10, at: 0.7, c: "t1s", anchor: "middle" });
      k.text(HOME[0], HOME[1] + 254, "one patient", { b: 10, at: 0.8, c: "m2", anchor: "middle" });
      k.raw(`</g>`);
      icon({ b: 10, at: 1.2, x: 11 }, [
        `M1190 508C1124 458 1150 404 1190 438C1230 404 1256 458 1190 508Z`,
        `M1150 466h18l8 -16l12 32l8 -16h24`,
      ]);
      icon({ b: 10, at: 1.6, x: 11 }, [`M1128 420l-12 -8`, `M1252 420l12 -8`, `M1118 462h-14`, `M1262 462h14`]);
      mk(1190, 530, { b: 10, at: 0 });

      // 11. He steps aside. Three notes, three wordings, and a system that matches text sees three conditions.
      notes.forEach(([who, term], i) => {
        const y = ROWS[i];
        const at = 0.9 + i * 0.18;
        k.line(450, 600, 560, y, { b: 11, at, dur: 0.3, hair: true });
        k.rect(560, y - 56, 440, 112, { b: 11, at: at + 0.15, dur: 0.45 });
        k.text(584, y - 12, who, { b: 11, at: at + 0.4, c: "m2" });
        k.text(584, y + 32, term, { b: 11, at: at + 0.5, c: "t1s" });
        k.line(1000, y, 1176, y, { b: 11, at: 1.8 + i * 0.1, dur: 0.3, dash: true, x: 12 });
        k.sq(1196, y, { b: 11, at: 2.1 + i * 0.1, size: 22, x: 12 });
      });
      k.text(1260, 596, "3 conditions?", { b: 11, at: 2.3, x: 12, c: "t1" });
      k.text(1260, 646, "COUNTED THREE TIMES", { b: 11, at: 2.4, x: 12, c: "m2" });
      mk(1196, ROWS[1], { b: 11, at: 1.9 });

      // 12. Every wording is a synonym of one concept.
      k.path(`M1000 ${ROWS[0]}C1130 ${ROWS[0]} 1110 ${CONCEPT[1]} 1240 ${CONCEPT[1]}`, { b: 12, at: 0.35, dur: 0.5 });
      k.line(1000, CONCEPT[1], 1240, CONCEPT[1], { b: 12, at: 0.45, dur: 0.4 });
      k.path(`M1000 ${ROWS[2]}C1130 ${ROWS[2]} 1110 ${CONCEPT[1]} 1240 ${CONCEPT[1]}`, { b: 12, at: 0.55, dur: 0.5 });
      k.sq(CONCEPT[0], CONCEPT[1], { b: 12, at: 1.05, size: 34 });
      k.text(1300, 612, "22298006", { b: 12, at: 1.2, c: "t1", overlap: true });
      k.text(1300, 658, "ONE CONCEPT, COUNTED ONCE", { b: 12, at: 1.35, c: "m2", overlap: true });
      mk(CONCEPT[0], CONCEPT[1], { b: 12, at: 0.6, dur: 0.5 });

      // 13. The concept has parents. The clinic asks for heart disease and finds Sam, though
      // none of his notes says so. The upper link stands for more than one step, so it is broken.
      k.line(CONCEPT[0], 583, CONCEPT[0], 488, { b: 13, at: 0.2, dur: 0.3 });
      k.text(1284, 546, "is a", { b: 13, at: 0.35, c: "m2" });
      k.sq(CONCEPT[0], 474, { b: 13, at: 0.5, size: 22 });
      k.text(1296, 484, "Ischemic heart disease", { b: 13, at: 0.55, c: "t1s" });
      k.line(CONCEPT[0], 460, CONCEPT[0], 428, { b: 13, at: 0.7, dur: 0.15 });
      [418, 408, 398].forEach((y) =>
        k.raw(`<circle class="f" cx="${CONCEPT[0]}" cy="${y}" r="1.8" ${attrs({ b: 13, at: 0.8 }, "pop")}/>`),
      );
      k.line(CONCEPT[0], 388, CONCEPT[0], 356, { b: 13, at: 0.85, dur: 0.15 });
      k.text(1284, 416, "is a", { b: 13, at: 0.9, c: "m2" });
      k.sq(CONCEPT[0], 342, { b: 13, at: 1.0, size: 22 });
      k.text(1296, 352, "Heart disease", { b: 13, at: 1.05, c: "t1s" });
      k.line(1528, 342, 1552, 342, { b: 13, at: 1.3, dur: 0.15, hair: true });
      k.rect(1560, 290, 250, 108, { b: 13, at: 1.3, dur: 0.4 });
      k.text(1580, 330, "CLINIC LIST", { b: 13, at: 1.6, c: "m2" });
      k.text(1610, 376, "Sam", { b: 13, at: 2.3, c: "t1s" });
      k.path(`M1690 364l8 9l16 -20`, { b: 13, at: 2.45, dur: 0.2 });
      mk(1590, 366, {
        b: 13,
        at: 1.0,
        dur: 1.3,
        via: [
          [CONCEPT[0], 474],
          [CONCEPT[0], 342],
          [1552, 342],
        ],
      });
    }
    k.raw(`</g>`);
    return k.svg();
  },
};
