(function () {
  document.documentElement.classList.add('js');
  var reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var desktop = window.matchMedia('(min-width: 961px)');

  /* ---------- Hero code typing (works even if CDNs fail) ---------- */
  var source = [
    ['f','Presence'],['\n'],
    ['You mentioned moving the queue consumers\nto GCP. What broke first?\n\n'],
    ['k','Candidate'],['\n'],
    ['Ordering. We had assumed one worker per\npartition, and autoscaling broke that, so we\nadded idempotency keys.\n\n'],
    ['f','Presence'],['\n'],
    ['How did you test that the fix held?']
  ];
  var typedEl = document.getElementById('typed');
  var tests = document.querySelectorAll('#tests .t');
  function esc(s){return s.replace(/&/g,'&amp;').replace(/</g,'&lt;')}
  function render(n){
    var html='',count=0;
    for(var i=0;i<source.length&&count<n;i++){
      var kind=source[i].length===2?source[i][0]:null;
      var txt=source[i].length===2?source[i][1]:source[i][0];
      var take=txt.slice(0,n-count); count+=take.length;
      html+= kind? '<span class="c-'+kind+'">'+esc(take)+'</span>' : esc(take);
    }
    typedEl.innerHTML=html;
  }
  var total=source.reduce(function(a,s){return a+(s.length===2?s[1]:s[0]).length},0);
  if(reduce){ render(total); tests.forEach(function(t){t.classList.add('done')}); document.getElementById('note').classList.add('show'); }
  else {
    var n=0, started=false;
    function tick(){
      n+=2; render(Math.min(n,total));
      if(n<total){ setTimeout(tick, 22); }
      else { tests.forEach(function(t,i){ setTimeout(function(){t.classList.add('done')}, 400+i*450); }); setTimeout(function(){document.getElementById('note').classList.add('show')},400+tests.length*450+300); }
    }
    setTimeout(function(){ if(!started){started=true;tick();} }, 900);
  }

  if (typeof gsap === 'undefined') {            // CDN blocked: show everything plainly
    document.querySelectorAll('.reveal-up').forEach(function(e){e.style.opacity=1;e.style.transform='none'});
    document.querySelectorAll('.split-words').forEach(function(e){e.style.opacity=1});
    return;
  }
  gsap.registerPlugin(ScrollTrigger);

  /* ---------- Smooth scroll ---------- */
  var lenis = null;
  if (!reduce && typeof Lenis !== 'undefined') {
    lenis = new Lenis({ duration: 1.15, easing: function(t){return Math.min(1,1.001-Math.pow(2,-10*t))} });
    lenis.on('scroll', ScrollTrigger.update);
    gsap.ticker.add(function(t){ lenis.raf(t*1000) });
    gsap.ticker.lagSmoothing(0);
    document.querySelectorAll('a[href^="#"]').forEach(function(a){
      a.addEventListener('click', function(e){
        var id=a.getAttribute('href'); if(id.length<2) return;
        var el=document.querySelector(id); if(!el) return;
        e.preventDefault(); lenis.scrollTo(el,{offset:id==='#platform'?0:-10});
      });
    });
  }

  /* ---------- Nav behaviour ---------- */
  var nav=document.getElementById('nav'), lastY=0;
  ScrollTrigger.create({ start:0, end:'max', onUpdate:function(self){
    var y=self.scroll();
    nav.classList.toggle('scrolled', y>30);
    nav.classList.toggle('hide', y>lastY && y>400);
    lastY=y;
  }});

  /* ---------- Hero intro ---------- */
  if(!reduce){
    var tl=gsap.timeline({defaults:{ease:'power4.out'}});
    tl.from('.line-in',{yPercent:110,duration:1.2,stagger:.12})
      .to('.reveal-up',{opacity:1,y:0,duration:1,stagger:.12},'-=.8');
    gsap.to('.hero-editor',{yPercent:-6,ease:'none',scrollTrigger:{trigger:'.hero',start:'top top',end:'bottom top',scrub:true}});
  } else {
    gsap.set('.reveal-up',{opacity:1,y:0});
  }

  /* ---------- Word-by-word scroll reveal ---------- */
  document.querySelectorAll('.split-words').forEach(function(el){
    var words=el.textContent.trim().split(/\s+/);
    el.innerHTML=words.map(function(w){return '<span class="w">'+w+'</span>'}).join(' ');
    if(reduce) return;
    var onDark = el.classList.contains('on-dark');
    gsap.to(el.querySelectorAll('.w'),{
      opacity:1, stagger:.08, ease:'none',
      scrollTrigger:{trigger:el,start:'top 82%',end:'bottom 45%',scrub:true}
    });
  });

  /* ---------- Pinned story ---------- */
  var steps=document.querySelectorAll('.story-steps li');
  var scenes=document.querySelectorAll('.scene');
  var numEl=document.getElementById('storyNum');
  var current=-1;
  function setStep(i){
    if(i===current) return; current=i;
    steps.forEach(function(s,k){s.classList.toggle('active',k===i)});
    scenes.forEach(function(s,k){s.classList.toggle('on',k===i)});
    numEl.textContent='0'+(i+1);
  }
  setStep(0);
  ScrollTrigger.matchMedia({
    '(min-width: 961px)': function(){
      if(reduce) return;
      ScrollTrigger.create({
        trigger:'.story-pin', start:'top top', end:'+=240%', pin:true, scrub:true,
        onUpdate:function(self){ setStep(Math.min(3,Math.floor(self.progress*4))); }
      });
    },
    '(max-width: 960px)': function(){
      // stacked layout: advance scenes as each step scrolls into view
      steps.forEach(function(s,i){
        ScrollTrigger.create({trigger:s,start:'top 60%',end:'bottom 60%',onToggle:function(self){ if(self.isActive) setStep(i); }});
      });
    }
  });

  /* ---------- Rows + lists ---------- */
  if(!reduce){
    gsap.from('.rl',{opacity:0,y:40,stagger:.1,duration:.9,ease:'power3.out',scrollTrigger:{trigger:'.rowlist',start:'top 80%'}});
    gsap.from('.ticks li',{opacity:0,y:20,stagger:.08,duration:.7,ease:'power3.out',scrollTrigger:{trigger:'.audience',start:'top 70%'}});
    gsap.from('.aud-rule',{scaleY:0,transformOrigin:'top',duration:1.2,ease:'power3.out',scrollTrigger:{trigger:'.audience',start:'top 70%'}});
    gsap.from('.form > *',{opacity:0,y:24,stagger:.08,duration:.8,ease:'power3.out',scrollTrigger:{trigger:'.form',start:'top 85%'}});
    gsap.from('.foot-word',{yPercent:40,duration:1.4,ease:'power4.out',scrollTrigger:{trigger:'.footer',start:'top 90%'}});
  }

  /* ---------- Integrity icons draw on view ---------- */
  document.querySelectorAll('.int-list li').forEach(function(li){
    ScrollTrigger.create({trigger:li,start:'top 82%',once:true,onEnter:function(){li.classList.add('in')}});
    if(!reduce) gsap.from(li,{opacity:0,x:30,duration:.9,ease:'power3.out',scrollTrigger:{trigger:li,start:'top 88%'}});
  });
  document.querySelectorAll('.int-list .draw').forEach(function(p){
    if(p.getTotalLength){ var L=Math.ceil(p.getTotalLength()); p.style.setProperty('--len',L); }
  });
  document.querySelectorAll('.pair-board .draw').forEach(function(p){
    if(p.getTotalLength){ p.style.setProperty('--len',Math.ceil(p.getTotalLength())+2); }
  });

  /* ---------- Demo form ---------- */
  var form=document.getElementById('demoForm');
  if(form){
    form.addEventListener('submit',function(e){
      e.preventDefault();
      form.classList.remove('error'); form.classList.add('sending');
      fetch('https://formsubmit.co/ajax/ashishkaranam06@gmail.com',{
        method:'POST',headers:{'Accept':'application/json'},body:new FormData(form)
      }).then(function(r){return r.json()}).then(function(j){
        form.classList.remove('sending');
        if(j.success===true||j.success==='true'){form.classList.add('sent');form.reset();}
        else form.classList.add('error');
      }).catch(function(){form.classList.remove('sending');form.classList.add('error');});
    });
  }

  /* ---------- Scoring section ---------- */
  document.querySelectorAll('[data-block]').forEach(function(b){
    ScrollTrigger.create({trigger:b,start:'top 72%',once:true,onEnter:function(){b.classList.add('in')}});
  });
  var data={py:{A:1612,B:1574,C:1531,D:1498},mq:{C:1640,A:1587,D:1552,B:1490},aws:{B:1605,D:1570,A:1533,C:1501}};
  var rankEl=document.getElementById('rank');
  function ranked(skill){
    var d=data[skill], items=[].slice.call(rankEl.children);
    items.sort(function(x,y){return d[y.dataset.c]-d[x.dataset.c]});
    items.forEach(function(li,i){
      li.style.transform='translateY('+(i*64)+'px)';
      li.querySelector('.rk').textContent='0'+(i+1);
      li.querySelector('em').textContent=d[li.dataset.c];
      li.querySelector('.bar i').style.width=Math.round((d[li.dataset.c]-1350)/3.2)+'%';
      li.classList.toggle('top',i===0);
    });
  }
  var rankSeen=false;
  ranked('py');
  document.querySelectorAll('.tabs button').forEach(function(btn){
    btn.addEventListener('click',function(){
      document.querySelectorAll('.tabs button').forEach(function(x){x.classList.remove('on')});
      btn.classList.add('on'); ranked(btn.dataset.skill);
    });
  });

  window.addEventListener('load',function(){ScrollTrigger.refresh()});
})();
