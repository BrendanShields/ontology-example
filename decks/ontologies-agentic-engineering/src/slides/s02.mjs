import { kit } from "../kit.mjs";

const r = (n) => Math.round(n * 100) / 100;

const attrs = (o, type) =>
  `data-b="${o.b}" data-a="${type}" data-at="${r(o.at)}"` +
  (o.dur != null ? ` data-dur="${o.dur}"` : "") +
  (o.x != null ? ` data-x="${o.x}"` : "");

const PAPER = "#f2f2ef";
const TINT = "#d4d4ce";
const INK = "#141414";
const TURN = 4;
let people = 0;

// One person, drawn as an outlined avatar in two tones: a bold ink line, a flat tint for
// hair and one piece of clothing, dot eyes and a small mouth. (cx, cy) is the centre of
// the face. The whole figure enters as one piece, because its parts are filled to sit in
// front of each other.
//   look   bun | short | long | beard | older
//   faces  [{ face }, { b, at, face }, ...] the face on arrival, then each change of it.
//          face = { brows: none | level | raised | high | cocked | worried | uneven,
//                   mouth: smile | broad | grin | smirk | side | flat | gasp | wavy,
//                   eyes: wide, mark: shock | what }
//   top    what the tint picks out on the clothes: band | tie | lapels | pocket | none
//   gaze   [{ b, to: [x, y], pos?: [x, y], t? }] where the face turns on each hold. The first
//          entry is how the person arrives. `pos` is where the person stands by then, if a
//          group has moved them. The eyes and mouth slide together, which reads as a head
//          turning and keeps the eyes as plain dots.
function person(k, cx, cy, s, look, o) {
  const X = (v) => r(cx + v * s);
  const Y = (v) => r(cy + v * s);
  const L = (v) => r(v * s);
  const pt = (x, y) => `${X(x)} ${Y(y)}`;
  const line = `stroke: ${INK}; stroke-width: ${L(2.1)}; stroke-linejoin: round; stroke-linecap: round`;
  const shape = (d, fill = PAPER, extra = "") => k.raw(`<path style="fill: ${fill}; ${line}" d="${d}"${extra}/>`);
  const stroke = (d, extra = "") => shape(d, "none", extra);
  const flat = (d, fill = TINT) => k.raw(`<path style="fill: ${fill}" d="${d}"/>`);

  let arrive = { x: 0, y: 0 };
  let seen = arrive;
  const turns = [];
  (o.gaze ?? []).forEach((g, i) => {
    const [px, py] = g.pos ?? [cx, cy];
    const dx = g.to[0] - px;
    const dy = g.to[1] - py;
    const len = Math.hypot(dx, dy) || 1;
    const at = { x: r((dx / len) * TURN * s), y: r((dy / len) * TURN * 0.7 * s) };
    if (i === 0) arrive = seen = at;
    else if (Math.hypot(at.x - seen.x, at.y - seen.y) > 0.5) {
      turns.push({ b: g.b, t: g.t ?? 0.1, x: r(at.x - seen.x), y: r(at.y - seen.y) });
      seen = at;
    }
  });

  const cap = `M${pt(-36, -3)}V${Y(-22)}C${pt(-36, -54)} ${pt(36, -54)} ${pt(36, -22)}V${Y(-3)}`;

  k.raw(`<g ${attrs({ b: o.b, at: o.at, dur: 0.35, x: o.x }, "snap")}>`);
  if (look === "long") {
    shape(
      `M${pt(-45, -20)}C${pt(-45, -62)} ${pt(45, -62)} ${pt(45, -20)}V${Y(50)}Q${pt(45, 66)} ${pt(30, 66)}` +
        `H${X(-30)}Q${pt(-45, 66)} ${pt(-45, 50)}Z`,
      TINT,
    );
  }

  // Shoulders, a short neck and a collar.
  shape(
    `M${pt(-82, 132)}V${Y(102)}Q${pt(-82, 76)} ${pt(-56, 68)}L${pt(-14, 54)}V${Y(38)}H${X(14)}V${Y(54)}` +
      `L${pt(56, 68)}Q${pt(82, 76)} ${pt(82, 102)}V${Y(132)}Z`,
  );
  const top = o.top ?? "none";
  if (top === "band") flat(`M${pt(-81, 100)}H${X(81)}V${Y(116)}H${X(-81)}Z`);
  if (top === "pocket") flat(`M${pt(28, 94)}H${X(56)}V${Y(114)}H${X(28)}Z`);
  if (top === "lapels") {
    shape(`M${pt(-14, 54)}L${pt(-32, 88)}L${pt(0, 72)}Z`, TINT);
    shape(`M${pt(14, 54)}L${pt(32, 88)}L${pt(0, 72)}Z`, TINT);
  } else if (look === "beard" || look === "older") stroke(`M${pt(-14, 54)}Q${pt(0, 74)} ${pt(14, 54)}`);
  else stroke(`M${pt(-14, 54)}L${pt(0, 72)}L${pt(14, 54)}`);
  if (top === "tie") shape(`M${pt(-5, 74)}H${X(5)}L${pt(8, 112)}L${pt(0, 122)}L${pt(-8, 112)}Z`, TINT);

  // Ears, then the face over them.
  [-1, 1].forEach((side) =>
    k.raw(`<circle style="fill: ${PAPER}; ${line}" cx="${X(side * 35)}" cy="${Y(4)}" r="${L(8)}"/>`),
  );
  shape(
    `M${pt(-34, -22)}C${pt(-34, -52)} ${pt(34, -52)} ${pt(34, -22)}V${Y(8)}A${L(34)} ${L(34)} 0 0 1 ${pt(-34, 8)}Z`,
  );
  if (look === "beard") {
    // A chin-strap beard below the mouth. Higher, it reads as a face mask.
    shape(
      `M${pt(-34, 6)}V${Y(8)}A${L(34)} ${L(34)} 0 0 0 ${pt(34, 8)}V${Y(6)}Q${pt(24, 30)} ${pt(0, 30)}` +
        `Q${pt(-24, 30)} ${pt(-34, 6)}Z`,
      TINT,
    );
  }

  if (look === "bun") {
    k.raw(`<circle style="fill: ${TINT}; ${line}" cx="${X(0)}" cy="${Y(-58)}" r="${L(15)}"/>`);
    shape(`${cap}Q${pt(28, -26)} ${pt(0, -27)}Q${pt(-28, -26)} ${pt(-36, -3)}Z`, TINT);
  }
  if (look === "short") shape(`${cap}Q${pt(30, -22)} ${pt(12, -23)}Q${pt(-12, -25)} ${pt(-36, -3)}Z`, TINT);
  if (look === "beard") shape(`${cap}L${pt(29, -19)}H${X(-29)}L${pt(-36, -3)}Z`, TINT);
  if (look === "long") shape(`${cap}Q${pt(30, -30)} ${pt(0, -35)}Q${pt(-30, -30)} ${pt(-36, -3)}Z`, TINT);
  if (look === "older") {
    [-1, 1].forEach((side) =>
      shape(
        `M${pt(side * 36, -3)}V${Y(-20)}Q${pt(side * 36, -30)} ${pt(side * 29, -35)}` +
          `Q${pt(side * 27, -16)} ${pt(side * 36, -3)}Z`,
        TINT,
      ),
    );
  }

  // Everything that turns with the head.
  const who = people++;
  turns.forEach((m) =>
    k.raw(
      `<g data-shift-b="${m.b}" data-shift-x="${m.x}" data-shift-y="${m.y}" data-shift-dur="0.35" data-shift-at="${m.t}">`,
    ),
  );
  k.raw(`<g transform="translate(${arrive.x} ${arrive.y})">`);
  // Each person blinks on their own clock.
  const blink = `data-phase="${r(who * 1.37)}" data-every="${r(3.1 + (who % 4) * 0.55)}"`;
  [-13, 13].forEach((ex) => {
    k.raw(`<g data-idle="blink" data-origin="${X(ex)} ${Y(0)}" ${blink}>`);
    k.raw(`<circle style="fill: ${INK}" cx="${X(ex)}" cy="${Y(0)}" r="${L(3.3)}"/>`);
    k.raw(`</g>`);
  });
  const low = look === "older" ? 7 : 0;
  if (look === "older") {
    flat(
      `M${pt(-15, 12)}Q${pt(-7, 5)} ${pt(0, 10)}Q${pt(7, 5)} ${pt(15, 12)}Q${pt(7, 17)} ${pt(0, 14)}` +
        `Q${pt(-7, 17)} ${pt(-15, 12)}Z`,
      INK,
    );
  }

  const browOf = {
    level: (side) => `M${pt(side * 19, -9)}Q${pt(side * 13, -12)} ${pt(side * 7, -9)}`,
    raised: (side) => `M${pt(side * 19, -10)}Q${pt(side * 13, -15)} ${pt(side * 7, -11)}`,
    high: (side) => `M${pt(side * 20, -14)}Q${pt(side * 13, -21)} ${pt(side * 6, -15)}`,
    worried: (side) => `M${pt(side * 20, -8)}L${pt(side * 7, -13)}`,
    cocked: (side) => (side === 1 ? browOf.raised(side) : browOf.level(side)),
    uneven: (side) => (side === 1 ? browOf.high(side) : `M${pt(-20, -12)}L${pt(-7, -8)}`),
  };
  const mouthOf = {
    smile: () => stroke(`M${pt(-7, 14 + low)}A${L(7)} ${L(7)} 0 0 0 ${pt(7, 14 + low)}`),
    broad: () => stroke(`M${pt(-11, 12)}A${L(11)} ${L(11)} 0 0 0 ${pt(11, 12)}`),
    grin: () => shape(`M${pt(-10, 12)}A${L(10)} ${L(10)} 0 0 0 ${pt(10, 12)}Z`, INK),
    smirk: () => stroke(`M${pt(-7, 17)}Q${pt(2, 23)} ${pt(10, 13)}`),
    side: () =>
      shape(`M${pt(-9, 14)}Q${pt(2, 17)} ${pt(11, 11)}Q${pt(9, 25)} ${pt(-1, 23)}Q${pt(-7, 21)} ${pt(-9, 14)}Z`, INK),
    flat: () => stroke(`M${pt(-5, 17 + low)}H${X(5)}`),
    gasp: () =>
      k.raw(
        `<ellipse style="fill: ${INK}" cx="${X(0)}" cy="${Y(19 + low)}" rx="${L(4.6)}" ry="${L(6.2)}"/>`,
      ),
    wavy: () => stroke(`M${pt(-9, 18)}q${L(3)} ${L(-5)} ${L(6)} 0t${L(6)} 0t${L(6)} 0`),
  };

  // A face is a run of states. Each one shows from its own moment until the next begins.
  const faces = o.faces ?? [{ face: {} }];
  faces.forEach((state, i) => {
    const next = faces[i + 1];
    const f = state.face ?? {};
    let timing = i ? " " + attrs({ b: state.b, at: state.at }, "pop") : "";
    if (next) timing += ` data-x="${next.b}" data-xat="${r(Math.max(0, next.at - 0.1))}"`;
    k.raw(`<g${timing}>`);
    if (f.eyes === "wide") {
      [-13, 13].forEach((ex) =>
        k.raw(`<circle style="fill: ${INK}" cx="${X(ex)}" cy="${Y(0)}" r="${L(4.8)}"/>`),
      );
    }
    if (f.brows && f.brows !== "none") [-1, 1].forEach((side) => stroke(browOf[f.brows](side)));
    // The mouth breathes a little in the presenter, each one at its own pace.
    k.raw(
      `<g data-idle="mouth" data-origin="${X(0)} ${Y(16 + low)}" data-amp="0.08" data-phase="${r(who * 0.9)}" data-every="${r(2.3 + (who % 3) * 0.45)}">`,
    );
    mouthOf[f.mouth ?? "smile"]();
    k.raw(`</g>`);
    if (f.mark === "shock") {
      [-1, 1].forEach((side) => {
        stroke(`M${pt(side * 50, -34)}L${pt(side * 60, -43)}`);
        stroke(`M${pt(side * 55, -17)}L${pt(side * 67, -20)}`);
      });
    }
    if (f.mark === "what") {
      k.raw(`<text class="t1" x="${X(46)}" y="${Y(-40)}" data-layout-allow-overlap>?</text>`);
    }
    k.raw(`</g>`);
  });
  k.raw(`</g>`);
  turns.forEach(() => k.raw(`</g>`));
  k.raw(`</g>`);
}

