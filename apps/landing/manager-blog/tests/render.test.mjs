import test from 'node:test';
import assert from 'node:assert/strict';
import { renderManagerMarkdown } from '../lib/render-manager-markdown.mjs';

test('renders comparison tables, numbered steps and escaped fenced code', () => {
 const html = renderManagerMarkdown('# Test\n\n| Method | Cost |\n| --- | --- |\n| IPF | Low |\n\n1. Get data\n2. Compare\n\n```js\n<script>bad()</script>\n```');
 assert.match(html, /<table/); assert.match(html, /<th[^>]*>Method/); assert.match(html, /<td[^>]*>IPF/);
 assert.match(html, /<ol/); assert.match(html, /<li>Compare/);
 assert.match(html, /&lt;script&gt;bad\(\)&lt;\/script&gt;/); assert.doesNotMatch(html, /<script>/);
});
test('blocks executable and protocol-relative links and attribute injections', () => {
 const html = renderManagerMarkdown('[bad](javascript:alert) ![x](data:bad) [bad](//evil.test) [slash](/\\evil.test) ![quote\"](/safe.png) <img onerror=bad>');
 assert.doesNotMatch(html, /href="(?:javascript|\/\/|\/\\)|src="data|alt="quote""|<img onerror/);
 assert.match(html, /alt="quote&quot;"/); assert.match(html, /&lt;img/);
});
test('keeps citations, local media, readable paragraphs and formatting', () => {
 const html = renderManagerMarkdown('## Result\n\n**Better** with `IPF` and [source](https://example.org/a?q=1&x=2).\n\n![Result](/blog/manager/media/abc.png)\n\n- One\n- Two');
 assert.match(html, /<strong>Better/); assert.match(html, /<code/); assert.match(html, /href="https:\/\/example.org\/a\?q=1&amp;x=2"/);
 assert.match(html, /src="\/blog\/manager\/media\/abc.png"/); assert.match(html, /<ul/);
});
