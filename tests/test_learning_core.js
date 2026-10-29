'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const corePath = path.join(__dirname, '../web/learning-core.js');
const lexPath = path.join(__dirname, '../web/learning-lexicon.js');
const core = fs.existsSync(corePath) ? require(corePath) : {};
const lexicon = fs.existsSync(lexPath) ? require(lexPath) : [];
const retainedIds = [
  'glass-half','natural-governor','nimby','coiled-spring','buy-the-dip','tailwinds',
  'otherworldly','astounding','bifurcated','ensued','historical-analogs',
  'irrational-exuberance','preemptive-tightening','qoq-revenue','priced-in',
  'de-risking','long-short-positioning','capitulation','dovish','style-tilt',
  'frontier-models','revenue-per-worker','cds-widen','treasury-issuance'
];
const excludedTerms = [
  ['heres-the-thing', 'here’s the thing'], ['skeptics', 'skeptics'], ['catalyst', 'catalyst'],
  ['competitive-threat', 'competitive threat'], ['revenue-slowdown', 'revenue slowdown'],
  ['tumble-in-stocks', 'a tumble in stocks'], ['hedge-funds', 'hedge funds'],
  ['shorting', 'shorting'], ['fed-hike', 'Fed hike'], ['odds', 'odds'], ['yields', 'yields'],
  ['surge', 'surge'], ['spiked', 'spiked'], ['sunk', 'sunk'], ['turnaround', 'turnaround'],
  ['relative-performance', 'relative performance'], ['underperformance', 'underperformed'],
  ['seasonality', 'seasonality'], ['millennials', 'millennials'], ['bottlenecks', 'bottlenecks'],
  ['drive-productivity', 'driving productivity'], ['funding-needs', 'funding needs'],
  ['cost-of-funds', 'cost of funds'], ['default-risk', 'default risk'],
  ['debt-issuance', 'debt issuance'], ['debt-default', 'debt default'],
  ['year-to-date', 'year-to-date'], ['large-cap', 'large-cap'], ['small-cap', 'small-cap'],
  ['basis-points', 'basis points'], ['portfolio-manager', 'portfolio manager'],
  ['democrat-leaning', 'Democrat-leaning'], ['flip-supporting', 'flip to supporting'],
  ['propaganda', 'propaganda']
];

test('known canonical IDs are excluded before the whole-video sentence quota, without mutating source', () => {
  const cues = Array.from({length: 70}, (_, i) => ({start:i,end:i+1,english:'Otherworldly astounding bifurcated ensued.',chinese:'原文'}));
  const original = JSON.stringify(cues), options = {known:['otherworldly']};
  const annotated = core.annotateCues(cues, options);
  assert.ok(annotated.every(c => !c.learning.some(x => x.id === 'otherworldly')));
  assert.deepEqual(annotated[0].learning.map(x => x.id), ['astounding','bifurcated','ensued']);
  assert.equal(annotated.flatMap(c => c.learning).filter(x => x.id === 'ensued').length, 2);
  assert.equal(JSON.stringify(cues), original);
  assert.deepEqual(options, {known:['otherworldly']});
  assert.deepEqual(core.annotateCues(cues), core.annotateCues(cues, {known:[]}));
});

test('known variants disappear across the full video and neutral reannotation restores the same two rows', () => {
  const cues = ['Otherworldly','OTHERWORLDLY','otherworldly'].map(english => ({english,chinese:''}));
  assert.equal(core.annotateCues(cues, {known:['otherworldly']}).flatMap(c => c.learning).length, 0);
  assert.deepEqual(core.annotateCues(cues, {known:[]}).map(c => c.learning.length), [1,1,0]);
});

// Exercise the real browser factory with synthetic claims, without retaining easy vocabulary.
function coreWithLexicon(entries) {
  const sandbox = {window: {LearningLexicon: entries.map(entry => ({
    kind: 'vocab', term: entry.id, meaning: '测试释义', note: '仅测试中文歧义保护。',
    chinese: [], ...entry
  }))}};
  vm.runInNewContext(fs.readFileSync(corePath, 'utf8'), sandbox);
  return {analyzePair: (...args) => JSON.parse(JSON.stringify(sandbox.window.LearningCore.analyzePair(...args)))};
}

function countIds(rows) {
  const counts = {};
  for (const row of rows) for (const item of row.learning) counts[item.id] = (counts[item.id] || 0) + 1;
  return counts;
}

