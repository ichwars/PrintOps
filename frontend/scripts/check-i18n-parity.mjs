// Verifies parity across all discovered locale files:
//   1. Leaf-key sets are identical (string-array entries use numeric paths)
//   2. Each leaf's {{placeholder}} set is identical
//   3. Plural suffixes: every en key ending in _plural / _one / _other must
//      exist in every other locale, and other locales must not introduce an
//      _one key that en does not have.
//   4. NEW: leaves in a non-English locale must not be identical to en, unless
//      the value is a brand name / technical token / pure punctuation, OR the
//      key+locale pair is explicitly listed in IDENTICAL_TO_EN_ALLOWED below.
//      Catches the "copy English text into non-English locale to satisfy the
//      key-count parity gate" anti-pattern that accumulated 700+ shipped
//      strings of debt before the gate was tightened. Add an explicit entry
//      ONLY when the string is a real word/term in that target locale.
// Malformed input (missing `export default`, parse errors, non-string leaves,
// unsupported property kinds) fails loudly instead of silently passing the gate.
// Exits 1 with a diagnostic report on any failure, else exits 0.

import fs from 'node:fs';
import path from 'node:path';
import url from 'node:url';

const scriptDir = path.dirname(url.fileURLToPath(import.meta.url));
const frontendDir = path.resolve(scriptDir, '..');
const localesDir = path.join(frontendDir, 'src/i18n/locales');
const tsPath = path.join(frontendDir, 'node_modules/typescript/lib/typescript.js');

const tsModule = await import(url.pathToFileURL(tsPath).href);
const ts = tsModule.default ?? tsModule;

function collectLeaves(node, prefix, leaves) {
  if (!ts.isObjectLiteralExpression(node)) return;
  leaves.containerTypes?.set(prefix, 'object');
  for (const prop of node.properties) {
    if (!ts.isPropertyAssignment(prop)) {
      console.error(
        `Unsupported property kind ${ts.SyntaxKind[prop.kind]} at "${prefix}" ` +
        `(locale files must use plain \`key: value\` assignments — no spread, shorthand, methods, or accessors).`,
      );
      process.exit(1);
    }
    let name;
    if (ts.isIdentifier(prop.name)) name = prop.name.text;
    else if (ts.isStringLiteral(prop.name) || ts.isNoSubstitutionTemplateLiteral(prop.name)) name = prop.name.text;
    else if (ts.isComputedPropertyName(prop.name)) {
      console.error(`ComputedPropertyName not allowed in locale file at path "${prefix}"`);
      process.exit(1);
    } else {
      console.error(`Unsupported property-name kind ${ts.SyntaxKind[prop.name.kind]} at "${prefix}"`);
      process.exit(1);
    }
    const p = prefix ? `${prefix}.${name}` : name;
    if (ts.isObjectLiteralExpression(prop.initializer)) {
      collectLeaves(prop.initializer, p, leaves);
    } else if (ts.isArrayLiteralExpression(prop.initializer)) {
      // Runtime table dictionaries use ordered column-label arrays. Inspect
      // every entry with the same strict string and placeholder checks.
      leaves.containerTypes?.set(p, 'array');
      prop.initializer.elements.forEach((element, index) => {
        const key = `${p}.${index}`;
        leaves.set(key, extractStringValue(element, key));
      });
    } else {
      const value = extractStringValue(prop.initializer, p);
      leaves.set(p, value);
    }
  }
}

function extractStringValue(node, keyPath) {
  if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) return node.text;
  if (ts.isTemplateExpression(node)) {
    let out = node.head.text;
    for (const span of node.templateSpans) {
      out += '${' + span.expression.getText() + '}';
      out += span.literal.text;
    }
    return out;
  }
  console.error(
    `Non-string leaf at "${keyPath}" (kind=${ts.SyntaxKind[node.kind]}): ${node.getText()}\n` +
    `Locale files must only contain string or template literals as leaf values.`,
  );
  process.exit(1);
}

