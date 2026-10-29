(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory(require('./learning-lexicon.js'));
  else root.LearningCore = factory(root.LearningLexicon);
})(typeof window !== 'undefined' ? window : this, function (lexicon) {
  'use strict';
  // JS regex indices and String.slice both use UTF-16 code units. Never normalize source text.
  const entries = lexicon.map(entry => ({...entry,
    matcher: new RegExp('(?<![\\p{L}\\p{N}_])(?:' + entry.pattern + ')(?![\\p{L}\\p{N}_])', 'giu'),
    gateMatcher: entry.gate ? new RegExp('(?<![\\p{L}\\p{N}_])(?:' + entry.gate + ')(?![\\p{L}\\p{N}_])', 'iu') : null,
    badMatcher: entry.bad ? new RegExp(entry.bad, 'u') : null
  }));
  const asText = value => typeof value === 'string' ? value : '';
  const overlaps = (a, b) => a.start < b.end && b.start < a.end;
  const span = (source, start, end) => ({start, end, text: source.slice(start, end)});

  function analyzePair(english, chinese, context = '') {
    return analyzeAvailablePair(english, chinese, context);
  }

  function analyzeAvailablePair(english, chinese, context, rowCounts, known) {
    english = asText(english); chinese = asText(chinese); context = asText(context).slice(0, 2400);
    const candidates = [];
    entries.forEach((entry, order) => {
      // Filter exhausted canonical IDs before the sentence's three-item selection.
      if (known?.has(entry.id) || (rowCounts && (rowCounts.get(entry.id) || 0) >= 2)) return;
      entry.matcher.lastIndex = 0;
      let match;
      while ((match = entry.matcher.exec(english))) {
        const start = match.index, end = start + match[0].length;
        // Only the local English neighborhood may license an ambiguous financial sense.
        const nearby = english.slice(Math.max(0, start - 240), end + 240) + '\n' + context;
        if (entry.gateMatcher && !entry.gateMatcher.test(nearby)) continue;
        candidates.push({entry, order, english: span(english, start, end)});
      }
    });
    candidates.sort((a, b) => (b.english.end - b.english.start) - (a.english.end - a.english.start) || a.english.start - b.english.start || a.order - b.order);
    const selected = [], ids = new Set();
    for (const candidate of candidates) {
      if (selected.length === 3) break;
      const {entry, english: englishSpan} = candidate;
      if (ids.has(entry.id) || selected.some(item => overlaps(item.english, englishSpan))) continue;
      selected.push(candidate);
      ids.add(entry.id);
    }
    // Collect all selected entries' claims before resolving any Chinese alignment.
    const claims = selected.map(({entry}) => {
      const chineseCandidates = [];
      for (const pattern of entry.chinese) {
        let start = chinese.indexOf(pattern);
        while (start !== -1) {
          chineseCandidates.push(span(chinese, start, start + pattern.length));
          start = chinese.indexOf(pattern, start + 1);
        }
      }
      chineseCandidates.sort((a, b) => (b.end - b.start) - (a.end - a.start) || a.start - b.start);
      const chineseSpans = [];
      for (const s of chineseCandidates) {
        if (!chineseSpans.some(p => overlaps(p, s))) chineseSpans.push(s);
      }
      return chineseSpans;
    });
    return selected.map(({entry, english: englishSpan}, index) => {
      const possible = claims[index];
      // Multiple occurrences or competing entries are ambiguous, never priority-assigned.
      const unambiguous = possible.length === 1 && !claims.some((other, otherIndex) =>
        otherIndex !== index && other.some(s => overlaps(s, possible[0])));
      return {id: entry.id, kind: entry.kind, term: entry.term, meaning: entry.meaning, note: entry.note,
        english: englishSpan, chinese: unambiguous ? possible : [],
        warning: entry.badMatcher && entry.badMatcher.test(chinese) ? entry.warning : ''};
    }).sort((a, b) => a.english.start - b.english.start);
  }

  function annotateCues(cues, {known = []} = {}) {
    // Pass the complete video once, then reuse these rows in every page/current/shadow view.
    // Counts belong to this invocation only; spelling/inflection variants share entry.id.
    const rowCounts = new Map(), knownIds = new Set(known);
    return cues.map((cue, index) => {
      const context = cues.slice(Math.max(0, index - 2), index + 2)
        .filter((_, offset) => Math.max(0, index - 2) + offset !== index)
        .map(row => asText(row.english).slice(0, 600)).join('\n');
      const learning = analyzeAvailablePair(cue.english, cue.chinese, context, rowCounts, knownIds);
      // Selection has at most one item per ID per row, regardless of repeated mentions.
      for (const item of learning) rowCounts.set(item.id, (rowCounts.get(item.id) || 0) + 1);
      return {...cue, learning};
    });
  }
  return {analyzePair, annotateCues};
});
