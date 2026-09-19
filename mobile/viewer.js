'use strict';
window.addEventListener('hashchange',()=>location.reload());
(async()=>{
  const style=document.createElement('style'); style.textContent=AnswerGuide.css; document.head.append(style);
  const status=document.getElementById('status'), content=document.getElementById('content');
  if(!location.hash) return;
  try {
    const data=await AnswerGuide.decode(location.hash);
    content.innerHTML=AnswerGuide.render(data);
    document.getElementById('welcome').hidden=true;
    document.getElementById('actions').hidden=false;
    const speech=GuideSpeech.create(document.getElementById('speak'),status);
    document.getElementById('speak').onclick=()=>speech.speak(AnswerGuide.speechText(data));
    document.getElementById('print').onclick=()=>window.print();
    document.getElementById('save').onclick=()=>{
      const blob=new Blob([AnswerGuide.portableHTML(data)],{type:'text/html;charset=utf-8'});
      const url=URL.createObjectURL(blob), link=document.createElement('a');
      link.href=url; link.download='Waschmaschinen-Anleitung.html'; link.click();
      setTimeout(()=>URL.revokeObjectURL(url),10000);
    };
    function progress(){const boxes=[...content.querySelectorAll('input[type=checkbox]')]; document.getElementById('progress').textContent=boxes.length?`${boxes.filter(b=>b.checked).length} von ${boxes.length} Schritten erledigt`:'';}
    content.addEventListener('change',progress); progress();
  } catch(error) { status.textContent=error.message || 'Die Anleitung konnte nicht geladen werden.'; }
})();
