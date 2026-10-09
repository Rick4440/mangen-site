const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const file = path.resolve(__dirname, '../assets/js/journal.js');
const available = fs.existsSync(file);
const journal = available ? require(file) : {};
const posts = Array.from({length:25}, (_,i) => ({slug:`post-${i}`,url:`/blog/post-${i}`,title:i%2?'京都庭园':'东京交通',excerpt:'行程安排',search:i%2?'京都庭园 清水寺':'东京交通 机场',destinations:[i%2?'京都':'东京'],topic:i%2?'行程路线':'交通与接送',date:'2026-10-01',cover:'',coverAlt:''}));
test('journal behavior module exists',()=>assert.ok(available,'Search/filter implementation is missing'));
test('search matches body keywords and intersects independent filters',()=>{
  assert.equal(typeof journal.filterPosts,'function');
  assert.equal(journal.filterPosts(posts,{q:'清水寺',destination:'京都',topic:'行程路线'}).length,12);
  assert.equal(journal.filterPosts(posts,{q:'清水寺',destination:'东京',topic:''}).length,0);
  assert.equal(journal.filterPosts(posts,{q:'  ',destination:'',topic:''}).length,25);
});
test('pagination includes all posts exactly once and clamps invalid bounds',()=>{
  assert.equal(typeof journal.paginate,'function');
  assert.equal(journal.paginate(posts,1,12).items.length,12);
  assert.equal(journal.paginate(posts,2,12).items.length,12);
  assert.equal(journal.paginate(posts,3,12).items.length,1);
  assert.equal(journal.paginate(posts,99,12).page,3);
  assert.equal(journal.paginate([],1,12).pages,0);
});
test('URL state and links preserve search while static pages have real routes',()=>{
  assert.equal(typeof journal.readState,'function');
  assert.deepEqual(journal.readState('https://mangen.jp/blog/page/2/'),{q:'',destination:'',topic:'',page:2});
  assert.equal(journal.stateURL({q:'',destination:'',topic:'',page:2}),'/blog/page/2/');
  const state={q:'清水寺',destination:'京都',topic:'行程路线',page:2};
  assert.deepEqual(journal.readState('https://mangen.jp'+journal.stateURL(state)),state);
});
test('cards escape arbitrary metadata rather than execute markup',()=>{
  assert.equal(typeof journal.cardHTML,'function');
  const html=journal.cardHTML({...posts[0],title:'<img src=x onerror=alert(1)>',excerpt:'"<&'});
  assert.ok(html.includes('&lt;img'));assert.ok(!html.includes('onerror=alert(1)>'));
});
const { JSDOM } = require('jsdom');
const tick = () => new Promise(resolve => setImmediate(resolve));
function dom(url='https://mangen.jp/blog/',fetcher) {
  const html=fs.readFileSync(path.resolve(__dirname,'../blog/index.html'),'utf8');
  const instance=new JSDOM(html,{url,runScripts:'outside-only'});
  instance.window.fetch=fetcher || (async()=>({ok:true,json:async()=>({posts,perPage:12})}));
  instance.window.scrollTo=()=>{};
  return instance;
}
test('DOM search, combined filters, empty state, reset, history and metadata work',async()=>{
  const d=dom();const win=d.window; journal.init(win); const doc=win.document;
  doc.querySelector('#guide-search').value='清水寺';
  doc.querySelector('.journal-search').dispatchEvent(new win.Event('submit',{bubbles:true,cancelable:true}));
  await tick();
  assert.equal(doc.querySelectorAll('.guide-card').length,12);
  assert.equal(doc.querySelector('#journal-robots').content,'noindex,follow');
  assert.ok(win.location.search.includes('q='));
  doc.querySelector('[data-filter="topic"][value="交通与接送"]').click();await tick();
  assert.equal(doc.querySelector('#empty-state').hidden,false);
  assert.equal(doc.querySelectorAll('.guide-card').length,0);
  doc.querySelector('[data-clear]').click();await tick();
  assert.equal(doc.querySelectorAll('.guide-card').length,12);
  assert.equal(doc.querySelector('#journal-robots').content,'index,follow');
  const next=doc.querySelector('#journal-pagination a[rel="next"]');
  // Observe after the delegated handler without performing JSDOM navigation.
  const gridClick=new win.MouseEvent('click',{bubbles:true,cancelable:true,button:0});
  next.dispatchEvent(gridClick);
  assert.equal(gridClick.defaultPrevented,false,'Static page links must retain native fallback');
  win.history.replaceState(null,'','/blog/page/2/');win.dispatchEvent(new win.PopStateEvent('popstate'));await tick();
  assert.equal(doc.querySelector('link[rel="canonical"]').href,'https://mangen.jp/blog/page/2/');
  win.history.replaceState(null,'','/blog/?q=清水寺');win.dispatchEvent(new win.PopStateEvent('popstate'));await tick();
  assert.equal(doc.querySelector('#guide-search').value,'清水寺');
  assert.equal(doc.querySelectorAll('.guide-card').length,12);
  d.window.close();
});
test('catalog fetch error preserves crawlable cards and permits retry',async()=>{
  let fail=true;const d=dom(undefined,async()=>{if(fail)throw Error('offline');return {ok:true,json:async()=>({posts,perPage:12})};});
  journal.init(d.window); const doc=d.window.document;const original=doc.querySelectorAll('.guide-card').length;
  doc.querySelector('.journal-search').dispatchEvent(new d.window.Event('submit',{bubbles:true,cancelable:true}));await tick();
  assert.equal(doc.querySelector('#journal-error').hidden,false);assert.equal(doc.querySelectorAll('.guide-card').length,original);
  fail=false;doc.querySelector('.journal-search').dispatchEvent(new d.window.Event('submit',{bubbles:true,cancelable:true}));await tick();
  assert.equal(doc.querySelector('#journal-error').hidden,true);assert.equal(doc.querySelectorAll('.guide-card').length,12);d.window.close();
});
test('mobile navigation announces expanded state and Escape closes it',async()=>{
  const d=dom(); const win=d.window;win.matchMedia=()=>({matches:false,addEventListener:()=>{}});
  win.fetch=async()=>({ok:true,json:async()=>({})});
  win.eval(fs.readFileSync(path.resolve(__dirname,'../assets/js/main.js'),'utf8'));
  win.document.dispatchEvent(new win.Event('DOMContentLoaded'));await tick();
  const button=win.document.querySelector('.menu-btn');button.click();
  assert.equal(button.getAttribute('aria-expanded'),'true');
  win.document.dispatchEvent(new win.KeyboardEvent('keydown',{key:'Escape'}));
  assert.equal(button.getAttribute('aria-expanded'),'false');
  assert.equal(win.document.querySelector('#site-navigation').classList.contains('open'),false);d.window.close();
});
