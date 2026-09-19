const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const Guide = require('../mobile/guide.js');

function frontend() {
    const elements = new Map();
    const element = () => ({style: {}, children: [], innerHTML: '',
        appendChild(child) { this.children.push(child); },
        append(...children) { this.children.push(...children); },
        addEventListener() {}});
    const document = {
        getElementById(id) {
            if (!elements.has(id)) elements.set(id, element());
            return elements.get(id);
        },
        createElement: element,
        querySelector: () => element(),
        addEventListener() {},
    };
    const context = vm.createContext({document, window: {},
        location: {protocol: 'http:', origin: 'http://127.0.0.1:3001'},
        AnswerGuide: Guide, GuideSpeech: {create: () => ({stop() {}})}});
    const html = fs.readFileSync(require.resolve('../index.html'), 'utf8');
    for (const script of html.matchAll(/<script>([\s\S]*?)<\/script>/g)) {
        vm.runInContext(script[1], context);
    }
    return {context, elements};
}

test('summary-only model responses are visible, escaped, and not empty cards', () => {
    const {context, elements} = frontend();
    context.renderResults({tts_summary: 'E:23: Wasserhahn schließen. <script>bad()</script>',
        results: [{title: 'Handbuch', content: '', sourceType: 'manual'}]}, '', 'E:23');
    const card = elements.get('results-list').children[0].innerHTML;
    assert.match(card, /Wasserhahn schließen/);
    assert.match(card, /&lt;script&gt;bad\(\)&lt;\/script&gt;/);
    assert.doesNotMatch(card, /<script>/);
});

test('a full answer retains the detailed steps instead of the summary fallback', () => {
    const {context, elements} = frontend();
    context.renderResults({tts_summary: 'Kurze Zusammenfassung',
        results: [{title: 'Handbuch', content: '- [ ] Wasserhahn schließen.', sourceType: 'manual'}]}, '', 'E:23');
    const card = elements.get('results-list').children[0].innerHTML;
    assert.match(card, /Wasserhahn schließen/);
    assert.match(card, /type="checkbox"/);
    assert.doesNotMatch(card, /Kurze Zusammenfassung/);
});

test('the reformulated search is visible as text alongside the original answer', () => {
    const {context, elements} = frontend();
    context.renderResults({tts_summary: 'Wasser läuft aus', search_query: 'Wasser <läuft> aus',
        results: [{title: 'Handbuch', content: 'Ablaufschlauch prüfen.', sourceType: 'manual'}]}, '', 'Wasser schießt aus der Maxchine');
    assert.match(elements.get('results-list').children[0].textContent || '', /Wasser <läuft> aus/);
});