test('publishes browser and CommonJS contracts and a selective curated array', () => {
  assert.equal(typeof core.analyzePair, 'function');
  assert.equal(typeof core.annotateCues, 'function');
  assert.ok(Array.isArray(lexicon));
  assert.deepEqual(lexicon.map(x => x.id).sort(), [...retainedIds].sort());
  assert.equal(new Set(lexicon.map(x => x.id)).size, lexicon.length);
  const sandbox = {window: {}};
  vm.runInNewContext(fs.readFileSync(lexPath, 'utf8'), sandbox);
  vm.runInNewContext(fs.readFileSync(corePath, 'utf8'), sandbox);
  assert.equal(typeof sandbox.window.LearningCore.analyzePair, 'function');
  assert.ok(Array.isArray(sandbox.window.LearningLexicon));
  assert.equal(sandbox.window.LearningCore.analyzePair('astounding', '惊人')[0].kind, 'vocab');
});

function validate(en, zh, items) {
  assert.ok(items.length <= 3);
  assert.equal(new Set(items.map(x => x.id)).size, items.length);
  const english = [], chinese = [];
  for (const item of items) {
    assert.deepEqual(Object.keys(item).sort(), ['id','kind','term','meaning','note','english','chinese','warning'].sort());
    assert.ok(['idiom','vocab','finance'].includes(item.kind));
    for (const key of ['id','term','meaning','note','warning']) assert.equal(typeof item[key], 'string');
    assert.ok(item.meaning && item.note);
    for (const [source, spans, previous] of [[en,[item.english],english],[zh,item.chinese,chinese]]) {
      for (const s of spans) {
        assert.ok(s.start >= 0 && s.end > s.start && s.end <= source.length);
        assert.equal(source.slice(s.start, s.end), s.text);
        assert.ok(previous.every(p => p.end <= s.start || s.end <= p.start));
        previous.push(s);
      }
    }
  }
}

test('UTF-16 offsets, original case and exact curated Chinese spans remain lossless', () => {
  const en = '😀 An ASTOUNDING bifurcated pattern ensued.', zh = '😀 惊人的两极分化随之而来。';
  const items = core.analyzePair(en, zh);
  assert.equal(items.length, 3);
  validate(en, zh, items);
  assert.equal(items.find(x => x.term === 'astounding').english.start, 6);
  assert.equal(items.find(x => x.term === 'astounding').chinese[0].start, 3);
});

test('word boundaries exclude basic words, names and embedded terms', () => {
  for (const en of ['I think Tom Lee and Cisco know this.', 'astoundingly catalystic skepticsx', 'éastounding astoundingé']) {
    assert.deepEqual(core.analyzePair(en, ''), []);
  }
});

test('longest first, distinct IDs, max three and no overlap in either language', () => {
  const en = 'quarter-over-quarter revenue growth, irrational exuberance, natural governor, credit default swaps widen, astounding';
  const zh = '季度环比收入增长，非理性繁荣，自发约束机制，信用违约掉期利差扩大，惊人';
  const items = core.analyzePair(en, zh);
  validate(en, zh, items);
  assert.equal(items.length, 3);
  assert.ok(items.some(x => x.english.text === 'quarter-over-quarter revenue growth'));
  const glass = core.analyzePair('glass half full, glass half empty', '半满半空的玻璃杯');
  assert.equal(glass.length, 1);
  assert.equal(glass[0].kind, 'idiom');
});

test('Chinese has explicit counterparts only; absent and bad literals use gloss plus separate warnings', () => {
  for (const [en, zh, expected] of [
    ['natural governor','天然的统治者','自发约束机制'],
    ['not in my backyard','不在我后院','邻避'],
    ['buying this AI dip','人工智能浸','逢回调买入'],
    ['getting priced in','都被定价了','价格'],
    ['capitulation','投降','恐慌性抛售']
  ]) {
    const [item] = core.analyzePair(en, zh, 'stocks short positioning');
    assert.ok(item, en);
    assert.match(item.meaning, new RegExp(expected));
    assert.ok(item.warning, en);
    assert.deepEqual(item.chinese, []);
  }
  assert.deepEqual(core.analyzePair('astounding', '毫无对应')[0].chinese, []);
  assert.equal(core.analyzePair('astounding', '惊人')[0].warning, '');
  assert.match(core.analyzePair('coiled spring','弹簧')[0].note, /不.*保证|并非.*保证/);
  assert.match(core.analyzePair('dovish','鸽派')[0].note, /不.*已.*降息/);
});

