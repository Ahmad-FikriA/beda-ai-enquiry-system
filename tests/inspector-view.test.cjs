const {test} = require('node:test');
const assert = require('node:assert/strict');
const view = require('../beda/static/inspector-view.js');

test('structured results become readable labels without losing false or zero', () => {
  const html = view.renderSection('Recommendation', {requires_approval:true, crm_modified:false, attempt_count:0, action:'REQUEST_MISSING_INFORMATION'});
  assert.match(html, /Human approval required/);
  assert.match(html, />Yes</);
  assert.match(html, />No</);
  assert.match(html, />0</);
  assert.match(html, /Request missing information/);
  assert.match(html, /<details class="technical-details">/);
  assert.doesNotMatch(html, /<details[^>]*\bopen\b/);
});

test('untrusted messages and JSON remain text, never executable markup', () => {
  const html = view.renderSection('<script>title</script>', {body:'<img src=x onerror=alert(1)> & "hello"'});
  assert.doesNotMatch(html, /<script>|<img/);
  assert.match(html, /&lt;img/);
  assert.match(html, /&amp;/);
});

test('missing information and evidence render as lists and labelled records', () => {
  const html = view.renderSection('Output', {missing_fields:['electricity_bill'], facts:[{name:'company',value:'ACME',evidence:'Company: ACME'}]});
  assert.match(html, /Missing information/);
  assert.match(html, /Electricity bill/);
  assert.match(html, /<ul/);
  assert.match(html, /Supporting quote/);
  assert.match(html, /ACME/);
});

test('empty values are explicit without implying an unknown value is false', () => {
  assert.match(view.renderValue(null), /Not provided/);
  assert.match(view.renderValue([]), /None recorded/);
  assert.match(view.renderValue({}), /None recorded/);
  assert.match(view.renderValue(false), />No</);
});

test('free text and unusual field names are preserved rather than treated as status codes', () => {
  assert.equal(view.renderValue('HIGH','body'), '<span class="result-text">HIGH</span>');
  assert.equal(view.renderValue('toString','status'), '<span class="result-text">toString</span>');
  assert.match(view.renderValue(JSON.parse('{"constructor":"original"}')), /<dt>Constructor<\/dt>/);
});

test('technical JSON highlights keys while preserving source values and punctuation', () => {
  const html = view.highlightJson({company:'ACME',approved:false});
  assert.match(html, /json-key/);
  assert.match(html, /json-string/);
  assert.match(html, /json-literal/);
  const text = html.replace(/<[^>]*>/g,'').replace(/&quot;/g,'"');
  assert.deepEqual(JSON.parse(text), {company:'ACME',approved:false});
});
