// Exercise the installed wrapper dependencies, including after production pruning.
const assert = require('node:assert/strict');
const { createRequire } = require('node:module');
const path = require('node:path');
const http = require('node:http');
const { PassThrough } = require('node:stream');
const zlib = require('node:zlib');
const { test } = require('node:test');

const wrapperRequire = createRequire(path.resolve(process.argv[2], 'package.json'));
const express = wrapperRequire('express');
const multer = wrapperRequire('multer');
const qs = wrapperRequire('qs');

for (const encoding of ['gzip', 'deflate']) {
  for (const trailing of [false, true]) {
    test(`compressed JSON: ${encoding}, trailing bytes=${trailing}`, { timeout: 5000 }, async (t) => {
      const app = express();
      let client;
      app.use(express.json());
      app.post('/', (req, res) => {
        if (trailing) {
          req.once('end', () => res.json(req.body));
          client.end(Buffer.alloc(1024, 0x58));
        } else res.json(req.body);
      });
      const server = app.listen(0, '127.0.0.1');
      t.after(() => { server.closeAllConnections(); server.close(); });
      await new Promise((resolve) => server.once('listening', resolve));
      const compressed = zlib[encoding === 'gzip' ? 'gzipSync' : 'deflateSync']('{"a":1}');
      const first = trailing ? Buffer.concat([compressed, Buffer.from([0])]) : compressed;
      const response = await new Promise((resolve, reject) => {
        client = http.request({
          host: '127.0.0.1', port: server.address().port, method: 'POST', path: '/', agent: false,
          headers: { 'content-type': 'application/json', 'content-encoding': encoding,
            'content-length': first.length + (trailing ? 1024 : 0) },
        }, (res) => {
          let body = '';
          res.on('data', (chunk) => { body += chunk; });
          res.on('end', () => resolve({ status: res.statusCode, body }));
        });
        client.on('error', reject);
        client.setTimeout(2000, () => client.destroy(new Error('HTTP parser stalled')));
        if (trailing) client.write(first); else client.end(first);
      });
      // Wait for decoder errors that can arrive after a successful response.
      await new Promise((resolve) => setTimeout(resolve, 100));
      assert.equal(response.status, 200);
      assert.deepEqual(JSON.parse(response.body), { a: 1 });
    });
  }
}

test('late asynchronous file filter after request teardown', { timeout: 5000 }, async () => {
  const req = new PassThrough();
  const failure = new Error('file rejected');
  let resumeFilter;
  let parser;
  let calls = 0;
  const boundary = 'PrintOpsTeardown';
  const body = ['first', 'second'].map((name) => [
    `--${boundary}`, `Content-Disposition: form-data; name="${name}"; filename="${name}.txt"`,
    'Content-Type: text/plain', '', name,
  ].join('\r\n')).join('\r\n'); // Deliberately truncated multipart input.
  const upload = multer({
    fileHwm: 1,
    streamHandler: (_req, stream) => { parser = stream; req.pipe(stream); },
    fileFilter: (_req, file, cb) => {
      if (file.fieldname === 'first') resumeFilter = cb;
      else req.once('end', () => setImmediate(() => cb(failure)));
    },
  }).any();
  req.headers = { 'content-type': `multipart/form-data; boundary=${boundary}`,
    'content-length': Buffer.byteLength(body) };
  await new Promise((resolve, reject) => {
    upload(req, null, (err) => {
      calls++;
      try { assert.equal(err, failure); assert.equal(typeof resumeFilter, 'function'); }
      catch (error) { reject(error); return; }
      setImmediate(() => {
        parser.once('close', resolve); // Do not mask an unhandled parser error.
        resumeFilter(null, true);
      });
    });
    req.end(body);
  });
  assert.equal(calls, 1);
  assert.deepEqual(req.files, []);
});

for (const encodeValuesOnly of [false, true]) {
  test(`comma serialization rejects hostile coercion safely, encodeValuesOnly=${encodeValuesOnly}`, () => {
    const options = { arrayFormat: 'comma', encodeValuesOnly };
    for (const value of [
      JSON.parse('{"a":[{"toString":"x"}]}'),
      qs.parse('a[0][toString]=x', { allowPrototypes: true }),
      qs.parse('a[][b]=c', { plainObjects: true }),
    ]) {
      assert.doesNotThrow(() => qs.stringify(value, options));
    }
    assert.equal(qs.stringify({ a: ['x', 'y'] }, options), encodeValuesOnly ? 'a=x,y' : 'a=x%2Cy');
    assert.equal(qs.stringify({ a: [{ toString: () => 'custom' }] }, options), 'a=custom');
  });
}