test('glass-half contrast is one complete bilingual span, with standalone variants retained', () => {
  const phrase = 'glass half full, glass half empty';
  const en = '😀 This is a ' + phrase + ' thing.', zh = '这就像半满半空的玻璃杯。';
  const items = core.analyzePair(en, zh);
  assert.equal(items.length, 1);
  assert.equal(items[0].id, 'glass-half');
  assert.deepEqual(items[0].english, {start: en.indexOf(phrase), end: en.indexOf(phrase) + phrase.length, text: phrase});
  assert.deepEqual(items[0].chinese, [{start: 3, end: 11, text: '半满半空的玻璃杯'}]);
  validate(en, zh, items);
  for (const standalone of ['glass half full', 'glass half empty']) {
    const [item] = core.analyzePair(standalone, '');
    assert.equal(item.id, 'glass-half');
    assert.equal(item.english.text, standalone);
  }
});

test('ambiguous finance meanings require bounded relevant English context', () => {
  for (const en of ['capitulation', 'de-risking the runway', 'tailwinds over the runway']) assert.deepEqual(core.analyzePair(en, ''), []);
  assert.ok(core.analyzePair('capitulation', '', 'short positioning in stocks').length);
  assert.ok(core.analyzePair('de-risking', '', 'Treasury bond and Fed').length);
  assert.ok(core.analyzePair('tailwinds', '', 'AI stocks and markets').length);
  assert.ok(core.analyzePair('AI market tailwinds', '市场利好因素').some(x => x.id === 'tailwinds'));
});

test('annotateCues uses two preceding and one following row, copies rows and never mutates', () => {
  const input = [{english:'stocks',chinese:''},{english:'nothing',chinese:''},{english:'capitulation',chinese:'投降',start:2,end:3},{english:'nothing',chinese:''},{english:'capitulation',chinese:''}];
  const before = JSON.stringify(input);
  input.forEach(Object.freeze); Object.freeze(input);
  const result = core.annotateCues(input);
  assert.notEqual(result,input);
  result.forEach((row,i) => assert.notEqual(row,input[i]));
  assert.equal(result[2].learning.length,1);
  assert.equal(result[4].learning.length,0);
  assert.equal(JSON.stringify(input), before);
  assert.equal(core.annotateCues([{english:'de-risking',chinese:''},{english:'Treasury bonds',chinese:''}])[0].learning.length,1);
  assert.equal(core.annotateCues([{english:'de-risking',chinese:''},{english:'nothing'},{english:'Treasury bonds'}])[0].learning.length,0);
});

test('default analysis excludes easy vocabulary before applying the three-item sentence quota', () => {
  for (const [, term] of excludedTerms) {
    assert.deepEqual(core.analyzePair(term, '', 'Fed Treasury bonds stocks AI markets'), [], term);
  }
  const simple = excludedTerms.map(([, term]) => term).join(', ');
  assert.deepEqual(core.analyzePair(simple, ''), []);
  assert.deepEqual(core.annotateCues([{english: simple, chinese: '普通词汇无需标记。'}])[0].learning, []);
  const en = simple + '; astounding, bifurcated, ensued.';
  for (const items of [core.analyzePair(en, ''), core.annotateCues([{english: en, chinese: ''}])[0].learning]) {
    assert.deepEqual(items.map(item => item.id), ['astounding', 'bifurcated', 'ensued']);
    validate(en, '', items);
  }
});

test('whole-video cap follows canonical IDs across 125 rows and 50-row page boundaries', () => {
  const rows = Array.from({length: 125}, (_, index) => ({
    id: 'source-' + index, english: '😀 Original sentence ' + index + '.', chinese: '原始句子。',
    start: index * 2, end: index * 2 + 1, provenance: {source: 'retained', index}
  }));
  const occurrences = [49, 50, 99, 100, 124];
  const variants = [
    'AI markets: TAILWIND, HISTORICAL ANALOGUE, DE-RISK.',
    'AI markets: tailwinds, historical analogs, de risking.',
    'AI markets: Tailwind, Historical Analogues, DE-RISKING.'
  ];
  occurrences.forEach((row, index) => { rows[row].english = variants[index % variants.length]; });
  const before = JSON.stringify(rows);
  rows.forEach(row => { Object.freeze(row.provenance); Object.freeze(row); });
  Object.freeze(rows);
  const annotated = core.annotateCues(rows);
  assert.deepEqual(countIds(annotated), {'tailwinds': 2, 'historical-analogs': 2, 'de-risking': 2});
  assert.deepEqual(annotated.filter(row => row.learning.length).map(row => row.id), ['source-49', 'source-50']);
  annotated.forEach((row, index) => {
    const {learning, ...original} = row;
    assert.notEqual(row, rows[index]);
    assert.deepEqual(original, rows[index]);
    validate(row.english, row.chinese, learning);
  });
  // All views take rows from this one complete annotation result, never annotate page slices.
  const pages = [annotated.slice(0, 50), annotated.slice(50, 100), annotated.slice(100)];
  assert.deepEqual(pages.map(page => page.reduce((sum, row) => sum + row.learning.length, 0)), [3, 3, 0]);
  assert.strictEqual(pages[1][0], annotated[50]);
  assert.deepEqual(core.annotateCues(rows), annotated);
  core.annotateCues([{english: variants[0], chinese: ''}]);
  core.analyzePair(variants[0], '');
  assert.deepEqual(core.annotateCues(rows), annotated);
  assert.deepEqual(core.annotateCues(annotated), annotated);
  assert.equal(JSON.stringify(rows), before);
});