function star(cx, cy, R) {
  let d = "";
  for (let i = 0; i < 10; i++) {
    const a = -Math.PI / 2 + (i * Math.PI) / 5;
    const rad = i % 2 ? R * 0.42 : R;
    d += `${i ? "L" : "M"}${r(cx + rad * Math.cos(a))} ${r(cy + rad * Math.sin(a))}`;
  }
  return d + "Z";
}

const CY = 600;
// With no caption or reference line below, the scenes sit lower to balance the frame.
// The first scene is taller, so it drops less.
const DROP = { people: 36, rest: 56 };

export default {
  id: "s02",
  holds: 21,
  eyebrow: "02 / EVERYDAY ONTOLOGIES",
  title: ["You already use ontologies"],
  css: `      #s02 .eyebrow {
        visibility: hidden;
      }`,
  body() {
    const k = kit();
    people = 0;

    // The strip under the title names each idea as its scene starts, so the last hold shows all
    // four. The one in play is underlined.
    const strip = [
      [126, "Social graphs", 1, 9, 236],
      [457, "Search", 9, 14, 132],
      [683, "Disambiguation", 14, 18, 272],
      [1049, "Regulated domains", 18, null, 316],
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

    // 1 to 8. Maya. Then Tom, whom she knows. Then Priya, whom Tom knows. The dot walks from
    // Maya to Priya straight through Tom. Then Ben, who has Maya's job at the same company.
    k.raw(`<g transform="translate(0 ${drop})">`);
    {
      const x = 9;
      const s = 1.3;
      const ORG = [1000, 372];
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

      // Three nested groups move people aside as each newcomer arrives: Maya for Tom (2),
      // the pair for Priya (3), all three for Ben (7). Coordinates inside a group are the
      // ones it has before it moves.
      k.raw(`<g data-shift-b="7" data-shift-x="-160" data-shift-y="0">`);
      k.line(1024, CY, 1286, CY, { b: 3, at: 1.6, dur: 0.6, x });
      k.raw(`<g data-shift-b="3" data-shift-x="-200" data-shift-y="0">`);
      k.line(824, CY, 1096, CY, { b: 2, at: 1.45, dur: 0.6, x });

      // On holds 4 and 5 the deck's own dot hides and this one stands in for it. It is drawn
      // before Tom, so it goes into one ear, is hidden by his head, and comes out of the other.
      k.raw(`<g data-shift-b="5" data-shift-x="326" data-shift-y="0" data-shift-at="0.2" data-shift-dur="0.9">`);
      k.raw(`<g data-shift-b="4" data-shift-x="64" data-shift-y="0" data-shift-at="0.3" data-shift-dur="0.5">`);
      k.raw(`<circle class="acc" cx="1096" cy="${CY}" r="5" ${attrs({ b: 4, at: 0.1, x: 6 }, "pop")}/>`);
      k.raw(`</g></g>`);

      k.raw(`<g data-shift-b="2" data-shift-x="-200" data-shift-y="0">`);
      person(k, 960, CY, s, "bun", {
        b: 1,
        at: 0.1,
        x,
        top: "band",
        faces: [
          { face: { mouth: "smile" } },
          { b: 2, at: 2.3, face: { mouth: "grin" } },
          { b: 4, at: 0.8, face: shock },
          { b: 5, at: 0.7, face: { mouth: "smile" } },
          { b: 8, at: 1.6, face: { mouth: "grin" } },
        ],
        gaze: [
          { b: 1, to: [960, 478] },
          { b: 2, to: [1096, CY], pos: [760, CY], t: 1.5 },
          { b: 6, to: [560, 490], pos: [560, CY], t: 0.5 },
          { b: 7, to: ORG, pos: [400, CY] },
          { b: 8, to: [1600, CY], pos: [400, CY], t: 0.5 },
        ],
      });
      k.text(960, NAME, "Maya", { b: 1, at: 0.5, x, c: "t1s", anchor: "middle" });
      k.text(960, TAG, "Person", { b: 6, at: 1.6, x: 8, c: "m2", anchor: "middle" });
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
          { b: 4, at: 0.55, face: shock },
          { b: 5, at: 0.55, face: { brows: "uneven", mouth: "wavy", mark: "what" } },
          { b: 5, at: 1.9, face: { brows: "cocked", mouth: "smirk" } },
        ],
        gaze: [
          { b: 2, to: [1096, CY] },
          { b: 3, to: [1286, CY], pos: [960, CY], t: 1.0 },
          { b: 4, to: [896, CY], pos: [960, CY], t: 0.2 },
          { b: 5, to: [1286, CY], pos: [960, CY], t: 0.6 },
          { b: 6, to: [560, 490], pos: [960, CY], t: 0.3 },
          { b: 7, to: ORG, pos: [800, CY] },
          { b: 8, to: [1600, CY], pos: [800, CY], t: 0.5 },
        ],
      });
      k.text(1160, NAME, "Tom", { b: 2, at: 1.1, x, c: "t1s", anchor: "middle" });
      k.text(960, CY - 20, "knows", { b: 2, at: 2.1, x, c: "m2k", anchor: "middle" });
      k.text(1160, TAG, "Person", { b: 6, at: 1.7, x: 8, c: "m2", anchor: "middle" });
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
          { b: 4, at: 0.85, face: shock },
          { b: 5, at: 0.75, face: { brows: "raised", mouth: "broad" } },
        ],
        gaze: [
          { b: 3, to: [1024, CY] },
          { b: 6, to: [560, 490], t: 0.2 },
          { b: 7, to: ORG, pos: [1200, CY] },
          { b: 8, to: [1600, CY], pos: [1200, CY], t: 0.5 },
        ],
      });
      k.text(1360, NAME, "Priya", { b: 3, at: 1.2, x, c: "t1s", anchor: "middle" });
      k.text(1160, CY - 20, "knows", { b: 3, at: 2.1, x, c: "m2k", anchor: "middle" });
      k.text(1360, TAG, "Person", { b: 6, at: 1.8, x: 8, c: "m2", anchor: "middle" });
      k.raw(`</g>`);

      // 4 and 5. The deck's dot hides while the stand-in goes in at one ear, and returns
      // where the stand-in stops beside Priya.
      mk(896, CY, { b: 4, at: 0.1, dur: 0.05, s: 0 });
      mk(1286, CY, { b: 5, at: 1.1, dur: 0.05 });

      // 6. The suggestion travels back over Tom's head, from Priya to Maya.
      k.path(`M${arc[0].join(" ")}C${arc[1].join(" ")} ${arc[2].join(" ")} ${arc[3].join(" ")}`, {
        b: 6,
        at: 0.2,
        dur: 1.2,
        dash: true,
        x: 7,
      });
      mk(arc[3][0], arc[3][1], {
        b: 6,
        at: 0.1,
        dur: 1.35,
        via: [0, 0.15, 0.3, 0.45, 0.6, 0.75, 0.9].map(along),
      });
      k.text(960, 440, "PEOPLE YOU MAY KNOW", { b: 6, at: 1.5, x: 7, c: "m1", anchor: "middle" });

      // 7. All three work at one company, and so does Ben.
      const seats = [
        [400, 498],
        [800, 534],
        [1200, 528],
        [1600, 534],
      ];
      mk(ORG[0], ORG[1], { b: 7, at: 0, dur: 0.9 });
      k.rect(ORG[0] - 22, ORG[1] - 26, 44, 52, { b: 7, at: 0.9, dur: 0.35, x });
      [
        [-10, -12],
        [10, -12],
        [-10, 6],
        [10, 6],
      ].forEach(([wx, wy]) => k.sq(ORG[0] + wx, ORG[1] + wy, { b: 7, at: 1.1, size: 8, x }));
      k.text(ORG[0] + 44, ORG[1] + 11, "Acme", { b: 7, at: 1.15, x, c: "t1s" });
      k.text(ORG[0] + 146, ORG[1] + 11, "Organization", { b: 7, at: 1.25, x, c: "m2" });
      k.line(ORG[0], ORG[1] + 26, ORG[0], 440, { b: 7, at: 1.3, dur: 0.2, x });
      k.line(seats[0][0], 440, seats[3][0], 440, { b: 7, at: 1.4, dur: 0.6, x });
      seats.forEach(([sx, sy], i) => k.line(sx, 440, sx, sy, { b: 7, at: 1.8 + i * 0.08, dur: 0.25, x }));
      k.text(600, 420, "works at", { b: 7, at: 2.1, x, c: "m2k", anchor: "middle" });
      person(k, 1600, CY, s, "beard", {
        b: 7,
        at: 1.0,
        x,
        top: "pocket",
        faces: [{ face: { mouth: "flat" } }, { b: 8, at: 1.6, face: { mouth: "smile" } }],
        gaze: [
          { b: 7, to: ORG },
          { b: 8, to: [400, CY], t: 0.5 },
        ],
      });
      k.text(1600, NAME, "Ben", { b: 7, at: 1.4, x, c: "t1s", anchor: "middle" });
      k.text(1600, TAG, "Person", { b: 7, at: 1.5, x: 8, c: "m2", anchor: "middle" });

      // 8. Maya and Ben have the same role there. The dot walks from the company to Ben.
      ["Designer", "Engineer", "Analyst", "Designer"].forEach((role, i) =>
        k.text(seats[i][0], TAG, role, {
          b: 8,
          at: 0.3 + i * 0.08,
          x,
          c: "cd",
          anchor: "middle",
          overlap: true,
        }),
      );
      mk(seats[3][0], seats[3][1], {
        b: 8,
        at: 0.5,
        dur: 1.0,
        via: [
          [ORG[0], 440],
          [seats[3][0], 440],
        ],
      });
      [0, 3].forEach((i) =>
        k.line(seats[i][0] - 68, TAG + 12, seats[i][0] + 68, TAG + 12, { b: 8, at: 1.2 + i * 0.05, dur: 0.25, x }),
      );
      k.path(`M400 ${TAG + 18}V${TAG + 42}H780`, { b: 8, at: 1.5, dur: 0.4, dash: true, x });
      k.path(`M1220 ${TAG + 42}H1600V${TAG + 18}`, { b: 8, at: 1.8, dur: 0.4, dash: true, x });
      k.text(1000, TAG + 52, "PEOPLE YOU MAY KNOW", { b: 8, at: 2.0, x, c: "m1", anchor: "middle" });
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

    // 9 to 13. Maya is hungry and searches for something quick. Read as bare numbers, the
    // pages mislead the engine. Read as typed durations, they can be held to what it takes
    // "quick" to mean. The result is her reward.
    {
      const x = 14;
      const recipes = [
        ["Beef stew", "3", "3 h"],
        ["Lentil curry", "20", "20 min"],
        ["Lasagne", "90", "90 min"],
      ];
      const NODE = [700, 600];
      const BOX = [170, 790];

      // 9. Maya, centred, thinking about food.
      k.raw(`<g data-shift-b="10" data-shift-x="${DESK[0] - HOME[0]}" data-shift-y="0">`);
      person(k, HOME[0], HOME[1], 1.3, "bun", {
        b: 9,
        at: 0.35,
        x,
        top: "band",
        faces: [
          { face: { brows: "cocked", mouth: "flat" } },
          { b: 10, at: 1.2, face: { mouth: "smile" } },
          { b: 11, at: 2.2, face: { brows: "worried", mouth: "flat" } },
          { b: 12, at: 2.0, face: { mouth: "smile" } },
          { b: 13, at: 1.7, face: { brows: "raised", mouth: "grin" } },
        ],
        gaze: [
          { b: 9, to: [1240, 360] },
          { b: 10, to: [330, 900], pos: DESK, t: 1.0 },
          { b: 11, to: [860, ROWS[0]], pos: DESK, t: 0.4 },
          { b: 12, to: [860, ROWS[1]], pos: DESK, t: 1.5 },
          { b: 13, to: [1640, 600], pos: DESK, t: 1.0 },
        ],
      });
      k.text(HOME[0], HOME[1] + 214, "Maya", { b: 9, at: 0.7, x, c: "t1s", anchor: "middle" });
      k.raw(`</g>`);
      // A thought: two small puffs, then a cloud with three dinners in it.
      k.circ(1052, 452, 8, { b: 9, at: 0.9, dur: 0.15, x: 10 });
      k.circ(1086, 420, 13, { b: 9, at: 1.05, dur: 0.2, x: 10 });
      k.raw(
        `<rect class="s" x="1090" y="290" width="360" height="130" rx="65" ${attrs({ b: 9, at: 1.25, dur: 0.6, x: 10 }, "draw")}/>`,
      );
      const cy = 358;
      icon({ b: 9, at: 1.7, x: 10 }, [
        `M1140 ${cy - 2}H1192A26 22 0 0 1 1140 ${cy - 2}Z`,
        `M1158 ${cy - 12}q-5 -7 0 -14q5 -7 0 -14`,
        `M1174 ${cy - 12}q-5 -7 0 -14q5 -7 0 -14`,
      ]);
      icon({ b: 9, at: 1.95, x: 10 }, [
        `M1270 ${cy + 26}L1248 ${cy - 20}Q1270 ${cy - 30} 1292 ${cy - 20}Z`,
        `M1262 ${cy - 8}h1M1277 ${cy - 4}h1M1269 ${cy + 8}h1`,
      ]);
      icon({ b: 9, at: 2.2, x: 10 }, [
        `M1350 ${cy - 6}A24 20 0 0 1 1398 ${cy - 6}Z`,
        `M1348 ${cy + 2}H1400`,
        `M1350 ${cy + 10}H1398Q1398 ${cy + 20} 1388 ${cy + 20}H1360Q1350 ${cy + 20} 1350 ${cy + 10}Z`,
      ]);
      mk(1052, 452, { b: 9, at: 0 });

      // 10. She sits down to search, and the box types what she asks for.
      k.rect(BOX[0], BOX[1], 320, 64, { b: 10, at: 0.9, dur: 0.4, x });
      k.circ(BOX[0] + 36, BOX[1] + 30, 10, { b: 10, at: 1.1, dur: 0.2, x });
      k.line(BOX[0] + 43, BOX[1] + 37, BOX[0] + 52, BOX[1] + 46, { b: 10, at: 1.2, dur: 0.15, x });
      k.raw(
        `<g ${attrs({ b: 10, at: 1.4, dur: 0.08, x }, "dots")}>` +
          [..."quick dinner"]
            .map((ch, i) => `<text class="cd" x="${r(BOX[0] + 68 + i * 16.8)}" y="${BOX[1] + 42}">${ch === " " ? "&#160;" : ch}</text>`)
            .join("") +
          `</g>`,
      );
      mk(BOX[0] - 16, BOX[1] + 32, { b: 10, at: 0.9 });

      // 11. Without types. Each page gives its time as a bare number, and the smallest is 3.
      k.path(`M${BOX[0] + 320} ${BOX[1] + 32}H620Q${NODE[0]} ${BOX[1] + 32} ${NODE[0]} ${NODE[1] + 60}V${NODE[1] + 16}`, {
        b: 11,
        at: 0.2,
        dur: 0.6,
        x,
      });
      k.sq(NODE[0], NODE[1], { b: 11, at: 0.8, size: 28, x });
      k.text(NODE[0] - 26, NODE[1] + 9, "Recipe", { b: 11, at: 0.85, x, c: "cd", anchor: "end" });
      recipes.forEach(([name, bare, typed], i) => {
        const y = ROWS[i];
        const keep = i === 1 ? x : 13;
        const at = 1.0 + i * 0.12;
        k.line(NODE[0] + 16, NODE[1], 848, y, { b: 11, at, dur: 0.3, x: keep });
        k.sq(860, y, { b: 11, at: at + 0.25, x: keep });
        k.text(884, y + 10, name, { b: 11, at: at + 0.3, x: keep, c: "t1s" });
        k.line(1098, y, 1346, y, { b: 11, at: at + 0.5, dur: 0.3, hair: true, x: 12 });
        k.text(1360, y + 9, bare, { b: 11, at: at + 0.75, x: 12, c: "cd" });

        // 12. With types. The same numbers, each now a duration under one shared property.
        k.line(1098, y, 1128, y, { b: 12, at: 0.25, dur: 0.15, hair: true, x: keep });
        k.text(1140, y + 9, "prepTime", { b: 12, at: 0.3 + i * 0.08, x: keep, c: "m2" });
        k.line(1296, y, 1346, y, { b: 12, at: 0.45, dur: 0.15, hair: true, x: keep });
        k.text(1360, y + 9, typed, { b: 12, at: 0.55 + i * 0.08, x: keep, c: "cd", overlap: true });
        if (i !== 1) k.line(1352, y, 1368 + typed.length * 16.8, y, { b: 12, at: 1.8, dur: 0.2, x: keep });
      });
      k.text(1400, ROWS[0] + 9, "hours? minutes?", { b: 11, at: 2.3, x: 12, c: "m2" });
      mk(860, ROWS[0], {
        b: 11,
        at: 0.2,
        dur: 1.7,
        via: [
          [BOX[0] + 320, BOX[1] + 32],
          [620, BOX[1] + 32],
          [NODE[0], NODE[1] + 60],
          [NODE[0], NODE[1]],
        ],
      });
      guess(12, 1.0, x, [BOX[0] + 110, BOX[1] + 68], "under 30 min");
      mk(860, ROWS[1], { b: 12, at: 1.6, dur: 0.5 });

      // 13. The other recipes drop away, the rating is read the same way, and the answer arrives.
      k.path(`M872 ${ROWS[1] + 12}V${ROWS[1] + 50}H1128`, { b: 13, at: 0.3, dur: 0.35, hair: true, x });
      k.text(1140, ROWS[1] + 59, "ratingValue", { b: 13, at: 0.55, x, c: "m2" });
      k.text(1360, ROWS[1] + 59, "4.5", { b: 13, at: 0.7, x, c: "cd" });
      k.rect(1490, 500, 310, 200, { b: 13, at: 1.0, dur: 0.5, x });
      k.text(1514, 548, "SEARCH RESULT", { b: 13, at: 1.3, x, c: "m2" });
      k.text(1514, 602, "Lentil curry", { b: 13, at: 1.4, x, c: "t1s" });
      k.raw(`<path class="f" d="${star(1546, 652, 16)}" ${attrs({ b: 13, at: 1.6, x }, "snap")}/>`);
      k.text(1570, 664, "4.5", { b: 13, at: 1.65, x, c: "t1s" });
      k.text(1660, 664, "20 min", { b: 13, at: 1.8, x, c: "t1s" });
      mk(1514, 652, { b: 13, at: 0.35, dur: 0.6 });
    }

    // 14 to 17. Tom asks for Mercury. There are three. Each has its own ID and typed facts,
    // and only one of them is something you can play.
    {
      const x = 18;
      const things = [
        ["Q308", "instance of", "planet"],
        ["Q925", "instance of", "chemical element"],
        ["Q15869", "occupation", "singer"],
      ];
      const FORK = [790, 600];

      // 14. Tom, centred, asking.
      k.raw(`<g data-shift-b="15" data-shift-x="${DESK[0] - HOME[0]}" data-shift-y="0">`);
      person(k, HOME[0], HOME[1], 1.3, "short", {
        b: 14,
        at: 0.35,
        x,
        top: "tie",
        faces: [
          { face: { brows: "cocked", mouth: "smirk" } },
          { b: 15, at: 2.2, face: { brows: "uneven", mouth: "flat" } },
          { b: 16, at: 2.1, face: { brows: "cocked", mouth: "smirk" } },
          { b: 17, at: 1.5, face: { brows: "raised", mouth: "side" } },
        ],
        gaze: [
          { b: 14, to: [1300, 380] },
          { b: 15, to: FORK, pos: DESK, t: 1.0 },
          { b: 16, to: [1330, ROWS[2]], pos: DESK, t: 1.2 },
          { b: 17, to: [1560, 600], pos: DESK, t: 0.9 },
        ],
      });
      k.text(HOME[0], HOME[1] + 214, "Tom", { b: 14, at: 0.7, x, c: "t1s", anchor: "middle" });
      k.path(
        `M1058 330H1342a18 18 0 0 1 18 18V388a18 18 0 0 1-18 18H1112L1032 450L1080 406H1058a18 18 0 0 1-18-18V348a18 18 0 0 1 18-18Z`,
        { b: 14, at: 0.9, dur: 0.6, x },
      );
      k.text(1090, 380, "Play Mercury", { b: 14, at: 1.4, x, c: "t1s" });
      k.raw(`</g>`);
      mk(1066, 369, { b: 14, at: 0 });

      // 15. He steps aside. One word, three things.
      mk(1066 + DESK[0] - HOME[0], 369, { b: 15, at: 0, dur: 0.9 });
      k.text(620, 614, "Mercury", { b: 15, at: 1.0, x, c: "t1" });
      k.text(620, 664, "which one?", { b: 15, at: 2.3, x: 16, c: "m2" });
      things.forEach(([id, prop, value], i) => {
        const y = ROWS[i];
        const keep = i === 2 ? x : 17;
        k.line(FORK[0], FORK[1], 868, y, { b: 15, at: 1.3 + i * 0.12, dur: 0.4, dash: true, x: keep });

        // 16. Each one has its own identifier and says what it is.
        k.text(940, y + 9, id, { b: 16, at: 0.25 + i * 0.12, x: keep, c: "cd" });
        k.line(1056, y, 1086, y, { b: 16, at: 0.4 + i * 0.12, dur: 0.15, hair: true, x: keep });
        k.text(1098, y + 9, prop, { b: 16, at: 0.45 + i * 0.12, x: keep, c: "m2" });
        k.line(1304, y, 1334, y, { b: 16, at: 0.6 + i * 0.12, dur: 0.15, hair: true, x: keep });
        k.text(1348, y + 9, value, { b: 16, at: 0.65 + i * 0.12, x: keep, c: "cd" });
        if (i !== 2) k.line(1340, y, 1356 + value.length * 16.8, y, { b: 16, at: 2.0, dur: 0.2, x: keep });
      });
      k.circ(900, ROWS[0], 18, { b: 15, at: 1.75, dur: 0.25, x: 17 });
      k.raw(
        `<ellipse class="s" cx="900" cy="${ROWS[0]}" rx="30" ry="8" transform="rotate(-20 900 ${ROWS[0]})" ${attrs({ b: 15, at: 1.85, x: 17 }, "snap")}/>`,
      );
      k.sq(900, ROWS[1], { b: 15, at: 1.9, size: 44, x: 17 });
      k.text(900, ROWS[1] + 10, "Hg", { b: 15, at: 1.95, x: 17, c: "cd", anchor: "middle" });
      k.raw(`<circle class="f" cx="893" cy="${ROWS[2] + 12}" r="9" ${attrs({ b: 15, at: 2.05, x }, "pop")}/>`);
      k.path(`M901.5 ${ROWS[2] + 12}V${ROWS[2] - 24}q16 4 16 20`, { b: 15, at: 2.08, dur: 0.2, x });

      // What "play" asks for is the assistant's reading. The facts decide which Mercury fits it.
      guess(16, 1.1, x, [492, 410], "needs a musician", 580);
      k.line(FORK[0], FORK[1], 868, ROWS[2], { b: 16, at: 1.6, dur: 0.4, x });
      mk(868, ROWS[2], { b: 16, at: 1.2, dur: 0.9, via: [FORK] });

      // 17. The other two drop away and the music starts.
      k.rect(1490, 500, 310, 200, { b: 17, at: 0.6, dur: 0.5, x });
      k.text(1514, 548, "NOW PLAYING", { b: 17, at: 0.9, x, c: "m2" });
      k.text(1514, 602, "Freddie Mercury", { b: 17, at: 1.0, x, c: "t1s" });
      [0, 1, 2, 3, 4, 5, 6].forEach((n) => {
        const h = [14, 30, 20, 38, 24, 34, 12][n];
        k.line(1548 + n * 16, 672, 1548 + n * 16, 672 - h, { b: 17, at: 1.3 + n * 0.05, dur: 0.2, x });
      });
      mk(1514, 656, { b: 17, at: 0.6, dur: 0.6 });
    }

    // 18 to 21. Sam has a heart attack. Three clinicians write it three ways, one concept ID
    // counts it once, and that concept's parents put him on the heart clinic's list.
    {
      const notes = [
        ["GP", "heart attack"],
        ["EMERGENCY", "MI"],
        ["CARDIOLOGY", "myocardial infarction"],
      ];
      const CONCEPT = [1262, 600];

      // 18. Sam, centred, unwell.
      k.raw(`<g data-shift-b="19" data-shift-x="${DESK[0] - HOME[0]}" data-shift-y="0">`);
      person(k, HOME[0], HOME[1], 1.3, "older", {
        b: 18,
        at: 0.35,
        faces: [
          { face: { brows: "worried", mouth: "flat" } },
          { b: 20, at: 1.2, face: { brows: "level", mouth: "flat" } },
          { b: 21, at: 2.3, face: { brows: "level", mouth: "smile" } },
        ],
        gaze: [
          { b: 18, to: [1190, 470] },
          { b: 19, to: [1196, 600], pos: DESK, t: 1.6 },
          { b: 21, to: [1262, 340], pos: DESK, t: 1.0 },
        ],
      });
      k.text(HOME[0], HOME[1] + 214, "Sam", { b: 18, at: 0.7, c: "t1s", anchor: "middle" });
      k.text(HOME[0], HOME[1] + 254, "one patient", { b: 18, at: 0.8, c: "m2", anchor: "middle" });
      k.raw(`</g>`);
      icon({ b: 18, at: 1.2, x: 19 }, [
        `M1190 508C1124 458 1150 404 1190 438C1230 404 1256 458 1190 508Z`,
        `M1150 466h18l8 -16l12 32l8 -16h24`,
      ]);
      icon({ b: 18, at: 1.6, x: 19 }, [`M1128 420l-12 -8`, `M1252 420l12 -8`, `M1118 462h-14`, `M1262 462h14`]);
      mk(1190, 530, { b: 18, at: 0 });

      // 19. He steps aside. Three notes, three wordings, and a system that matches text sees three conditions.
      notes.forEach(([who, term], i) => {
        const y = ROWS[i];
        const at = 0.9 + i * 0.18;
        k.line(450, 600, 560, y, { b: 19, at, dur: 0.3, hair: true });
        k.rect(560, y - 56, 440, 112, { b: 19, at: at + 0.15, dur: 0.45 });
        k.text(584, y - 12, who, { b: 19, at: at + 0.4, c: "m2" });
        k.text(584, y + 32, term, { b: 19, at: at + 0.5, c: "t1s" });
        k.line(1000, y, 1176, y, { b: 19, at: 1.8 + i * 0.1, dur: 0.3, dash: true, x: 20 });
        k.sq(1196, y, { b: 19, at: 2.1 + i * 0.1, size: 22, x: 20 });
      });
      k.text(1260, 596, "3 conditions?", { b: 19, at: 2.3, x: 20, c: "t1" });
      k.text(1260, 646, "COUNTED THREE TIMES", { b: 19, at: 2.4, x: 20, c: "m2" });
      mk(1196, ROWS[1], { b: 19, at: 1.9 });

      // 20. Every wording is a synonym of one concept.
      k.path(`M1000 ${ROWS[0]}C1130 ${ROWS[0]} 1110 ${CONCEPT[1]} 1240 ${CONCEPT[1]}`, { b: 20, at: 0.35, dur: 0.5 });
      k.line(1000, CONCEPT[1], 1240, CONCEPT[1], { b: 20, at: 0.45, dur: 0.4 });
      k.path(`M1000 ${ROWS[2]}C1130 ${ROWS[2]} 1110 ${CONCEPT[1]} 1240 ${CONCEPT[1]}`, { b: 20, at: 0.55, dur: 0.5 });
      k.sq(CONCEPT[0], CONCEPT[1], { b: 20, at: 1.05, size: 34 });
      k.text(1300, 612, "22298006", { b: 20, at: 1.2, c: "t1", overlap: true });
      k.text(1300, 658, "ONE CONCEPT, COUNTED ONCE", { b: 20, at: 1.35, c: "m2", overlap: true });
      mk(CONCEPT[0], CONCEPT[1], { b: 20, at: 0.6, dur: 0.5 });

      // 21. The concept has parents. The clinic asks for heart disease and finds Sam, though
      // none of his notes says so. The upper link stands for more than one step, so it is broken.
      k.line(CONCEPT[0], 583, CONCEPT[0], 488, { b: 21, at: 0.2, dur: 0.3 });
      k.text(1284, 546, "is a", { b: 21, at: 0.35, c: "m2" });
      k.sq(CONCEPT[0], 474, { b: 21, at: 0.5, size: 22 });
      k.text(1296, 484, "Ischemic heart disease", { b: 21, at: 0.55, c: "t1s" });
      k.line(CONCEPT[0], 460, CONCEPT[0], 428, { b: 21, at: 0.7, dur: 0.15 });
      [418, 408, 398].forEach((y) =>
        k.raw(`<circle class="f" cx="${CONCEPT[0]}" cy="${y}" r="1.8" ${attrs({ b: 21, at: 0.8 }, "pop")}/>`),
      );
      k.line(CONCEPT[0], 388, CONCEPT[0], 356, { b: 21, at: 0.85, dur: 0.15 });
      k.text(1284, 416, "is a", { b: 21, at: 0.9, c: "m2" });
      k.sq(CONCEPT[0], 342, { b: 21, at: 1.0, size: 22 });
      k.text(1296, 352, "Heart disease", { b: 21, at: 1.05, c: "t1s" });
      k.line(1528, 342, 1552, 342, { b: 21, at: 1.3, dur: 0.15, hair: true });
      k.rect(1560, 290, 250, 108, { b: 21, at: 1.3, dur: 0.4 });
      k.text(1580, 330, "CLINIC LIST", { b: 21, at: 1.6, c: "m2" });
      k.text(1610, 376, "Sam", { b: 21, at: 2.3, c: "t1s" });
      k.path(`M1690 364l8 9l16 -20`, { b: 21, at: 2.45, dur: 0.2 });
      mk(1590, 366, {
        b: 21,
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
