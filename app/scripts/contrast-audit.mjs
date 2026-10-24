#!/usr/bin/env node
/**
 * Contrast and color-vision audit for src/constants/theme.ts.
 *
 *   node scripts/contrast-audit.mjs           # table, exits 1 on any failure
 *   node scripts/contrast-audit.mjs --md      # Markdown tables for ACCESSIBILITY.md
 *
 * 1. WCAG 2.2 contrast (1.4.3 text 4.5:1, 1.4.11 UI parts 3:1) for every
 *    token pair the UI draws, in all three themes.
 * 2. Overlays on the live camera (caption pill, profile button, window
 *    frame, info card, dock) are checked against the worst cases, a pure
 *    white and a pure black scene: at least one of their edges must pass.
 * 3. Color-vision deficiency: status and alert colors are simulated for
 *    protanopia, deuteranopia, tritanopia (Machado et al. 2009, severity 1)
 *    and achromatopsia, and the CIE76 color difference is reported. Colors
 *    that merge are allowed only because every status also has its own icon
 *    and words (WCAG 1.4.1); the report flags them so that stays true.
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const md = process.argv.includes('--md');
const src = readFileSync(fileURLToPath(new URL('../src/constants/theme.ts', import.meta.url)), 'utf8');

// --- parse the Palettes object (flat `key: '#RRGGBB'` lines per theme) ---
const themes = {};
const block = src.slice(src.indexOf('export const Palettes'), src.indexOf('/** Sizes at 100%'));
let current = null;
for (const line of block.split('\n')) {
  const t = line.match(/^ {2}(\w+): \{/);
  if (t) current = themes[t[1]] = {};
  const kv = line.match(/^ {4}(\w+): '(#[0-9A-Fa-f]{6})'/);
  if (current && kv) current[kv[1]] = kv[2].toUpperCase();
}

// --- WCAG relative luminance and contrast ---
const rgb = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16) / 255);
const lin = (c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
const lum = (h) => {
  const [r, g, b] = rgb(h).map(lin);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
};
const cr = (a, b) => {
  const [x, y] = [lum(a), lum(b)].sort((m, n) => n - m);
  return (x + 0.05) / (y + 0.05);
};
const WHITE = '#FFFFFF';
const BLACK = '#000000';

// --- checks ---
const pairs = (p) => [
  ['Body text on background', cr(p.text, p.bg), 4.5],
  ['Body text on card', cr(p.text, p.surface), 4.5],
  ['Secondary text on card', cr(p.textMuted, p.surface), 4.5],
  ['Secondary text on background', cr(p.textMuted, p.bg), 4.5],
  ['Control border on card', cr(p.border, p.surface), 3],
  ['Primary button label', cr(p.onPrimary, p.primary), 4.5],
  ['Primary button vs card', Math.max(cr(p.primary, p.surface), cr(p.border, p.surface)), 3],
  ['Mint button label', cr(p.onAccent, p.accent), 4.5],
  ['Mint button edge vs card (fill or text-color border)', Math.max(cr(p.accent, p.surface), cr(p.text, p.surface)), 3],
  ['Dock text, light end', cr(p.onDock, p.dockTop), 4.5],
  ['Dock text, dark end', cr(p.onDock, p.dockBottom), 4.5],
  ['Talk button vs dock, top', Math.max(cr(p.talkTop, p.dockTop), cr(p.talkRing, p.dockTop)), 3],
  ['Talk button vs dock, bottom', Math.max(cr(p.talkBottom, p.dockBottom), cr(p.talkRing, p.dockBottom)), 3],
  ['Talk icon and label, light end', cr(p.onTalk, p.talkTop), 4.5],
  ['Talk icon and label, dark end', cr(p.onTalk, p.talkBottom), 4.5],
  ['Dock edge vs white scene', Math.max(cr(p.dockEdge, WHITE), cr(p.dockTop, WHITE)), 3],
  ['Dock edge vs black scene', Math.max(cr(p.dockEdge, BLACK), cr(p.dockTop, BLACK)), 3],
  ['Caption pill text', cr(p.onPill, p.pill), 4.5],
  ['Caption pill vs white scene', Math.max(cr(p.pill, WHITE), cr(p.pillBorder, WHITE)), 3],
  ['Caption pill vs black scene', Math.max(cr(p.pill, BLACK), cr(p.pillBorder, BLACK)), 3],
  ['Profile initial', cr(p.onProfile, p.profileBg), 4.5],
  ['Profile button vs white scene', Math.max(cr(p.profileBg, WHITE), cr(p.profileRing, WHITE)), 3],
  ['Profile button vs black scene', Math.max(cr(p.profileBg, BLACK), cr(p.profileRing, BLACK)), 3],
  ['Window frame vs white scene', Math.max(cr(p.frameOuter, WHITE), cr(p.frameInner, WHITE)), 3],
  ['Window frame vs black scene', Math.max(cr(p.frameOuter, BLACK), cr(p.frameInner, BLACK)), 3],
  ['Window frame (warning) vs either scene', Math.min(Math.max(cr(p.frameOuter, WHITE), cr(p.warningEdge, WHITE)), Math.max(cr(p.frameOuter, BLACK), cr(p.warningEdge, BLACK))), 3],
  ['Window frame (danger) vs either scene', Math.min(Math.max(cr(p.frameOuter, WHITE), cr(p.dangerEdge, WHITE)), Math.max(cr(p.frameOuter, BLACK), cr(p.dangerEdge, BLACK))), 3],
  ['Info card vs white scene', Math.max(cr(p.surface, WHITE), cr(p.cardEdge, WHITE)), 3],
  ['Info card vs black scene', Math.max(cr(p.surface, BLACK), cr(p.cardEdge, BLACK)), 3],
  ['HSA eligible label', cr(p.eligible, p.eligibleBg), 4.5],
  ['Not HSA eligible label', cr(p.notEligible, p.notEligibleBg), 4.5],
  ['Could not confirm label', cr(p.unconfirmed, p.unconfirmedBg), 4.5],
  ['Red alert title', cr(p.danger, p.dangerBg), 4.5],
  ['Red alert body text', cr(p.text, p.dangerBg), 4.5],
  ['Red alert edge vs card', cr(p.dangerEdge, p.surface), 3],
  ['Orange alert title', cr(p.warning, p.warningBg), 4.5],
  ['Orange alert body text', cr(p.text, p.warningBg), 4.5],
  ['Orange alert edge vs card', cr(p.warningEdge, p.surface), 3],
  ['Selected option border vs card', cr(p.primary, p.surface), 3],
];

// --- color-vision simulation (Machado 2009, severity 1.0, linear RGB) ---
const CVD = {
  protanopia: [[0.152286, 1.052583, -0.204868], [0.114503, 0.786281, 0.099216], [-0.003882, -0.048116, 1.051998]],
  deuteranopia: [[0.367322, 0.860646, -0.227968], [0.280085, 0.672501, 0.047413], [-0.01182, 0.04294, 0.968881]],
  tritanopia: [[1.255528, -0.076749, -0.178779], [-0.078411, 0.930809, 0.147602], [0.004733, 0.691367, 0.3039]],
};
const simulate = (hex, kind) => {
  const c = rgb(hex).map(lin);
  if (kind === 'achromatopsia') {
    const y = 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
    return [y, y, y];
  }
  return CVD[kind].map((row) => Math.min(1, Math.max(0, row[0] * c[0] + row[1] * c[1] + row[2] * c[2])));
};
const lab = (linRgb) => {
  const [r, g, b] = linRgb;
  const X = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047;
  const Y = 0.2126 * r + 0.7152 * g + 0.0722 * b;
  const Z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883;
  const f = (t) => (t > 216 / 24389 ? Math.cbrt(t) : (24389 / 27 * t + 16) / 116);
  return [116 * f(Y) - 16, 500 * (f(X) - f(Y)), 200 * (f(Y) - f(Z))];
};
const dE = (a, b) => Math.hypot(...a.map((v, i) => v - b[i]));
const statusPairs = (p) => [
  ['Eligible vs not eligible', p.eligible, p.notEligible],
  ['Eligible vs could not confirm', p.eligible, p.unconfirmed],
  ['Not eligible vs could not confirm', p.notEligible, p.unconfirmed],
  ['Red alert vs orange alert', p.dangerEdge, p.warningEdge],
];
const KINDS = ['normal', 'protanopia', 'deuteranopia', 'tritanopia', 'achromatopsia'];
const MERGE = 15; // CIE76 ΔE below this reads as "about the same color"

// --- report ---
let failures = 0;
const names = Object.keys(themes);
const rows = pairs(themes[names[0]]).map(([label, , need], i) => {
  const vals = names.map((n) => pairs(themes[n])[i][1]);
  vals.forEach((v) => v < need && failures++);
  return [label, vals, need];
});

if (md) {
  console.log(`| Element | ${names.join(' | ')} | Needs |\n|---|${names.map(() => '---').join('|')}|---|`);
  for (const [label, vals, need] of rows) {
    console.log(`| ${label} | ${vals.map((v) => `${v.toFixed(2)}${v < need ? ' FAIL' : ''}`).join(' | ')} | ${need}:1 |`);
  }
  console.log(`\n| Status colors (ΔE, standard theme) | ${KINDS.join(' | ')} |\n|---|${KINDS.map(() => '---').join('|')}|`);
  for (const [label, a, b] of statusPairs(themes.standard)) {
    const d = KINDS.map((k) => dE(lab(k === 'normal' ? rgb(a).map(lin) : simulate(a, k)), lab(k === 'normal' ? rgb(b).map(lin) : simulate(b, k))));
    console.log(`| ${label} | ${d.map((v) => `${v.toFixed(0)}${v < MERGE ? ' (merges)' : ''}`).join(' | ')} |`);
  }
} else {
  for (const [label, vals, need] of rows) {
    const cells = vals.map((v) => `${v.toFixed(2).padStart(6)}${v < need ? ' FAIL' : '     '}`).join(' ');
    console.log(`${label.padEnd(54)} ${cells}  (>= ${need})`);
  }
  console.log(`\nColor-vision ΔE (standard theme; under ${MERGE} merges, icons and words carry the meaning):`);
  for (const [label, a, b] of statusPairs(themes.standard)) {
    const d = KINDS.map((k) => dE(lab(k === 'normal' ? rgb(a).map(lin) : simulate(a, k)), lab(k === 'normal' ? rgb(b).map(lin) : simulate(b, k))));
    console.log(`  ${label.padEnd(36)} ${KINDS.map((k, i) => `${k} ${d[i].toFixed(0)}`).join(', ')}`);
  }
  console.log(`\n${failures === 0 ? 'PASS' : `FAIL: ${failures} pair(s) below WCAG 2.2 AA`} (themes: ${names.join(', ')})`);
}
process.exit(failures ? 1 : 0);