test('repeated mentions in one row consume one occurrence, not two', () => {
  const rows = ['ASTOUNDING, astounding, Astounding.', 'astounding', 'ASTOUNDING']
    .map(english => ({english, chinese: '惊人'}));
  const annotated = core.annotateCues(rows);
  assert.deepEqual(annotated.map(row => row.learning.length), [1, 1, 0]);
  assert.equal(annotated[0].learning[0].english.text, 'ASTOUNDING');
  assert.deepEqual(countIds(annotated), {astounding: 2});
});

test('exhausted IDs are excluded before the sentence quota so fresh advanced items still fit', () => {
  const spent = 'quarter-over-quarter revenue growth, long-short positioning, irrational exuberance';
  const rows = [spent, spent, spent + ', astounding bifurcated ensued']
    .map(english => ({english, chinese: ''}));
  const annotated = core.annotateCues(rows);
  assert.deepEqual(annotated[2].learning.map(item => item.id), ['astounding', 'bifurcated', 'ensued']);
  assert.ok(Object.values(countIds(annotated)).every(count => count <= 2));
  validate(rows[2].english, '', annotated[2].learning);
});

test('context-rejected and sentence-quota-rejected items do not consume video occurrences', () => {
  const rows = [
    {english: 'tailwinds over the runway', chinese: ''},
    ...Array.from({length: 3}, () => ({english: 'nothing', chinese: ''})),
    {english: 'AI tailwinds', chinese: ''},
    {english: 'AI TAILWIND', chinese: ''},
    {english: 'AI tailwinds', chinese: ''},
    {english: 'quarter-over-quarter revenue growth, long-short positioning, irrational exuberance, astounding', chinese: ''},
    {english: 'astounding', chinese: ''},
    {english: 'ASTOUNDING', chinese: ''},
    {english: 'astounding', chinese: ''}
  ];
  const annotated = core.annotateCues(rows);
  assert.equal(annotated[0].learning.length, 0);
  assert.deepEqual(annotated.slice(4, 7).map(row => row.learning.length), [1, 1, 0]);
  assert.ok(annotated[7].learning.every(item => item.id !== 'astounding'));
  assert.deepEqual(annotated.slice(8).map(row => row.learning.length), [1, 1, 0]);
});

test('self-authored full-video UTF-8 pairs preserve every source field and validate annotations', () => {
  const examples=[['😀 An otherworldly invention appeared.','😀 一项超凡脱俗的发明出现了。'],['An astounding discovery ensued.','随后出现了惊人的发现。'],['The path bifurcated near the garden.','小路在花园附近分叉。']];
  const rows=Array.from({length:114},(_,i)=>({start:i*2,end:i*2+2,english:examples[i%3][0],chinese:examples[i%3][1],source:'self-authored-public-test',fragment:false}));
  const before = JSON.stringify(rows), annotated = core.annotateCues(rows);
  annotated.forEach((row,i) => {const {learning,...original}=row; assert.deepEqual(original, rows[i]); validate(row.english,row.chinese,learning);});
  assert.equal(JSON.stringify(rows),before);
  const counts = countIds(annotated);
  assert.ok(Object.values(counts).every(count => count <= 2));
  assert.ok(Object.keys(counts).every(id => retainedIds.includes(id)));
  for (const [id] of excludedTerms) assert.equal(counts[id], undefined, id);
  assert.deepEqual(core.annotateCues(rows), annotated);
});