function loadLocale(filePath) {
  const src = fs.readFileSync(filePath, 'utf8');
  const sf = ts.createSourceFile(filePath, src, ts.ScriptTarget.Latest, true);
  if (sf.parseDiagnostics && sf.parseDiagnostics.length > 0) {
    console.error(`${filePath}: ${sf.parseDiagnostics.length} parse error(s):`);
    for (const d of sf.parseDiagnostics.slice(0, 10)) {
      const msg = typeof d.messageText === 'string' ? d.messageText : d.messageText.messageText;
      const { line, character } = sf.getLineAndCharacterOfPosition(d.start ?? 0);
      console.error(`  ${line + 1}:${character + 1} ${msg}`);
    }
    process.exit(1);
  }
  const leaves = new Map();
  leaves.containerTypes = new Map();
  let foundExport = false;
  ts.forEachChild(sf, (n) => {
    if (ts.isExportAssignment(n)) {
      foundExport = true;
      collectLeaves(n.expression, '', leaves);
    }
  });
  if (!foundExport) {
    console.error(`${filePath}: no \`export default\` found — locale files must use \`export default { ... }\`.`);
    process.exit(1);
  }
  if (leaves.size === 0) {
    console.error(`${filePath}: \`export default\` resolved to zero leaves — file is empty or not a nested object.`);
    process.exit(1);
  }
  return leaves;
}

const placeholderRe = /\{\{[^{}]+\}\}/g;

// Exact exceptions are static reviewable data, independent of runtime catalogs.
// Dutch and German do not inherit the older-locale English fallback list.
const parityData = JSON.parse(fs.readFileSync(path.join(scriptDir, 'i18n-parity-data.json'), 'utf8'));

function exactValueSet(values, name) {
  if (!Array.isArray(values) || values.some((value) => typeof value !== 'string')) {
    throw new Error(`Invalid exact parity data: ${name} must be an array of strings.`);
  }
  return new Set(values);
}

const ORDER_MANAGEMENT_ENGLISH_FALLBACK_LOCALES = exactValueSet(
  parityData.orderManagementEnglishFallbackLocales, 'orderManagementEnglishFallbackLocales',
);
const PRINTER_CONTROL_ENGLISH_FALLBACK_KEYS = exactValueSet(
  parityData.printerControlEnglishFallbackKeys, 'printerControlEnglishFallbackKeys',
);
const ORDER_MANAGEMENT_ENGLISH_FALLBACK_KEYS = exactValueSet(
  parityData.orderManagementEnglishFallbackKeys, 'orderManagementEnglishFallbackKeys',
);

// Task 16 deliberately provides the complete English layout-editor fallback
// outside German. The exception is constrained to the new namespace and its
// two navigation leaves; unrelated copied English strings still fail.
function isAllowedOrderManagementEnglishFallback(locale, key) {
  // This message was already unconditionally English in the German business
  // number-sequence UI. Preserve that exact legacy display; it is not claimed
  // as a German translation. The Dutch resource is translated and checked.
  if (locale === 'de' && key === 'orders.runtimeDevice.business.noProfileSelected') return true;
  // These rows previously displayed the raw backend status code in German.
  // Preserve those exact displays; Dutch has translated labels for each code.
  const legacyGermanStatusCodes = new Set([
    'orders.runtimeDomain.orderStatus.active',
    'orders.runtimeDomain.orderStatus.cancelled',
    'orders.runtimeDomain.orderStatus.completed',
    'orders.runtimeDomain.reservationStatus.active',
    'orders.runtimeDomain.reservationStatus.released',
    'orders.runtimeDomain.reservationStatus.cancelled',
    'orders.runtimeDomain.reservationStatus.consumed',
    'orders.runtimeDomain.reservationStatus.completed',
  ]);
  if (locale === 'de' && legacyGermanStatusCodes.has(key)) return true;
  // The language selector already displayed the native names Deutsch/English.
  if (locale === 'de' && (key === 'orders.runtimeDomain.documentLanguageNames.de'
    || key === 'orders.runtimeDomain.documentLanguageNames.en')) return true;
  const isDocumentLayoutFallback = key === 'settings.tabs.orderManagementFormatPreview'
    || key === 'settings.orderManagementSubTabDescriptions.formatPreview'
    || key.startsWith('settings.documentLayout.');
  return ORDER_MANAGEMENT_ENGLISH_FALLBACK_LOCALES.has(locale)
    && (
      ORDER_MANAGEMENT_ENGLISH_FALLBACK_KEYS.has(key)
      || PRINTER_CONTROL_ENGLISH_FALLBACK_KEYS.has(key)
      || isDocumentLayoutFallback
    );
}

