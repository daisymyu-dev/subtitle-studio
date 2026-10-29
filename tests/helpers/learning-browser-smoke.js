'use strict';
// Optional real-browser QA: NODE_PATH supplies Playwright; BROWSER_CHANNEL may select installed Chrome.
// Self-authored captions and mocked APIs only. No translation, video SDK or dictionary network traffic.
const fs=require('node:fs'),http=require('node:http'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('playwright');

async function main(){
  const root=path.resolve(__dirname,'../../web'),id='a'.repeat(32),requests=[],errors=[];
  const profile={known:[],saved:[],progress:{[id]:3.5}};
  const cues=[
    {start:0,end:2,english:'An otherworldly idea demands resilience.',chinese:'一个非凡的想法需要韧性。'},
    {start:3,end:6,english:'Small steps build resilience.',chinese:'小步前进培养韧性。'}
  ];
  const result={id,title:'A small learning journey / 自编演示',url:null,sentence_version:1,source:'local_caption',count:2,preview:[],files:{}};
  const server=http.createServer((req,res)=>{
    const url=new URL(req.url,'http://127.0.0.1'),name=url.pathname==='/'?'index.html':url.pathname.slice(1),file=path.join(root,name);
    if(!file.startsWith(root+path.sep)){res.writeHead(403);res.end();return;}
    try{
      let data=fs.readFileSync(file);
      if(name==='index.html')data=data.toString().replaceAll('__SESSION_TOKEN__','test-token').replaceAll('__VIDEO_BRIDGE_ORIGIN__','http://127.0.0.1:1').replaceAll('__DESIGN__','studio').replaceAll('__DESIGN_NAME__','Studio').replaceAll('__DESIGN_NUMBER__','01');
      res.setHeader('Content-Type',name.endsWith('.js')?'text/javascript':name.endsWith('.css')?'text/css':'text/html');res.end(data);
    }catch{res.writeHead(404);res.end();}
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));let browser;
  try{
    browser=await chromium.launch({headless:true,...(process.env.BROWSER_CHANNEL?{channel:process.env.BROWSER_CHANNEL}:{})});
    const page=await browser.newPage({viewport:{width:1280,height:900}});page.on('pageerror',error=>errors.push(String(error)));
    await page.route('**/*',async route=>{
      const req=route.request(),url=new URL(req.url());
      if(url.hostname!=='127.0.0.1')throw Error('Unexpected external request: '+url.origin);
      if(!url.pathname.startsWith('/api/'))return route.continue();
      requests.push({path:url.pathname,method:req.method(),body:req.postData()});let body;
      if(url.pathname==='/api/learning')body=profile;
      else if(url.pathname==='/api/library')body={items:[{id,title:result.title,cue_count:2,position:3.5}]};
      else if(url.pathname==='/api/jobs/'+id)body={status:'done',stage:'done',result};
      else if(url.pathname.endsWith('/study'))body={...result,cues,mode:'sentences'};
      else if(url.pathname==='/api/dictionary'){
        const word=req.postDataJSON().word;
        body={word,phonetic:'/rɪˈzɪliəns/',definitions:[{part_of_speech:'noun',definition:'The ability to recover after difficulty.',example:'Small steps help us recover.'}],source_url:'https://en.wiktionary.org/wiki/'+word,license:{name:'CC BY-SA 3.0',url:'https://creativecommons.org/licenses/by-sa/3.0/'}};
      }else if(url.pathname.endsWith('/term')){
        const item=req.postDataJSON();profile.known=profile.known.filter(key=>key!==item.key);profile.saved=profile.saved.filter(value=>value.key!==item.key);
        if(item.state==='known')profile.known.push(item.key);if(item.state==='learn')profile.saved.push(item);body=profile;
      }else if(url.pathname.endsWith('/progress'))body={ok:true};else throw Error('Unexpected mock API: '+url.pathname);
      await route.fulfill({json:body});
    });
    await page.goto('http://127.0.0.1:'+server.address().port+'/?job='+id+'&page=study');await page.waitForLoadState('networkidle');
    assert.equal(await page.locator('#watch-current-en').textContent(),'Small steps build resilience.');
    await page.getByRole('button',{name:'学习库'}).click();await page.locator('#dictionary-input').fill('resilience');
    assert.equal(requests.filter(value=>value.path==='/api/dictionary').length,0);
    await page.getByRole('button',{name:'同意并查词'}).click();await page.locator('#dictionary-definitions').getByText('The ability to recover after difficulty.').waitFor();
    assert.deepEqual(JSON.parse(requests.find(value=>value.path==='/api/dictionary').body),{word:'resilience'});
    await page.locator('#dictionary-save').click();await page.locator('#dictionary-status').getByText('学习状态已保存在本机。').waitFor();assert.equal(profile.saved[0].key,'resilience');
    await page.locator('#dictionary-close').click();
    await page.locator('.watch-row-en .learning-token').first().hover();await page.locator('#learning-card').waitFor({state:'visible'});
    await page.locator('#learning-known').click();await page.waitForFunction(()=>document.querySelectorAll('.watch-row-en .learning-token').length===0);assert.ok(profile.known.includes('otherworldly'));
    await page.getByRole('button',{name:'学习库'}).click();await page.locator('.library-known summary').click();await page.getByRole('button',{name:'重新学习'}).click();await page.waitForFunction(()=>document.querySelectorAll('.watch-row-en .learning-token').length===1);
    await page.locator('#library-close').click();
    await page.locator('.watch-row-en').first().evaluate(node=>{
      const walker=document.createTreeWalker(node,NodeFilter.SHOW_TEXT);let text;
      while((text=walker.nextNode()))if(text.textContent.includes('resilience'))break;
      const start=text.textContent.indexOf('resilience'),range=document.createRange();range.setStart(text,start);range.setEnd(text,start+10);
      const selection=window.getSelection();selection.removeAllRanges();selection.addRange(range);
    });
    await page.locator('.watch-row-en').first().dispatchEvent('pointerup');await page.locator('#dictionary-selection').waitFor({state:'visible'});
    assert.equal(requests.filter(value=>value.path==='/api/dictionary').length,1);
    await page.locator('#dictionary-lookup').click();await page.locator('#dictionary-definitions').getByText('The ability to recover after difficulty.').waitFor();
    assert.equal(requests.filter(value=>value.path==='/api/dictionary').length,2);await page.locator('#dictionary-close').click();
    await page.setViewportSize({width:390,height:844});await page.getByRole('button',{name:'学习库'}).click();assert.equal(await page.locator('#dictionary-input').isVisible(),true);
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);assert.deepEqual(errors,[]);
    if(process.env.SUBTITLE_QA_SCREENSHOT)await page.screenshot({path:process.env.SUBTITLE_QA_SCREENSHOT,fullPage:false});
    console.log('BROWSER PASS: local resume, manual + selected-word lookup, save/known/unlearn, hover, 390px layout; no page errors or external requests.');
  }finally{await browser?.close();await new Promise(resolve=>server.close(resolve));}
}
main().catch(error=>{console.error(error);process.exitCode=1;});
