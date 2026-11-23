/* Picture versions, voice variants and scene management (set aside, move, add). Everything is written to story.txt; no file is renamed or deleted. */
const goScene=sid=>{const el=document.querySelector(`section[data-scene="${sid}"]`);if(el)el.scrollIntoView({block:'start',behavior:SMOOTH})};
const setMark=(f,m,v)=>{f.dataset.m=v;m.status=v;stats();filt()};
function showVersion(f,m){const im=f.querySelector('img'),v=m.versions[m.vi];if(im)im.src=v.src;m.src=v.src;
  const c=f.querySelector('.vc');if(c)c.textContent=`${m.vi+1} / ${m.versions.length}${m.picked&&v.name===m.picked?' ✔':''}`}
function wireVersions(){
  $$('figure.shot').forEach(f=>{const id=f.dataset.id,m=BL.flatMap(b=>b.images).find(x=>x.id===id);if(!m)return;
    /* the ✅ button chooses the picture that is shown (choosing = approving); with no picture it is the old plain mark */
    const ok=f.querySelector('button[data-m=ok]');
    if(ok)ok.onclick=async()=>{try{
      if(m.versions.length){
        if(f.dataset.m==='ok'){await api('/api/image',{id,pick:'',status:''});m.picked='';setMark(f,m,'')}
        else{const name=m.versions[m.vi].name;await api('/api/image',{id,pick:name});m.picked=name;setMark(f,m,'ok')}
        showVersion(f,m)}
      else{const v=f.dataset.m==='ok'?'':'ok';await api('/api/image',{id,status:v});setMark(f,m,v)}}catch(e){fail(e)}};
    /* ◀ ▶ browse the versions; the one you stop on is the chosen (approved) one */
    f.querySelectorAll('[data-vn]').forEach(b=>b.onclick=async()=>{try{const n=m.versions.length,ni=(m.vi+(+b.dataset.vn)+n)%n,name=m.versions[ni].name;
      await api('/api/image',{id,pick:name});m.vi=ni;m.picked=name;setMark(f,m,'ok');showVersion(f,m)}catch(e){fail(e)}});
    const off=f.querySelector('[data-ioff]');
    if(off)off.onclick=async()=>{try{await api('/api/image',{id,off:!m.off});await reload()}catch(e){fail(e)}}});
  $$('section[data-scene]').forEach(s=>{const sid=s.dataset.scene;
    s.querySelectorAll('[data-smv]').forEach(b=>b.onclick=async()=>{try{await api('/api/scenemove',{scene:sid,step:+b.dataset.smv});await reload();goScene(sid)}catch(e){fail(e)}});
    s.querySelectorAll('[data-soff]').forEach(b=>b.onclick=async()=>{if(!confirm('این صحنه کنار گذاشته بشه؟\nمتن، عکس‌ها و صداهاش پاک نمی‌شن؛ فقط از ترتیب نهایی بیرون می‌ره و هوش مصنوعی نادیده‌اش می‌گیره.'))return;
      try{await api('/api/sceneoff',{scene:sid,off:true});await reload()}catch(e){fail(e)}});
    s.querySelectorAll('[data-son]').forEach(b=>b.onclick=async()=>{try{await api('/api/sceneoff',{scene:sid,off:false});await reload();goScene(sid)}catch(e){fail(e)}})});
  $$('[data-addscene]').forEach(b=>b.onclick=async()=>{const title=prompt('عنوان صحنهٔ جدید؟','صحنهٔ جدید');if(title===null)return;
    const n=prompt('چند جای خالی برای تصویر داشته باشه؟ (۰ تا ۱۲)','1');if(n===null)return;
    try{const r=await api('/api/addscene',{after:b.dataset.addscene,title,images:+n||0});await reload();goScene(r.scene)}catch(e){fail(e)}})}
/* the small ‹1/2› next to a voice button: next voice of that line; the one you stop on becomes the chosen (final) voice */
document.addEventListener('click',async e=>{const b=e.target.closest('.vv');if(!b)return;
  const lg=b.dataset.vv,iid=b.dataset.iid,it=BL.flatMap(x=>x.items).find(x=>x.id===iid);if(!it)return;
  const v=it.audio_v[lg],i=(v.names.indexOf(v.chosen)+1)%v.names.length,name=v.names[i];
  try{await api('/api/voicepick',{scene:b.dataset.sc,id:iid,lang:lg,variant:name})}catch(err){return fail(err)}
  v.chosen=name;const url=(name==='default'?`audio/${lg}/${iid}.mp3`:`audio/${lg}/${iid}.${name}.mp3`)+'?v='+Date.now();it.audio[lg]=url;
  const play=b.parentElement.querySelector(`.ab[data-lg="${lg}"]`);play.dataset.src=url;b.textContent=`‹${i+1}/${v.names.length}›`;
  b.title=`${lg==='fa'?'صدای فارسی':'English voice'}: ${name} · کلیک = صدای بعدی (همونی که آخر می‌ذاری، صدای نهایی می‌شه)`;stopLine();play.click()});