// Heuristic: values that are ALWAYS allowed to match en, regardless of locale.
// Brand names, technical tokens, pure punctuation, very short strings, version
// numbers, hex codes, and ALL-CAPS acronyms. Cognates that happen to be the
// same word in a specific locale go in IDENTICAL_TO_EN_ALLOWED instead.
function isAlwaysAllowedIdentical(value) {
  if (!value) return true;
  if (/^[\s\W_]+$/.test(value)) return true;            // pure punctuation/whitespace
  if (value.length <= 2) return true;                   // single character or 2-char abbrev
  if (/^[A-Z][A-Z0-9_]+$/.test(value)) return true;     // ALL_CAPS_TOKEN
  if (/^v?\d+(\.\d+)+/.test(value)) return true;        // version-like
  if (/^#[0-9a-fA-F]{3,8}$/.test(value)) return true;   // hex color
  if (/^\{\{[^}]+\}\}$/.test(value)) return true;       // pure placeholder
  if (/^\{\{[^}]+\}\}([\s/\-–·,]+\{\{[^}]+\}\})+$/.test(value)) return true;  // placeholders joined by punctuation only ({{a}} / {{b}})
  if (/^[0-9a-fA-F]{6}$/.test(value)) return true;      // bare hex color
  if (/^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$/i.test(value)) return true;  // email
  if (/^https?:\/\//.test(value)) return true;          // URL
  if (/^ON,\s+true,\s+1$/.test(value)) return true;     // literal example "ON, true, 1"
  // Brand / technical names that ship verbatim everywhere.
  if (/^(PrintOps|PrintOps|SpoolBuddy|Bambu Lab|Bambu Studio|Bambu Studio 2\.6\+|Bambu Studio sidecar URL|OrcaSlicer|OrcaSlicer sidecar URL|MakerWorld|Spoolman|\(Spoolman\)|Spoolman URL|Tailscale|GitHub|GitLab|Gitea|Forgejo|Discord|MQTT|FTP|HTTPS?|JSON|YAML|RTSP|TLS|SSL|CSRF|OIDC|SSO|SSO \/ OIDC|LDAP|TOTP|2FA|MFA|API|AMS|CRC|SHA256|SHA-256|kWh|MB|GB|KB|RGBA?|HSL|RGB|UTC|ISO|UI|HTTP|HTTP Method|H2D|H2D Pro|X1C|X1E|P1S|P1P|A1|A1 Mini|H2C|N3F|N3S|PETG|PLA|ABS|PA|TPU|PEI|PA-CF|PVA|HIPS|ASA|PC|PETG-HF|G\.code|G-code|gcode|cm³|°C|°F|GCODE|SOURCE|ntfy|Pushover|Telegram|Webhook|Webhook URL|Home Assistant|Home Assistant URL|CallMeBot\/WhatsApp|PrintOps URL|Cool Plate|Cool Plate SuperTack|Engineering Plate|High Temp Plate|Smooth PEI Plate|Textured PEI Plate|Ext-L|Ext-R|ISO \(YYYY-MM-DD\))$/.test(value)) return true;
  return false;
}

// Each locale has a finite exact-value cognate list. Translator notes live next
// to these values in i18n-parity-data.json; unrelated English still fails.
const IDENTICAL_TO_EN_ALLOWED = Object.fromEntries(
  Object.entries(parityData.identicalToEnglishAllowed).map(([locale, values]) => [
    locale, exactValueSet(values, `identicalToEnglishAllowed.${locale}`),
  ]),
);

