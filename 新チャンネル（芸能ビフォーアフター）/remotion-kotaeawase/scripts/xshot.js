// Xの公式の埋め込み表示を開いて、投稿の部分だけをスクショする（日本時間、返信の欄へのボタンは入れない）
// 使い方：node xshot.js <status ID> <出力png>
const { chromium } = require('playwright');
(async () => {
  const [id, out] = process.argv.slice(2);
  const browser = await chromium.launch({ proxy: { server: process.env.HTTPS_PROXY } });
  const page = await browser.newPage({ viewport: { width: 550, height: 1400 }, deviceScaleFactor: 2, locale: 'ja-JP', timezoneId: 'Asia/Tokyo' });
  await page.goto(`https://platform.twitter.com/embed/Tweet.html?id=${id}&lang=ja&theme=light&hideThread=true&dnt=true`, { waitUntil: 'networkidle', timeout: 60000 });
  await page.waitForTimeout(2000);
  // 読み込めなかった絵文字の画像は、その絵文字の文字に置き換える
  await page.evaluate(() => {
    document.querySelectorAll('img[alt]').forEach((img) => {
      if (/emoji/.test(img.src) || (img.naturalWidth === 0 && img.alt)) {
        const s = document.createElement('span'); s.textContent = img.alt; img.replaceWith(s);
      }
    });
  });
  const art = await page.$('article');
  const box = await art.boundingBox();
  let bottom = box.y + box.height;
  const btn = await page.$('text=/返信を読む|件の返信/');
  if (btn) { const b = await btn.boundingBox(); if (b) bottom = b.y - 6; }
  await page.screenshot({ path: out, clip: { x: box.x, y: box.y, width: box.width, height: bottom - box.y } });
  console.log('ok', out);
  await browser.close();
})().catch(e => { console.error(e); process.exit(1); });
