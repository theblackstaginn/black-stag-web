/* Smoke-check a published privacy notice and its sitewide links.
 * No form submissions, external requests or contact data access. */
import { readFileSync } from "node:fs";
import assert from "node:assert/strict";

const pages=[
  "index.html",
  "website-checkup.html",
  "faq.html",
  "north-georgia-web-design.html",
  "cleveland-ga-web-design.html",
  "ownership.html",
  "restaurants-food-trucks.html",
  "contractors-trades.html",
  "salons-tattoo.html",
  "leaf-case-study.html",
  "clearview-kennels-case-study.html",
  "cavalier-country-farm-case-study.html",
  "southern-pressure-washing-case-study.html",
  "stag-stone-case-study.html"
];
const read=p=>readFileSync(p,"utf8");
for(const page of pages){
  const html=read(page);
  const footerStart=html.indexOf('<footer class="site-footer">');
  const footerEnd=html.indexOf("</footer>",footerStart);
  assert(footerStart>=0&&footerEnd>footerStart,page+": missing site footer");
  const footer=html.slice(footerStart,footerEnd);
  assert.equal((footer.match(/href="\/privacy\.html"/g)||[]).length,1,page+": privacy link not in footer exactly once");
  assert(html.includes("bsw-meta-pixel.js?v=20261016"),page+": sitewide Pixel script missing");
}
const notice=read("privacy.html");
const sections=["Who to contact","Information you choose to send","Meta Pixel and website measurement",
                "Website services and outside links","Your choices","Retention and changes"];
for(const heading of sections) assert(notice.includes(heading),"Missing disclosure section: "+heading);
for(const text of ["2289161921865343","PageView","Lead","fbclid","Supabase","Google Fonts",
                   "GitHub Pages","blackstagwebdesign@gmail.com","does not currently provide an on-site"])
  assert(notice.includes(text),"Missing factual disclosure: "+text);
assert(!notice.includes("3219951841530933"),"Wrong/orphaned Pixel ID in privacy notice");
assert(notice.includes('href="/privacy.html"')&&notice.includes('bsw-meta-pixel.js?v=20261016'),
  "Notice cannot be located or lacks Pixel disclosure context");
const checkup=read("website-checkup.html");
assert(checkup.includes('class="field-help checkup-privacy-note"'),"Checkup missing adjacent notice");
assert(checkup.includes('name="consent_to_contact" type="checkbox" required'),
       "Existing contact permission was altered");
assert(checkup.includes('window.fbq("track", "Lead")'),"Existing Lead event removed");
assert(checkup.includes("black-stag-lead-intake"),"Lead intake endpoint removed");
const sitemap=read("sitemap.xml");
assert(sitemap.includes("https://blackstagweb.com/privacy.html"),"Privacy notice not in sitemap");
console.log("PASS: privacy notice, 14 footer links, checkup disclosure, Meta tracking and lead flow intact.");
