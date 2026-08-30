const fs = require('fs');
const { Resvg } = require('@resvg/resvg-js');

const C = 256;
const outerR = 240;
const innerR = 178;
const gap = 7;               // degrees of gap between segments
const half = (90 - gap) / 2; // half angular width of each drawn segment

const P = (angDeg, r) => {
  const a = (angDeg * Math.PI) / 180;
  return [C + r * Math.cos(a), C + r * Math.sin(a)];
};
const f = (n) => n.toFixed(2);

// annulus sector, clockwise (SVG y-down)
function seg(centerAng, fill) {
  const a0 = centerAng - half;
  const a1 = centerAng + half;
  const [ox0, oy0] = P(a0, outerR);
  const [ox1, oy1] = P(a1, outerR);
  const [ix1, iy1] = P(a1, innerR);
  const [ix0, iy0] = P(a0, innerR);
  return `<path fill="${fill}" d="M${f(ox0)},${f(oy0)} A${outerR},${outerR} 0 0 1 ${f(ox1)},${f(oy1)} L${f(ix1)},${f(iy1)} A${innerR},${innerR} 0 0 0 ${f(ix0)},${f(iy0)} Z"/>`;
}

const segments = [
  seg(-90, '#1b2a63'), // Noc  – deep indigo
  seg(0,   '#2f6fb3'), // Ráno/Večer – blue
  seg(90,  '#33b0c6'), // Dopoludnie – cyan
  seg(180, '#f5a11c'), // Popoludnie – amber
].join('\n    ');

// lightning bolt (amber) – centred, energetic diagonal
const bolt = '286,150 198,278 250,278 226,386 330,250 276,250 314,150';

const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
  <defs>
    <radialGradient id="disc" cx="42%" cy="38%" r="72%">
      <stop offset="0" stop-color="#183a68"/>
      <stop offset="1" stop-color="#0b1f3d"/>
    </radialGradient>
  </defs>
  <g>
    ${segments}
    <circle cx="256" cy="256" r="168" fill="url(#disc)"/>
    <path d="M168,340 L168,172 L256,286 L344,172 L344,340"
          fill="none" stroke="#ffffff" stroke-width="46"
          stroke-linecap="round" stroke-linejoin="round"/>
    <polygon points="${bolt}" fill="#f5a11c"
             stroke="#0b1f3d" stroke-width="10" stroke-linejoin="round"/>
  </g>
</svg>
`;

fs.writeFileSync('icon.svg', svg);

for (const size of [256, 512]) {
  const r = new Resvg(svg, { fitTo: { mode: 'width', value: size } });
  const png = r.render().asPng();
  const name = size === 512 ? 'icon@2x.png' : 'icon.png';
  fs.writeFileSync(name, png);
  console.log(`wrote ${name} (${size}x${size}, ${png.length} bytes)`);
}
console.log('wrote icon.svg');