// Pure comparison logic, exported so tests can verify each failure mode
// without going through file IO or the TypeScript parser.
// Input:  locales = { code: Map<leafKey, leafString> }  (must contain 'en')
// Output: { failed, reports: Array<{ label, items }> }
export function compareLocales(locales) {
  if (!locales.en) throw new Error("compareLocales requires a locales.en entry");
  const reports = [];
  const add = (label, items) => {
    if (items.length) reports.push({ label, items });
  };

  const enKeys = new Set(locales.en.keys());

  // Check 1: key set equality
  for (const [code, map] of Object.entries(locales)) {
    if (code === 'en') continue;
    const keys = new Set(map.keys());
    const missing = [...enKeys].filter((k) => !keys.has(k)).sort();
    const extra = [...keys].filter((k) => !enKeys.has(k)).sort();
    add(`${code}: missing keys vs en`, missing);
    add(`${code}: extra keys vs en`, extra);
    if (locales.en.containerTypes && map.containerTypes) {
      const shapeMismatches = [];
      for (const [key, expected] of locales.en.containerTypes) {
        const actual = map.containerTypes.get(key);
        // Leaf parity already checks object keys. Arrays additionally require
        // their ordered runtime shape, rather than a numeric-key object.
        if (expected !== 'array' && actual !== 'array') continue;
        if (actual !== expected) {
          shapeMismatches.push(`${key || '<root>'}: expected ${expected}, got ${actual ?? 'missing'}`);
        }
      }
      add(`${code}: container type mismatch vs en`, shapeMismatches);
    }
  }

  // Check 2: placeholder set equality per leaf
  for (const [code, map] of Object.entries(locales)) {
    if (code === 'en') continue;
    const mismatches = [];
    for (const [key, enValue] of locales.en) {
      const otherValue = map.get(key);
      if (otherValue === undefined) continue;
      const enPlaceholders = new Set((enValue.match(placeholderRe) ?? []));
      const otherPlaceholders = new Set((otherValue.match(placeholderRe) ?? []));
      const missingPh = [...enPlaceholders].filter((p) => !otherPlaceholders.has(p));
      const extraPh = [...otherPlaceholders].filter((p) => !enPlaceholders.has(p));
      if (missingPh.length || extraPh.length) {
        mismatches.push(`${key}: en=${[...enPlaceholders].join(',') || '∅'} vs ${code}=${[...otherPlaceholders].join(',') || '∅'}`);
      }
    }
    add(`${code}: placeholder mismatch vs en`, mismatches);
  }

  // Check 3: plural suffix presence + reverse _one guard
  for (const [code, map] of Object.entries(locales)) {
    if (code === 'en') continue;
    const pluralIssues = [];
    for (const key of enKeys) {
      if (key.endsWith('_plural') && !map.has(key)) pluralIssues.push(`missing _plural key: ${key}`);
      if (key.endsWith('_one') && !map.has(key)) pluralIssues.push(`missing _one key: ${key}`);
      if (key.endsWith('_other') && !map.has(key)) pluralIssues.push(`missing _other key: ${key}`);
    }
    for (const key of map.keys()) {
      if (key.endsWith('_one') && !enKeys.has(key)) {
        pluralIssues.push(`unexpected _one not present in en: ${key}`);
      }
    }
    add(`${code}: plural key mismatch`, pluralIssues);
  }

  // Check 4: identical-to-en leaks. A non-English leaf whose value exactly
  // matches en.ts must either pass the always-allowed heuristic OR be listed
  // in IDENTICAL_TO_EN_ALLOWED[code]. Otherwise it's almost certainly an
  // untranslated English string that slipped through past parity gates.
  for (const [code, map] of Object.entries(locales)) {
    if (code === 'en') continue;
    const allowed = IDENTICAL_TO_EN_ALLOWED[code] ?? new Set();
    const leaks = [];
    for (const [key, enValue] of locales.en) {
      const localeValue = map.get(key);
      if (localeValue === undefined) continue;
      if (localeValue !== enValue) continue;
      if (isAlwaysAllowedIdentical(enValue)) continue;
      if (isAllowedOrderManagementEnglishFallback(code, key)) continue;
      if (allowed.has(enValue)) continue;
      const preview = enValue.length > 60 ? `${enValue.slice(0, 57)}...` : enValue;
      leaks.push(`${key}: "${preview}"`);
    }
    add(`${code}: leaves identical to en (untranslated?)`, leaks);
  }

  return { failed: reports.length > 0, reports };
}

// en is the reference locale; every other locale discovered in the locales
// directory is checked identically and a drift in any of them fails CI.
// Skip file IO / process.exit when imported as a library (e.g. from tests).
const isMainModule = import.meta.url === url.pathToFileURL(process.argv[1] ?? '').href;
if (isMainModule) {
  const discovered = fs
    .readdirSync(localesDir)
    .filter((f) => f.endsWith('.ts'))
    .map((f) => f.slice(0, -3))
    .sort();
  if (!discovered.includes('en')) {
    console.error(`No en.ts found in ${localesDir} — cannot run parity check without a reference locale.`);
    process.exit(1);
  }
  const codes = ['en', ...discovered.filter((c) => c !== 'en')];
  const locales = Object.fromEntries(
    codes.map((c) => [c, loadLocale(path.join(localesDir, `${c}.ts`))]),
  );

  const MAX_REPORT = 20;
  const { reports } = compareLocales(locales);

  if (reports.length) {
    console.error(`\n=== Locale parity failures (en is the reference) ===`);
    for (const { label, items } of reports) {
      console.error(`\n[${label}] (${items.length})`);
      items.slice(0, MAX_REPORT).forEach((i) => console.error(`  ${i}`));
      if (items.length > MAX_REPORT) console.error(`  ... and ${items.length - MAX_REPORT} more`);
    }
  }

  console.log('\nLocale leaf counts:');
  for (const [code, map] of Object.entries(locales)) {
    const tier = code === 'en' ? 'ref' : 'locale';
    console.log(`  ${code.padEnd(6)} ${String(map.size).padEnd(6)} [${tier}]`);
  }

  if (reports.length > 0) {
    console.error(`\n❌ i18n parity check failed.`);
    process.exit(1);
  }
  const others = codes.filter((c) => c !== 'en');
  console.log(`\n✓ All locales in parity with en (${others.join(' / ')}).`);
}
