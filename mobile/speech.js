(function(root) {
    'use strict';
    function create(button, status) {
        let generation = 0, utterance = null, active = false;
        const synth = root.speechSynthesis;
        const supported = !!(synth && root.SpeechSynthesisUtterance);
        function reset(message) { active=false; utterance=null; button.textContent='Vorlesen'; button.setAttribute('aria-pressed','false'); status.textContent=message; }
        function stop() { generation++; if(supported) synth.cancel(); reset('Vorlesen gestoppt.'); }
        function speak(text) {
            if(!supported) { reset('Dieser Browser bietet keine Sprachausgabe.'); return; }
            if(active) { stop(); return; }
            const parts=[];
            for(let sentence of String(text||'').split(/(?<=[.!?])\s+|\n+/).filter(Boolean)) {
                while(sentence.length>180) {
                    const space=sentence.lastIndexOf(' ',180), cut=space>0?space:180;
                    parts.push(sentence.slice(0,cut)); sentence=sentence.slice(cut).trimStart();
                }
                if(sentence) parts.push(sentence);
            }
            if(!parts.length) return;
            const id=++generation;
            active=true; button.textContent='Stopp'; button.setAttribute('aria-pressed','true'); status.textContent='Sprachausgabe wird gestartet …';
            function next() {
                if(id!==generation) return;
                if(!parts.length) { reset('Vorlesen beendet.'); return; }
                utterance=new root.SpeechSynthesisUtterance(parts.shift());
                utterance.lang='de-DE'; utterance.rate=.95;
                const voices=synth.getVoices(), german=voices.filter(v=>/^de(?:-|_)/i.test(v.lang));
                utterance.voice=german.find(v=>v.localService) || german[0] || null;
                utterance.onstart=()=>{if(id===generation) status.textContent='Vorlesen läuft.';};
                utterance.onend=()=>{if(id===generation) next();};
                utterance.onerror=e=>{
                    if(id!==generation) return;
                    generation++; synth.cancel();
                    reset(['not-allowed','audio-busy'].includes(e.error) ? 'Sprachausgabe blockiert. Bitte Tonfreigabe und Audioausgabe im Browser prüfen.' : 'Sprachausgabe nicht verfügbar. Bitte eine deutsche Systemstimme und die Audioausgabe prüfen.');
                };
                synth.speak(utterance);
            }
            synth.cancel(); next();
        }
        if(!supported) { button.disabled=true; status.textContent='Dieser Browser bietet keine Sprachausgabe.'; }
        root.addEventListener?.('pagehide',stop);
        return {speak, stop, supported};
    }
    if(typeof module==='object' && module.exports) module.exports={create}; else root.GuideSpeech={create};
})(typeof globalThis!=='undefined'?globalThis:window);
