const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require(process.env.DCR_PLAYWRIGHT_MODULE || 'playwright');

(async () => {
  const output = process.argv[2];
  const browser = await chromium.launch({ headless: true, channel: 'chrome' });
  try {
    const page = await browser.newPage({ viewport: { width: 794, height: 1123 } });
    await page.route('**/*', route => route.abort());
    for (const name of ['exhibit_a_receipt', 'dealer_flooring_loan_payoff']) {
      await page.setContent(fs.readFileSync(path.join(output, name+'.html'), 'utf8'));
      if (name === 'exhibit_a_receipt') {
        const gap = await page.locator('.dealer-signature-space').evaluate(element => {
          const dealer = element.previousElementSibling.getBoundingClientRect();
          const anchor = element.querySelector('.lbl').getBoundingClientRect();
          return anchor.top - dealer.bottom;
        });
        assert.ok(gap >= 72, 'Signature must leave 72px below the dealer name');
        assert.equal(await page.getByText('/sig1/', { exact: true }).count(), 1);
      } else {
        assert.ok((await page.locator('body').innerText()).includes('$221,529.00'));
      }
      await page.pdf({ path: path.join(output, name+'.pdf'), format: 'A4', printBackground: true,
        margin: { top: '15mm', bottom: '15mm', left: '15mm', right: '15mm' } });
    }
    console.log('Signature spacing, anchor count and dated payoff amount passed.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
