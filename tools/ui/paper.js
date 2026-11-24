/* Torn-paper outlines of the dialogue cards (SVG clip paths). */
/* torn-paper outlines: gently wavy edges, no sharp corners (smooth curves through a few slightly shifted points) */
(function () {
  let seed = 11;
  const rnd = () => (seed = seed * 16807 % 2147483647) / 2147483647;
  const mk = () => {
    const P = [];
    for (let i = 0; i <= 6; i++)
      P.push([
        0.03 + 0.94 * i / 6,
        0.012 + 0.028 * rnd()
      ]);
    for (let j = 0; j <= 4; j++)
      P.push([
        0.992 - 0.011 * rnd(),
        0.1 + 0.8 * j / 4
      ]);
    for (let i = 0; i <= 6; i++)
      P.push([
        0.97 - 0.94 * i / 6,
        0.988 - 0.028 * rnd()
      ]);
    for (let j = 0; j <= 4; j++)
      P.push([
        0.008 + 0.011 * rnd(),
        0.9 - 0.8 * j / 4
      ]);
    const n = P.length, f = v => v.toFixed(4);
    let d = 'M' + f(P[0][0]) + ' ' + f(P[0][1]);
    for (let i = 0; i < n; i++) {
      const a = P[(i - 1 + n) % n], b = P[i], c = P[(i + 1) % n], e = P[(i + 2) % n];
      d += ' C' + f(b[0] + (c[0] - a[0]) / 6) + ' ' + f(b[1] + (c[1] - a[1]) / 6) + ' ' + f(c[0] - (e[0] - b[0]) / 6) + ' ' + f(c[1] - (e[1] - b[1]) / 6) + ' ' + f(c[0]) + ' ' + f(c[1]);
    }
    return d + ' Z';
  };
  document.body.insertAdjacentHTML('beforeend', '<svg width="0" height="0" style="position:absolute"><defs>' + [
    0,
    1,
    2
  ].map(i => `<clipPath id="paper${ i }" clipPathUnits="objectBoundingBox"><path d="${ mk() }"/></clipPath>`).join('') + '</defs></svg>');
}());
