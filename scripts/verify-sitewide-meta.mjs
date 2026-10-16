/* Verify BSWD sitewide Meta Pixel without contacting Meta or lead intake. */
import { readFileSync, existsSync } from "node:fs";
import { runInNewContext } from "node:vm";
import assert from "node:assert/strict";

const pixelId = "2289161921865343";
const legacyPixelId = "3219951841530933";
const pages = [
  "cavalier-country-farm-case-study.html",
  "clearview-kennels-case-study.html",
  "cleveland-ga-web-design.html",
  "contractors-trades.html",
  "faq.html",
  "index.html",
  "leaf-case-study.html",
  "north-georgia-web-design.html",
  "ownership.html",
  "restaurants-food-trucks.html",
  "salons-tattoo.html",
  "southern-pressure-washing-case-study.html",
  "stag-stone-case-study.html",
  "website-checkup.html",
  "privacy.html",
];
let checked=0;
for (const page of pages) {
  const html=readFileSync(page,"utf8");
  const loaders=[...html.matchAll(/<script\b[^>]*src="\/bsw-meta-pixel\.js\?v=20261016"[^>]*><\/script>/g)];
  assert.equal(loaders.length,1,page+": expected one shared Pixel loader");
  assert(!html.includes(legacyPixelId),page+": legacy Pixel ID exposed");
  assert(!/fbq\s*\(\s*["']init["']/.test(html),page+": duplicate inline fbq init");
  assert.equal((html.match(/<noscript>/g)||[]).length,1,page+": noscript fallback mismatch");
  assert(html.includes("facebook.com/tr?id="+pixelId),page+": fallback Pixel wrong");
  assert(existsSync("bsw-meta-pixel.js"),page+": missing Pixel script");
  if(page!=="website-checkup.html" && page!=="privacy.html"){
    assert(html.includes("bsw-site.js"),page+": original site script missing");
  }
  checked++;
}
const checkup=readFileSync("website-checkup.html","utf8");
assert(checkup.includes('window.fbq("track", "Lead")'),"Lead conversion was lost");
const leadIndex=checkup.indexOf('window.fbq("track", "Lead")');
const formSuccess=checkup.lastIndexOf('status.classList.add("is-success")',leadIndex);
assert(formSuccess>0 && formSuccess<leadIndex,"Lead event must remain after successful form submission");
assert(checkup.slice(formSuccess,leadIndex).includes("Never send form fields or contact details to Meta"),
  "Tracking privacy guard lost");
assert(!checkup.slice(formSuccess,leadIndex+60).includes("email:"),
  "No contact fields should be passed to fbq");
const created=[];
const firstScript={parentNode:{insertBefore(node){created.push(node)}}};
const doc={
  createElement(type){return {tagName:type}},
  getElementsByTagName(type){assert.equal(type,"script");return [firstScript]},
};
const browser={};
const script=readFileSync("bsw-meta-pixel.js","utf8");
runInNewContext(script,{window:browser,document:doc});
assert.equal(created.length,1,"Pixel loader must be inserted once");
assert.equal(created[0].src,"https://connect.facebook.net/en_US/fbevents.js");
assert.equal(browser.__blackStagMetaPageViewSent,true,"one-time guard missing");
assert.equal(browser.fbq.queue.length,2,"Expected exactly init and PageView");
assert.equal(browser.fbq.queue[0][0],"init");
assert.equal(browser.fbq.queue[0][1],pixelId);
assert.equal(browser.fbq.queue[1][0],"track");
assert.equal(browser.fbq.queue[1][1],"PageView");
runInNewContext(script,{window:browser,document:doc});
assert.equal(browser.fbq.queue.length,2,"Duplicate script fired extra PageView");
assert.equal(created.length,1,"Duplicate script inserted extra Meta network loader");
console.log("PASS: "+checked+" pages, exactly one PageView and correct Pixel ID, Lead event retained.");
