/* Progressive enhancement: the build already supplies crawlable cards and pages. */
(function (root, factory) {
  'use strict';
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else {
    root.MangenJournal = api;
    if (root.document.readyState === 'loading') root.document.addEventListener('DOMContentLoaded', () => api.init(root));
    else api.init(root);
  }
})(typeof window !== 'undefined' ? window : globalThis, function () {
  'use strict';
  const escape = value => String(value || '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const normalize = value => String(value || '').normalize('NFKC').toLocaleLowerCase().trim();
  function readState(url) {
    const parsed = new URL(url, 'https://mangen.jp');
    const route = parsed.pathname.match(/^\/blog\/page\/(\d+)\/?$/);
    const page = Number(parsed.searchParams.get('page') || (route ? route[1] : 1));
    return {q:(parsed.searchParams.get('q') || '').trim().slice(0,200), destination:parsed.searchParams.get('destination') || '', topic:parsed.searchParams.get('topic') || '', page:Number.isSafeInteger(page) && page > 0 ? page : 1};
  }
  function isFiltered(state) { return Boolean(state.q || state.destination || state.topic); }
  function stateURL(state) {
    if (!isFiltered(state)) return state.page > 1 ? `/blog/page/${state.page}/` : '/blog/';
    const params = new URLSearchParams();
    ['q','destination','topic'].forEach(key => { if (state[key]) params.set(key,state[key]); });
    if (state.page > 1) params.set('page',state.page);
    return '/blog/?'+params.toString();
  }
  function filterPosts(posts, state) {
    const terms = normalize(state.q).split(/\s+/).filter(Boolean);
    return posts.filter(post => (!state.destination || post.destinations.includes(state.destination)) && (!state.topic || post.topic === state.topic) && terms.every(term => normalize([post.title,post.excerpt,post.search,post.topic,...post.destinations].join(' ')).includes(term)));
  }
  function paginate(posts, page, perPage) {
    const pages = Math.ceil(posts.length / perPage);
    page = Math.max(1,Math.min(Number.isSafeInteger(page) ? page : 1, pages || 1));
    return {items:posts.slice((page-1)*perPage,page*perPage),page,pages,total:posts.length};
  }
  function creditHTML(post) {
    const parts = [];
    if(post.coverCaption) parts.push(escape(post.coverCaption));
    [[post.coverCredit,post.coverCreatorUrl],[post.coverSource?'来源':'',post.coverSource],[post.coverLicense,post.coverLicenseUrl]].forEach(([label,url])=>{
      if(label) parts.push(url?`<a href="${escape(url)}" rel="noopener noreferrer">${escape(label)}</a>`:escape(label));
    });
    if(post.coverChanges) parts.push(escape(post.coverChanges));
    return parts.join(' · ');
  }
  function cardHTML(post) {
    const image = post.cover ? `<div class="guide-image"><img src="${escape(post.cover)}" alt="${escape(post.coverAlt)}" loading="lazy" decoding="async" width="900" height="600"></div>` : '';
    return `<article class="guide-entry"><a class="guide-card${image?'':' guide-card--text'}" href="${escape(post.url)}">${image}<div class="guide-copy"><div class="guide-taxonomy">${escape(post.destinations.join(' / '))}<span> · </span>${escape(post.topic)}</div><h3>${escape(post.title)}</h3><p>${escape(post.excerpt)}</p><time datetime="${escape(post.date)}">${escape(post.date.replace(/-/g,'.'))}</time></div></a>${image?`<p class="image-credit">${creditHTML(post)}</p>`:''}</article>`;
  }
  function paginationHTML(state, pages) {
    if (pages <= 1) return pages ? '<span class="page-summary">已显示全部指南</span>' : '';
    const link = (number,label,attrs='') => `<a href="${escape(stateURL({...state,page:number}))}" ${attrs}>${label}</a>`;
    let html = state.page > 1 ? link(state.page-1,'上一页','rel="prev"') : '<span aria-disabled="true">上一页</span>';
    const numbers = Array.from(new Set([1,pages,...Array.from({length:5},(_,i)=>state.page-2+i).filter(n=>n>0&&n<=pages)])).sort((a,b)=>a-b);
    let previous=0;
    numbers.forEach(number=>{
      if(previous && number>previous+1) html+='<span class="page-gap" aria-hidden="true">…</span>';
      html+=link(number,String(number),`aria-label="第 ${number} 页"${number===state.page?' aria-current="page"':''}`);
      previous=number;
    });
    return html + (state.page < pages ? link(state.page+1,'下一页','rel="next"') : '<span aria-disabled="true">下一页</span>');
  }
  function init(win) {
    const doc=win.document, main=doc.querySelector('[data-journal]');
    if (!main || main.dataset.enhanced) return;
    main.dataset.enhanced='true';
    const form=doc.querySelector('.journal-search'), input=doc.querySelector('#guide-search'), grid=doc.querySelector('#guide-grid');
    const pagination=doc.querySelector('#journal-pagination'), empty=doc.querySelector('#empty-state'), active=doc.querySelector('#active-filters'), status=doc.querySelector('#result-count'), error=doc.querySelector('#journal-error');
    let state=readState(win.location.href), catalog=null, pending=null;
    function updateMetadata() {
      const filtered=isFiltered(state);
      doc.querySelector('#journal-robots').content=filtered?'noindex,follow':'index,follow';
      const canonical='https://mangen.jp'+(filtered?'/blog/':stateURL(state));
      doc.querySelector('link[rel="canonical"]').href=canonical;
      doc.querySelector('meta[property="og:url"]').content=canonical;
      doc.title=(filtered?'搜索与筛选旅行指南':'日本旅行指南'+(state.page>1?` · 第 ${state.page} 页`:''))+' | 株式会社万源';
    }
    function reflectControls() {
      input.value=state.q;
      doc.querySelectorAll('[data-filter]').forEach(button=>button.setAttribute('aria-pressed',String(button.value===state[button.dataset.filter])));
      doc.querySelectorAll('[data-select]').forEach(select=>{select.value=state[select.dataset.select];});
    }
    function render() {
      const result=paginate(filterPosts(catalog.posts,state),state.page,catalog.perPage);
      state.page=result.page;
      grid.innerHTML=result.items.map(cardHTML).join('');
      empty.hidden=result.total!==0;
      pagination.innerHTML=paginationHTML(state,result.pages);
      status.textContent=`${isFiltered(state)?'找到':'共'} ${result.total} 篇指南`+(result.pages>1?` · 第 ${result.page} / ${result.pages} 页`:'');
      active.hidden=!isFiltered(state);
      active.querySelector('p').textContent=[state.q?`关键词：${state.q}`:'',state.destination,state.topic].filter(Boolean).join(' / ');
      const featured=doc.querySelector('#featured-section');
      if(featured) featured.hidden=isFiltered(state)||state.page!==1;
      reflectControls();updateMetadata();
    }
    async function load() {
      if(catalog) return catalog;
      if(!pending) pending=win.fetch('/blog/articles.json').then(response=>{
        if(!response.ok) throw new Error('catalog unavailable');
        return response.json();
      }).then(data=>{
        if(!Array.isArray(data.posts)||data.perPage!==12) throw new Error('invalid catalog');
        catalog=data; return data;
      }).catch(cause=>{pending=null;throw cause;});
      return pending;
    }
    async function apply(next, historyMode='push', focus=false) {
      state=next;
      reflectControls();updateMetadata();
      main.setAttribute('aria-busy','true');
      try {
        await load();render();error.hidden=true;
        const url=stateURL(state);
        if(historyMode==='push' && url!==win.location.pathname+win.location.search) win.history.pushState(null,'',url);
        else if(historyMode==='replace') win.history.replaceState(null,'',url);
        if(focus) doc.querySelector('#guides-title').focus({preventScroll:true});
      } catch (_) {
        error.hidden=false;error.textContent='搜索暂时无法载入，仍可直接阅读下面的指南。请稍后重试。';
      } finally {main.removeAttribute('aria-busy');}
    }
    form.addEventListener('submit',event=>{event.preventDefault();apply({...state,q:input.value.trim().slice(0,200),page:1});});
    doc.querySelectorAll('[data-filter]').forEach(button=>button.addEventListener('click',()=>apply({...state,[button.dataset.filter]:button.value,page:1})));
    doc.querySelectorAll('[data-select]').forEach(select=>select.addEventListener('change',()=>apply({...state,[select.dataset.select]:select.value,page:1})));
    doc.querySelectorAll('[data-clear]').forEach(button=>button.addEventListener('click',()=>apply({q:'',destination:'',topic:'',page:1},'push',true)));
    pagination.addEventListener('click',event=>{
      const link=event.target.closest('a');
      if(!link || event.button!==0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      // Unfiltered routes are complete HTML pages. Keep native navigation working
      // even when the optional search catalog cannot be loaded.
      if(!isFiltered(readState(link.href))) return;
      event.preventDefault();apply(readState(link.href),'push',true);
    });
    win.addEventListener('popstate',()=>apply(readState(win.location.href),'none'));
    // Return-from-article scroll is restored natively by browser history/BFCache.
    reflectControls();updateMetadata();
    if(isFiltered(state)||new URL(win.location.href).searchParams.has('page')) apply(state,'replace');
    return {ready:()=>load(),state:()=>({...state})};
  }
  return {readState,stateURL,isFiltered,filterPosts,paginate,cardHTML,paginationHTML,init};
});
