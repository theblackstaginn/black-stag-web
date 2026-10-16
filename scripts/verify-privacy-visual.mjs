/* Render the privacy notice locally at desktop and iPhone-sized widths.
 * Intercept all Meta requests, so visual QA never sends artificial analytics.
 */
import assert from "node:assert/strict";
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";

const base=process.env.PREVIEW_BASE||"http://127.0.0.1:8765";
const browser=await chromium.launch({headless:true,args:["--no-sandbox"]});
const viewports={desktop:{width:1440,height:900},mobile:{width:390,height:844}};
mkdirSync("privacy-qa",{recursive:true});
try{
  for(const [label,viewport] of Object.entries(viewports)){
    const context=await browser.newContext({viewport,deviceScaleFactor:1,isMobile:label==="mobile",hasTouch:label==="mobile"});
    const page=await context.newPage();
    await page.route(/(connect\.facebook\.net|facebook\.com\/tr)/,route=>route.abort());
    await page.goto(base+"/privacy.html",{waitUntil:"domcontentloaded",timeout:25000});
    await page.locator("main.privacy-shell").waitFor({state:"visible"});
    assert.equal(await page.locator("main .privacy-panel section").count(),6,label+": privacy sections missing");
    assert(await page.locator("h1").isVisible(),label+": title not visible");
    assert(await page.locator(".privacy-panel a[href^='mailto:']").count()>0,label+": contact link missing");
    assert(await page.locator('footer a[href="/privacy.html"]').isVisible(),label+": footer notice link missing");
    const width=await page.evaluate(()=>({actual:document.documentElement.scrollWidth,viewport:innerWidth}));
    assert(width.actual<=width.viewport+5,label+": unwanted horizontal scroll "+JSON.stringify(width));
    await page.screenshot({path:"privacy-qa/"+label+"-privacy.png",fullPage:true});
    await page.locator(".privacy-panel").screenshot({path:"privacy-qa/"+label+"-full-notice.png"});
    await page.goto(base+"/website-checkup.html",{waitUntil:"domcontentloaded"});
    assert(await page.locator(".checkup-privacy-note a[href='/privacy.html']").isVisible(),
      label+": notice link hidden beside form");
    await page.locator(".checkup-privacy-note").screenshot({path:"privacy-qa/"+label+"-checkup-notice.png"});
    console.log("PASS "+label+": privacy layout and website-checkup disclosure render correctly.");
    await context.close();
  }
}finally{
  await browser.close();
}
