(function (root) {
    'use strict';
    const MAX_JSON = 32000, MAX_URL = 1900;
    const plain = value => String(value || '').replace(/\*\*/g, '').replace(/<!--.*?-->/gs, '').trim();
    const escape = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

    function fromResponse(response, question) {
        const results = response.results || [];
        const steps = [], intros = [];
        for (const item of results) {
            for (const line of String(item.content || '').split('\n').map(s => s.trim()).filter(Boolean)) {
                if (/^[-*]\s*\[\s*\]/.test(line)) {
                    steps.push(plain(line.replace(/^[-*]\s*\[\s*\]\s*/, '')));
                } else intros.push(plain(line));
            }
        }
        return validate({v:1, question:plain(question), summary:plain(response.tts_summary),
            intro:intros.join('\n'), steps,
            references:[...new Set(results.map(r => plain(r.reference)).filter(Boolean))],
            date:new Date().toISOString().slice(0, 10)});
    }

    function validate(data) {
        if (!data || data.v !== 1 || !Array.isArray(data.steps) || !Array.isArray(data.references) ||
            data.steps.length > 80 || data.references.length > 10) throw new Error('Ungültige Anleitung.');
        for (const key of ['question','summary','intro','date']) {
            if (typeof data[key] !== 'string' || data[key].length > 12000) throw new Error('Ungültiger Anleitungstext.');
        }
        if (![...data.steps, ...data.references].every(v => typeof v === 'string' && v.length <= 12000)) throw new Error('Ungültige Schritte.');
        const clean = {v:1, question:data.question, summary:data.summary, intro:data.intro,
            steps:data.steps.slice(), references:data.references.slice(), date:data.date};
        const json = JSON.stringify(clean);
        if (new TextEncoder().encode(json).length > MAX_JSON) throw new Error('Die Anleitung ist zu lang.');
        if (/\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{20,}/.test(json)) throw new Error('Inhalte mit einem API-Schlüssel werden nicht geteilt.');
        return clean;
    }

    async function readLimited(stream, limit) {
        const reader = stream.getReader(), chunks = []; let size = 0;
        try {
            for (;;) {
                const {done, value} = await reader.read(); if (done) break;
                size += value.length;
                if (size > limit) { await reader.cancel(); throw new Error('Die Anleitung ist zu groß.'); }
                chunks.push(value);
            }
        } finally { reader.releaseLock(); }
        const out = new Uint8Array(size); let offset = 0;
        for (const chunk of chunks) { out.set(chunk, offset); offset += chunk.length; }
        return out;
    }

    async function makeUrl(base, data) {
        const url = new URL(base);
        if (url.protocol !== 'https:' && !['localhost','127.0.0.1','[::1]'].includes(url.hostname)) throw new Error('Die Leseseite muss HTTPS verwenden.');
        if (!root.CompressionStream) throw new Error('Dieser Browser unterstützt keine kompakten QR-Links. Bitte HTML-Datei speichern.');
        const encoded = new TextEncoder().encode(JSON.stringify(validate(data)));
        const bytes = await readLimited(new Blob([encoded]).stream().pipeThrough(new CompressionStream('gzip')), MAX_JSON);
        let binary = ''; for (const byte of bytes) binary += String.fromCharCode(byte);
        const payload = btoa(binary).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'');
        url.search = ''; url.hash = 'g1.' + payload;
        if (url.href.length > MAX_URL) throw new Error('Die vollständige Antwort ist für einen gut lesbaren QR-Code zu lang. Bitte die HTML-Anleitung speichern und auf das Handy übertragen. Es wird nichts gekürzt.');
        return url.href;
    }

    async function decode(hash) {
        if (!/^#g1\.[A-Za-z0-9_-]+$/.test(hash) || hash.length > 4096) throw new Error('Dieser QR-Link enthält keine gültige Anleitung.');
        if (!root.DecompressionStream) throw new Error('Bitte einen aktuellen Browser verwenden.');
        const binary = atob(hash.slice(4).replace(/-/g,'+').replace(/_/g,'/'));
        const bytes = Uint8Array.from(binary, c => c.charCodeAt(0));
        const plainBytes = await readLimited(new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip')), MAX_JSON);
        return validate(JSON.parse(new TextDecoder('utf-8', {fatal:true}).decode(plainBytes)));
    }

    const drawings = {
        water:'<path d="M9 19h22v8H19v9h-8V25H9zM20 10v9m-7-9h14"/><path d="M30 33c-6 7-6 11 0 11s6-4 0-11z"/>',
        plug:'<path d="M17 7v12m14-12v12M12 19h24v6a12 12 0 0 1-24 0zM24 37v10"/>',
        cool:'<path d="M23 8a5 5 0 0 1 10 0v25a9 9 0 1 1-10 0zM28 19v21M12 14h4m-4 8h4"/>',
        service:'<path d="M13 8l8 9-5 5c4 7 7 10 14 14l5-5 9 8c-7 12-20 2-28-6S1 13 13 8z"/>',
        clean:'<path d="M30 8l9 8-17 18-10-9zM12 25l-5 11 11 9 5-11M11 32l8 7M8 39l5 4M38 29v9m-4-4h8"/>',
        info:'<circle cx="25" cy="25" r="19"/><path d="M25 23v14M25 14v2"/>',
    };
    function icon(text) {
        const kind = /abkühlen|heiß|Verbrüh/i.test(text) ? 'cool' : /Netzstecker|Stromnetz|ausschalten/i.test(text) ? 'plug' :
            /Wasserhahn/i.test(text) ? 'water' : /Kundendienst/i.test(text) ? 'service' : /reinigen/i.test(text) ? 'clean' : 'info';
        return '<svg viewBox="0 0 50 50" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round">' + drawings[kind] + '</svg>';
    }
    const css = `[hidden]{display:none!important}:root{color-scheme:light}*{box-sizing:border-box}body{margin:0;background:#f5f8f8;color:#18323c;font:17px/1.65 system-ui,sans-serif}main{max-width:760px;margin:auto;padding:32px 20px 64px}.eyebrow{font-size:12px;letter-spacing:.16em;font-weight:750;color:#087b80}h1{font-size:clamp(27px,7vw,40px);line-height:1.2;margin:12px 0 20px}h2{font-size:20px}p{margin:12px 0}.summary{font-size:20px}.intro,.step p{white-space:pre-wrap}.steps{list-style:none;padding:0;counter-reset:step}.step{position:relative;display:grid;grid-template-columns:52px 1fr;gap:16px;margin:18px 0;padding:22px 18px;background:white;border:1px solid #d7e2e4;border-radius:14px;counter-increment:step}.step svg{width:46px;height:46px;color:#007c83}.step p{margin:4px 0 14px}.step h2{font-size:13px;letter-spacing:.12em;color:#527078;margin:0}.step:has(input:checked){border-color:#16867e;background:#edf8f5}.step:has(input:checked) p{opacity:.7}label{font-size:14px;color:#43606a;display:flex;gap:9px;align-items:center}input{width:21px;height:21px;accent-color:#007c83}.warning{border-left:4px solid #b67a16}.reference,.note{font-size:13px;color:#587079}.note{padding-top:16px;border-top:1px solid #d4dfe0}button,a.button{font:inherit;padding:10px 16px;border:1px solid #007c83;border-radius:7px;color:#006b72;background:white;text-decoration:none;cursor:pointer}.actions{display:flex;gap:10px;flex-wrap:wrap;margin:24px 0}#status{min-height:1.6em;font-size:14px}#progress{font-size:14px;color:#007c83}@media print{body{background:white}main{max-width:none;padding:0}.actions,#status{display:none}.step{break-inside:avoid;box-shadow:none}}`;
    function render(data) {
        data = validate(data);
        return '<p class="eyebrow">WASCHMASCHINEN-ASSISTENT · ANLEITUNG</p><h1>' + escape(data.question || 'Hinweise aus dem Handbuch') + '</h1>' +
            '<p class="summary">' + escape(data.summary) + '</p><p class="intro">' + escape(data.intro) + '</p>' +
            '<p id="progress"></p><ol class="steps">' + data.steps.map((text,index) => '<li class="step' + (/Warnung|Gefahr|abkühlen|Netzstecker/i.test(text) ? ' warning' : '') + '">' + icon(text) + '<div><h2>Schritt ' + (index+1) + '</h2><p>' + escape(text.replace(/^Schritt\s+\d+\s*:\s*/i,'')) + '</p><label><input type="checkbox"> Erledigt</label></div></li>').join('') + '</ol>' +
            '<section class="reference"><h2>Quellenhinweis</h2>' + data.references.map(ref => '<p>' + escape(ref) + '</p>').join('') + '<p>Erstellt am ' + escape(data.date) + '</p></section>' +
            '<p class="note">Diese Ansicht übernimmt den Inhalt der erzeugten Antwort. Symbole dienen der Orientierung und zeigen keine gerätespezifischen Bauteile. Prüfen Sie die Bedienungsanleitung Ihres Geräts und beachten Sie deren Sicherheits- und Kundendiensthinweise.</p>';
    }
    function speechText(data) {
        return [data.summary, data.intro, ...data.steps.map((text,i) => `Schritt ${i+1}. ${text.replace(/^Schritt\s+\d+\s*:\s*/i,'')}`)].filter(Boolean).join('\n');
    }
    function portableHTML(data) {
        return '<!doctype html><html lang="de"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="referrer" content="no-referrer"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; img-src data:; base-uri \'none\'"><title>Waschmaschinen-Anleitung</title><style>'+css+'</style><main>'+render(data)+'</main></html>';
    }
    const api = {fromResponse, validate, makeUrl, decode, render, css, speechText, portableHTML, MAX_URL};
    if (typeof module === 'object' && module.exports) module.exports = api; else root.AnswerGuide = api;
})(typeof globalThis !== 'undefined' ? globalThis : window);
