(function(){
  var rm = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* theme: init from storage / system, persist */
  var root = document.documentElement;
  var saved = null; try{ saved = localStorage.getItem('yendari-theme'); }catch(e){}
  if(saved){ root.setAttribute('data-theme', saved); }
  else if(window.matchMedia('(prefers-color-scheme: light)').matches){ root.setAttribute('data-theme','light'); }
  function syncTheme(){
    var light = root.getAttribute('data-theme')==='light';
    var btn = document.getElementById('themeToggle');
    btn.querySelector('[data-icon="moon"]').style.display = light ? 'none':'block';
    btn.querySelector('[data-icon="sun"]').style.display  = light ? 'block':'none';
    btn.setAttribute('aria-label', light ? 'Switch to dark theme':'Switch to light theme');
  }
  syncTheme();
  document.getElementById('themeToggle').addEventListener('click', function(){
    var light = root.getAttribute('data-theme')==='light';
    root.setAttribute('data-theme', light ? 'dark':'light');
    try{ localStorage.setItem('yendari-theme', light ? 'dark':'light'); }catch(e){}
    syncTheme();
  });

  /* sticky header condense */
  var header = document.getElementById('header');
  function onScroll(){ header.classList.toggle('is-scrolled', window.scrollY > 8); }
  onScroll(); window.addEventListener('scroll', onScroll, {passive:true});

  /* language menu */
  var menu = document.getElementById('langMenu');
  var menuBtn = menu.querySelector('[data-menu-btn]');
  menuBtn.addEventListener('click', function(e){
    e.stopPropagation();
    var open = menu.classList.toggle('open');
    menuBtn.setAttribute('aria-expanded', open ? 'true':'false');
  });
  menu.querySelectorAll('[data-lang]').forEach(function(b){
    b.addEventListener('click', function(){
      menu.querySelectorAll('[data-lang]').forEach(function(x){ x.setAttribute('aria-checked','false'); });
      b.setAttribute('aria-checked','true');
      menu.querySelector('[data-lang-label]').textContent = b.getAttribute('data-lang');
      menu.classList.remove('open'); menuBtn.setAttribute('aria-expanded','false');
    });
  });
  document.addEventListener('click', function(){ menu.classList.remove('open'); menuBtn.setAttribute('aria-expanded','false'); });

  /* footer language pills + city filter (visual toggle) */
  function singleSelect(sel){
    document.querySelectorAll(sel).forEach(function(group){
      group.addEventListener('click', function(e){
        var b = e.target.closest('button'); if(!b) return;
        group.querySelectorAll('button').forEach(function(x){ x.setAttribute('aria-pressed','false'); });
        b.setAttribute('aria-pressed','true');
      });
    });
  }
  singleSelect('.lang-row'); singleSelect('.filter-chips');

  /* search: no backend yet — scroll to deals */
  document.getElementById('searchForm').addEventListener('submit', function(e){
    e.preventDefault();
    document.getElementById('deals').scrollIntoView({behavior: rm ? 'auto':'smooth', block:'start'});
  });

  /* reveal on scroll */
  var reveals = document.querySelectorAll('.reveal');
  if(rm || !('IntersectionObserver' in window)){
    reveals.forEach(function(el){ el.classList.add('in'); });
  } else {
    var io = new IntersectionObserver(function(entries){
      entries.forEach(function(en){ if(en.isIntersecting){ en.target.classList.add('in'); io.unobserve(en.target); } });
    }, {rootMargin:'0px 0px -8% 0px', threshold:.12});
    reveals.forEach(function(el){ io.observe(el); });
  }

  /* count-up stats */
  function countUp(el){
    var target = parseFloat(el.getAttribute('data-count'));
    var dec = parseInt(el.getAttribute('data-dec')||'0',10);
    var suffix = el.getAttribute('data-suffix')||'';
    if(rm){ el.textContent = (dec? target.toFixed(dec): target.toLocaleString('en-US'))+suffix; return; }
    var start = performance.now(), dur = 1100;
    function tick(now){
      var p = Math.min((now-start)/dur,1);
      var e = 1-Math.pow(1-p,3);
      var v = target*e;
      el.textContent = (dec? v.toFixed(dec) : Math.round(v).toLocaleString('en-US'))+suffix;
      if(p<1) requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  }
  var counters = document.querySelectorAll('[data-count]');
  if('IntersectionObserver' in window && !rm){
    var io2 = new IntersectionObserver(function(entries){
      entries.forEach(function(en){ if(en.isIntersecting){ countUp(en.target); io2.unobserve(en.target); } });
    },{threshold:.6});
    counters.forEach(function(el){ io2.observe(el); });
  } else { counters.forEach(countUp); }

  /* ROI simulator */
  var slider=document.getElementById('roiSlider');
  if(slider){
    var price=230000,
        roiYield=document.getElementById('roiYield'),
        roiRent=document.getElementById('roiRent'),
        roiVerdict=document.getElementById('roiVerdict');
    function roiUpdate(){
      var rent=+slider.value, y=rent*12/price*100, diff=y-4.5;
      roiYield.textContent=y.toFixed(1)+'%';
      roiRent.textContent='€'+rent.toLocaleString('en-US');
      roiVerdict.textContent=(diff>=0?'+':'')+diff.toFixed(1)+' pts '+(diff>=0?'above':'below')+' average';
      roiVerdict.style.color=diff>=0?'var(--pos-text)':'var(--text-3)';
    }
    slider.addEventListener('input',roiUpdate); roiUpdate();
  }

  /* lead form: validate email, show success state */
  var leadForm=document.getElementById('leadForm');
  if(leadForm){
    var emailF=document.getElementById('le-email'),
        ffEmail=document.getElementById('ff-email'),
        re=/^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    function validEmail(){ return re.test(emailF.value.trim()); }
    emailF.addEventListener('blur',function(){
      if(emailF.value.trim()===''){ ffEmail.classList.remove('invalid'); return; }
      ffEmail.classList.toggle('invalid',!validEmail());
    });
    emailF.addEventListener('input',function(){
      if(ffEmail.classList.contains('invalid') && validEmail()) ffEmail.classList.remove('invalid');
    });
    leadForm.addEventListener('submit',function(e){
      e.preventDefault();
      if(!validEmail()){ ffEmail.classList.add('invalid'); emailF.focus(); return; }
      var goalEl=leadForm.querySelector('input[name="le-goal"]:checked');
      var val=function(id){ var el=document.getElementById(id); return el?el.value:''; };
      var hp=leadForm.querySelector('[name="company"]');
      var payload={ email:emailF.value.trim(), phone:val('le-phone'), budget:val('le-budget'),
        timeline:val('le-timeline'), goal:goalEl?goalEl.value:'', company:hp?hp.value:'' };
      var btn=leadForm.querySelector('button[type="submit"]'); if(btn) btn.disabled=true;
      fetch('/home/api/lead',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)})
        .then(function(r){
          if(r.ok){
            document.getElementById('leadWrap').classList.add('is-sent');
            var done=document.querySelector('.form-done'); if(done) done.focus();
          } else { if(btn) btn.disabled=false; if(r.status!==429) ffEmail.classList.add('invalid'); }
        })
        .catch(function(){ if(btn) btn.disabled=false; });
    });
  }

  /* flagship CTA -> highlight the AL-licensed filter in deals */
  var alCta=document.getElementById('alCta'), alFilter=document.getElementById('alFilter');
  if(alCta && alFilter){
    alCta.addEventListener('click', function(){
      document.querySelectorAll('.filter-chips button').forEach(function(b){ b.setAttribute('aria-pressed','false'); });
      alFilter.setAttribute('aria-pressed','true');
    });
  }

  /* hero "today's top deal" — soft rotation of a few real listings */
  var topDeal=document.getElementById('topDeal');
  if(topDeal){
    var deals=(window.YENDARI_DEALS && window.YENDARI_DEALS.length) ? window.YENDARI_DEALS : [
      {img:'https://aicraftpin.com/img/3578', score:92, ring:'--pos', price:'€230,000', sub:'T2 · 85 m² · Bonfim, Porto', delta:'24% below market', al:false}
    ];
    var fcThumb=document.getElementById('fcThumb'),
        fcScore=document.getElementById('fcScore'),
        fcScoreNum=document.getElementById('fcScoreNum'),
        fcPrice=document.getElementById('fcPrice'),
        fcSub=document.getElementById('fcSub'),
        fcDeltaChip=document.getElementById('fcDelta'),
        fcDelta=fcDeltaChip.querySelector('.txt'),
        fcAl=document.getElementById('fcAl'),
        fcViz=document.getElementById('fcViz'),
        fcBar=document.getElementById('fcBar'),
        fcBarVal=document.getElementById('fcBarVal'),
        dots=Array.prototype.slice.call(topDeal.querySelectorAll('.fc-dots button')),
        idx=0, timer=null;
    function paint(d){
      fcThumb.src=d.img;
      fcScore.style.setProperty('--score', d.score);
      fcScore.style.setProperty('--ring-color', 'var('+d.ring+')');
      fcScore.setAttribute('aria-label', 'Deal score '+d.score+' out of 100');
      fcScoreNum.textContent=d.score;
      fcPrice.textContent=d.price;
      fcSub.textContent=d.sub;
      fcAl.style.display=d.al?'inline-flex':'none';
      // below-market hook + "vs area median" bar, derived from the delta string
      var m=/(\d+(?:\.\d+)?)/.exec(d.delta||''), pct=m?parseFloat(m[1]):0;
      fcDelta.textContent=d.delta||'';
      fcDeltaChip.style.display=d.delta?'inline-flex':'none';
      if(fcViz && fcBar){
        if(pct>0){ fcViz.style.display=''; fcBar.style.width=Math.max(6,100-pct)+'%'; if(fcBarVal) fcBarVal.textContent='−'+Math.round(pct)+'%'; }
        else { fcViz.style.display='none'; }
      }
      dots.forEach(function(b,k){ var on=k===idx; b.classList.toggle('active',on); b.setAttribute('aria-pressed', on?'true':'false'); });
    }
    function show(n){
      idx=(n+deals.length)%deals.length;
      if(rm){ paint(deals[idx]); return; }
      topDeal.style.opacity='.35';
      setTimeout(function(){ paint(deals[idx]); topDeal.style.opacity='1'; }, 170);
    }
    function restart(){ if(timer) clearInterval(timer); if(!rm) timer=setInterval(function(){ show(idx+1); }, 5200); }
    paint(deals[0]);
    dots.forEach(function(b,k){ b.addEventListener('click', function(){ show(k); restart(); }); });
    restart();
  }
})();
