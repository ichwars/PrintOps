import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { resolve } from 'node:path';
import { createInterface } from 'node:readline';
import {
  isIsoCountryCode,
  isIsoCurrencyCode,
  normalizeNfkcCasefold,
  orderMasterDataValidationMetadata,
} from '../src/lib/orderMasterDataValidation.ts';

const localVenv = process.platform === 'win32'
  ? resolve('..', '.venv', 'Scripts', 'python.exe')
  : resolve('..', '.venv', 'bin', 'python');
const arguments_ = process.argv.slice(2);
const explicitPython = arguments_.find((argument) => !argument.startsWith('--'));
const pythonExecutable = process.env.PYTHON
  ?? explicitPython
  ?? (existsSync(localVenv) ? localVenv : process.platform === 'win32' ? 'python' : 'python3');

async function verifyGeneratedSource() {
  const generator = spawn(
    pythonExecutable,
    [resolve('scripts', 'generate-order-master-data-validation.py'), '--check'],
    { stdio: 'inherit', windowsHide: true },
  );
  const exitCode = await new Promise((resolveCompletion, reject) => {
    generator.once('error', reject);
    generator.once('close', resolveCompletion);
  });
  if (exitCode !== 0) throw new Error(`Generator check exited with status ${exitCode}`);
}

async function verifyUnicodeParity() {
const pythonSource = String.raw`
import json
import sys

import pycountry
from backend.app.core.text_normalization import (
    UNICODE_NORMALIZATION_VERSION,
    normalize_case_insensitive_key,
)

if not (3, 10) <= sys.version_info[:2] <= (3, 13):
    raise RuntimeError(f"Expected Python 3.10-3.13, received {sys.version.split()[0]}")

print(json.dumps({
    "pythonVersion": sys.version.split()[0],
    "unicodeVersion": UNICODE_NORMALIZATION_VERSION,
    "unicodeProvider": "backend.app.core.text_normalization",
    "pycountryVersion": pycountry.__version__,
    "countryCodes": sorted(country.alpha_2 for country in pycountry.countries),
    "currencyCodes": sorted(currency.alpha_3 for currency in pycountry.currencies),
}))
chunk_size = 4096
for start in range(0, sys.maxunicode + 1, chunk_size):
    end = min(start + chunk_size, sys.maxunicode + 1)
    values = [normalize_case_insensitive_key(chr(cp)) for cp in range(start, end)]
    print(json.dumps([start, values], ensure_ascii=True))
`;

function acceptedCodes(length, predicate) {
  const accepted = [];
  const visit = (prefix) => {
    if (prefix.length === length) {
      if (predicate(prefix)) accepted.push(prefix);
      return;
    }
    for (let code = 65; code <= 90; code += 1) visit(prefix + String.fromCharCode(code));
  };
  visit('');
  return accepted;
}

const python = spawn(pythonExecutable, ['-c', pythonSource], {
  stdio: ['ignore', 'pipe', 'pipe'],
  windowsHide: true,
  cwd: resolve('..'),
});
let stderr = '';
python.stderr.setEncoding('utf8');
python.stderr.on('data', (chunk) => { stderr += chunk; });

const completion = new Promise((resolveCompletion, reject) => {
  python.once('error', reject);
  python.once('close', resolveCompletion);
});
const lines = createInterface({ input: python.stdout, crlfDelay: Infinity });
let metadataChecked = false;
let comparedCodePoints = 0;
let mismatchCount = 0;
const firstMismatches = [];

for await (const line of lines) {
  const payload = JSON.parse(line);
  if (!metadataChecked) {
    metadataChecked = true;
    const [, major, minor] = payload.pythonVersion.match(/^(\d+)\.(\d+)\./) ?? [];
    const supportedPython = Number(major) === 3 && Number(minor) >= 10
      && Number(minor) <= 13
      && payload.unicodeProvider === 'backend.app.core.text_normalization';
    if (!supportedPython
      || payload.unicodeVersion !== orderMasterDataValidationMetadata.unicodeVersion
      || payload.pycountryVersion !== orderMasterDataValidationMetadata.pycountryVersion) {
      throw new Error(
        `Expected Python 3.10-3.13 with checked-in backend normalization / Unicode ${orderMasterDataValidationMetadata.unicodeVersion} / pycountry ${orderMasterDataValidationMetadata.pycountryVersion}; received Python ${payload.pythonVersion} (${payload.unicodeProvider}) / Unicode ${payload.unicodeVersion} / pycountry ${payload.pycountryVersion}`,
      );
    }

    const actualCountries = acceptedCodes(2, isIsoCountryCode);
    const actualCurrencies = acceptedCodes(3, isIsoCurrencyCode);
    if (JSON.stringify(actualCountries) !== JSON.stringify(payload.countryCodes)
      || JSON.stringify(actualCurrencies) !== JSON.stringify(payload.currencyCodes)) {
      throw new Error('Generated ISO country or currency code set does not exactly match pycountry');
    }
    if (actualCountries.length !== orderMasterDataValidationMetadata.countryCodeCount
      || actualCurrencies.length !== orderMasterDataValidationMetadata.currencyCodeCount) {
      throw new Error('Generated ISO metadata counts do not match the exact accepted sets');
    }
    continue;
  }

  const [start, expectedValues] = payload;
  for (let offset = 0; offset < expectedValues.length; offset += 1) {
    const codePoint = start + offset;
    const actual = normalizeNfkcCasefold(String.fromCodePoint(codePoint));
    if (actual !== expectedValues[offset]) {
      mismatchCount += 1;
      if (firstMismatches.length < 10) {
        firstMismatches.push(`U+${codePoint.toString(16).toUpperCase().padStart(4, '0')}`);
      }
    }
  }
  comparedCodePoints += expectedValues.length;
}

const exitCode = await completion;
if (exitCode !== 0) throw new Error(stderr.trim() || `Python exited with status ${exitCode}`);
if (!metadataChecked) throw new Error('Python produced no verification metadata');
if (comparedCodePoints !== 0x110000) throw new Error(`Expected 1114112 code points, received ${comparedCodePoints}`);

console.log(`countries=${orderMasterDataValidationMetadata.countryCodeCount} currencies=${orderMasterDataValidationMetadata.currencyCodeCount} compared=${comparedCodePoints} mismatches=${mismatchCount}`);
if (mismatchCount > 0) {
  console.error(`first mismatches: ${firstMismatches.join(', ')}`);
  process.exitCode = 1;
}
}

if (arguments_.includes('--generated-only')) await verifyGeneratedSource();
else await verifyUnicodeParity();