test('every curated entry is reachable, deterministic and supplies a Chinese gloss', () => {
  for (const entry of lexicon) {
    const first = core.analyzePair(entry.term, '', 'Fed Treasury bonds stocks short positioning AI markets');
    assert.ok(first.some(item => item.id === entry.id), entry.id);
    validate(entry.term, '', first);
    assert.deepEqual(core.analyzePair(entry.term, '', 'Fed Treasury bonds stocks short positioning AI markets'), first);
    assert.match(entry.meaning, /[\u3400-\u9fff]/);
  }
});

test('curated variants retain source spelling, capitalization and hyphens', () => {
  for (const [surface, id] of [
    ['GLASS HALF EMPTY','glass-half'],['NIMBY','nimby'],['not in my backyard','nimby'],
    ['buy this dip','buy-the-dip'],['BUYING THE AI DIP','buy-the-dip'],
    ['priced in','priced-in'],['getting priced in','priced-in'],
    ['de-risk','de-risking'],['de risking','de-risking'],
    ['long-short positioning','long-short-positioning'],['quarter over quarter revenue growth','qoq-revenue'],
    ['historical analogues','historical-analogs'],['historical analog','historical-analogs']
  ]) {
    const items = core.analyzePair(surface, '', 'stocks');
    assert.equal(items[0].id,id,surface);
    assert.equal(items[0].english.text,surface);
  }
});

test('Chinese shared substrings never create overlapping or invented alignments', () => {
  const en = 'default risk and debt default', zh = '债务违约风险';
  const synthetic = coreWithLexicon([
    {id: 'default-risk', pattern: 'default risk', chinese: ['违约风险']},
    {id: 'debt-default', pattern: 'debt default', chinese: ['债务违约']}
  ]);
  const items = synthetic.analyzePair(en, zh);
  assert.equal(items.length,2);
  validate(en,zh,items);
  assert.ok(items.every(item => item.chinese.length === 0));
  assert.deepEqual(core.analyzePair('revenue per worker','每名工人的收入')[0].chinese,[]);
  assert.deepEqual(core.analyzePair('credit default swaps widen','信用违约掉期扩大')[0].chinese,[]);
});

function competingTranslationCore() {
  return coreWithLexicon([
    {id: 'surge', pattern: 'surge', chinese: ['急剧上升', '飙升']},
    {id: 'spiked', pattern: 'spiked', chinese: ['飙升', '猛升', '突然冲高']},
    {id: 'yields', pattern: 'yields?', chinese: ['国债收益率', '债券收益率', '收益率'], gate: 'bonds?'}
  ]);
}

test('repeated shared translations remain gloss-only instead of priority assigned', () => {
  const en = 'The stock surge ended and bond yields spiked.';
  const zh = '股市飙升结束了，债券收益率飙升。';
  const synthetic = competingTranslationCore();
  const items = synthetic.analyzePair(en, zh);
  assert.equal(items.length, 3);
  validate(en, zh, items);
  for (const id of ['surge', 'spiked']) {
    const item = items.find(x => x.id === id);
    assert.deepEqual(item.chinese, [], id);
    assert.ok(item.meaning);
  }
  assert.equal(items.find(x => x.id === 'yields').chinese[0].text, '债券收益率');
  assert.deepEqual(synthetic.analyzePair('surge', '飙升之后又飙升')[0].chinese, []);
});

test('one Chinese occurrence claimed by two selected terms is uncolored for both', () => {
  const synthetic = competingTranslationCore();
  for (const en of ['surge then spiked', 'spiked then surge']) {
    const items = synthetic.analyzePair(en, '飙升');
    assert.equal(items.length, 2);
    assert.ok(items.every(item => item.chinese.length === 0));
  }
  // A unique claim must not win against another entry with several possible matches.
  const items = synthetic.analyzePair('surge then spiked', '飙升之后猛升');
  assert.ok(items.every(item => item.chinese.length === 0));
});

test('within-entry overlapping alternatives keep the longest exact counterpart', () => {
  const [item] = core.analyzePair('coiled spring', '😀 压紧的弹簧');
  assert.deepEqual(item.chinese, [{start: 3, end: 8, text: '压紧的弹簧'}]);
});

test('empty inputs are empty and contextual matches do not leak into the current sentence', () => {
  assert.deepEqual(core.analyzePair('','','astounding'),[]);
  assert.deepEqual(core.analyzePair(null,undefined),[]);
  assert.deepEqual(core.annotateCues([]),[]);
  assert.deepEqual(core.annotateCues([{english:'nothing',chinese:'',learning:['old']}])[0].learning,[]);
  assert.deepEqual(core.analyzePair('capitulation ' + '.'.repeat(300) + ' stocks',''),[]);
});
