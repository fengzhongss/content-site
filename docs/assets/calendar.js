(function(){let data={},curDate=new Date(),activePopup=null;
function init(){
  let b=document.createElement('button');b.id='cal-toggle';b.textContent='📅';b.title='内容日历';b.onclick=toggle;document.body.appendChild(b);
  let w=document.createElement('div');w.id='cal-widget';
  w.innerHTML=`<div class="cal-w-header"><button onclick="window.__cp()">&lt;</button><span class="cal-w-title" id="cwt"></span><button onclick="window.__cn()">&gt;</button></div><table class="cal-w-grid"><thead><tr><th>日</th><th>一</th><th>二</th><th>三</th><th>四</th><th>五</th><th>六</th></tr></thead><tbody id="cwb"></tbody></table><div class="cal-w-popup" id="cwp"><span class="cal-w-popup-close" onclick="window.__cc()">✕</span><h4 id="cwpd"></h4><div id="cwpl"></div></div>`;
  document.body.appendChild(w);
  window.__cp=()=>{curDate.setMonth(curDate.getMonth()-1);render()};
  window.__cn=()=>{curDate.setMonth(curDate.getMonth()+1);render()};
  window.__cc=()=>{let p=document.getElementById('cwp');if(p)p.style.display='none'};
  fetch('/assets/calendar-data.json').then(r=>r.ok?r.json():null).then(d=>{if(d){data=d;render()}}).catch(()=>{});
  document.addEventListener('click',function(e){let w=document.getElementById('cal-widget'),b=document.getElementById('cal-toggle');if(!w||!b)return;if(w.classList.contains('cal-open')&&!w.contains(e.target)&&!b.contains(e.target)){closeCal()}});
}
function render(){
  let y=curDate.getFullYear(),m=curDate.getMonth();
  document.getElementById('cwt').textContent=y+'年'+(m+1)+'月';
  let fd=new Date(y,m,1).getDay(),dim=new Date(y,m+1,0).getDate(),td=new Date(),h='<tr>';
  for(let i=0;i<fd;i++)h+='<td class="cal-w-empty"></td>';
  for(let d=1;d<=dim;d++){
    let ds=y+'-'+String(m+1).padStart(2,'0')+'-'+String(d).padStart(2,'0');
    let has=data[ds]&&data[ds].length>0,isT=d===td.getDate()&&m===td.getMonth()&&y===td.getFullYear();
    let cls='cal-w-cell';if(isT)cls+=' cal-w-today';if(has)cls+=' cal-w-has';
    h+=`<td class="${cls}" onclick="window.__ck('${ds}')"><span class="cal-w-num">${d}</span>${has?'<span class="cal-w-dot"></span>':''}</td>`;
    if((fd+d)%7===0&&d<dim)h+='</tr><tr>';
  }
  h+='</tr>';document.getElementById('cwb').innerHTML=h;
}
window.__ck=function(ds){
  let a=data[ds],pop=document.getElementById('cwp');
  if(!a||!a.length){pop.style.display='none';return}
  document.getElementById('cwpd').textContent=ds;
  let l='';for(let x of a)l+=`<a href="/${x.path}">${x.title}</a>`;
  document.getElementById('cwpl').innerHTML=l;pop.style.display='block';
  if(activePopup!==ds){document.addEventListener('click',function e2(ev){let p=document.getElementById('cwp');if(p&&!p.contains(ev.target)&&ev.target.id!=='cal-toggle'){p.style.display='none';activePopup=null;document.removeEventListener('click',e2)}},{once:true});activePopup=ds}
};
function closeCal(){let w=document.getElementById('cal-widget'),b=document.getElementById('cal-toggle');w.classList.remove('cal-open');b.classList.remove('cal-open');let p=document.getElementById('cwp');if(p)p.style.display='none'}
function toggle(){let w=document.getElementById('cal-widget'),b=document.getElementById('cal-toggle');if(w.classList.contains('cal-open')){closeCal()}else{w.classList.add('cal-open');b.classList.add('cal-open');render()}}
document.readyState==='complete'?init():window.addEventListener('load',init);
})();
