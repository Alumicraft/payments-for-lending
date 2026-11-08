// Render the real portal assets with owned synthetic records; no hosted writes.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require(process.env.DCR_PLAYWRIGHT_MODULE || 'playwright');
const app = path.resolve(__dirname, '../..');
const template = fs.readFileSync(path.join(app, 'www/dealer_portal.html'), 'utf8');
const block = name => template.match(new RegExp('{% block ' + name + ' %}([\\s\\S]*?){% endblock %}'))[1];
const html = ('<html><head><meta charset="utf-8">' + block('head_include') + '</head><body>' + block('page_content') + '</body></html>').replace(/{{[^}]*}}/g, '');
const output = process.env.DCR_PORTAL_SCREENSHOT_DIR;
const documents = ['dealer_license_copy', 'sellers_permit_copy', 'w9_copy', 'retailer_application_copy'].map(fieldname => ({ fieldname, label: fieldname, uploaded: true, can_download: true, uploaded_on: '2026-10-01', file_name: 'owned.pdf' }));
const data = {
    customer: { name: 'DEALER-A', label: 'Harbor Point Homes', email: 'dealer@example.test' },
    factories: [{ name: 'FACTORY-A', label: 'Champion' }], onboarding_documents: documents,
    signatures: ['Dealer Agreement', 'MIFA'].map((document_type, i) => ({ name: 'ACCOUNT-' + i, document_type, status: 'Signed', signed_date: '2026-10-01', can_download: true })),
    support_url: 'mailto:accounting@example.test', ach: { available: true, accounts: [{ bank_name: 'First Platypus', last4: '0000', status: 'Active' }], automatic_payments: 'Not set up' },
    finance: { available: true, outstanding: 900000, funded_loans: 4, credit_limit: 1500000, available_credit: 600000, paid_total: 9000,
        principal_series: [{ date: '2026-10-01', amount: 909000 }, { date: '2026-11-07', amount: 900000 }], paid_series: [{ date: '2026-10-01', amount: 4500 }, { date: '2026-11-07', amount: 9000 }] },
    deals: Array.from({ length: 4 }, (_, i) => ({ name: 'ACC-HBR-2026-000' + (30 + i), floor_plan: 'Plan ' + i, home_type: i ? 'Spec' : 'Customer Sold',
        end_buyer_name: i ? 'Stale buyer' : 'Alex Rivera', home_serial_no: i ? 'TBD' : 'SN-2026', docstatus: 1, portal_status: 'Accepted',
        order_stage: 'Ordered', loan_stage: 'Funded', financing_type: 'Floored', quoted_amount: 220000, documents: { items: [] },
        loan: { source: 'Loan', name: 'LOAN-' + i, interest_rate: 12, payoff: { can_request: true }, payments_summary: {
            funded: true, funded_on: '2026-10-01', outstanding_principal: 225000, as_of: '2026-11-07',
            principal_series: [{ date: '2026-10-01', amount: 225000 }, { date: '2026-11-07', amount: 225000 }],
            upcoming: [{ date: '2026-12-01', principal: 0, interest: 2250, total: 2250, due_status: 'Scheduled' },
                { date: '2027-01-01', principal: 2250, interest: 2250.17, total: 4500.17, due_status: 'Scheduled' }],
            history: [{ date: '2026-11-01', amount: 2250, type: 'Normal Repayment' }] } } })),
};

(async () => {
    const browser = await chromium.launch({ headless: true, channel: 'chrome' });
    try {
        const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, colorScheme: 'light' });
        const errors = [];
        page.on('pageerror', e => errors.push(e.message));
        await page.clock.install({ time: new Date('2026-11-07T18:00:00Z') });
        await page.route('http://portal.test/**', route => {
            const url = new URL(route.request().url());
            if (url.pathname.endsWith('get_portal_context')) return route.fulfill({ json: { message: data } });
            if (url.pathname === '/portal') return route.fulfill({ contentType: 'text/html', body: html });
            if (url.pathname.startsWith('/assets/dcr/')) {
                const asset = path.join(app, 'public', url.pathname.slice('/assets/dcr/'.length));
                return route.fulfill({ contentType: asset.endsWith('.js') ? 'text/javascript' : asset.endsWith('.woff2') ? 'font/woff2' : 'text/css', body: fs.readFileSync(asset) });
            }
            return route.fulfill({ status: 404 });
        });
        async function open(route) {
            await page.goto('http://portal.test/portal#/' + route);
            await page.reload();
            await page.locator('#dcr-portal-view h1').waitFor();
            await page.evaluate(() => document.fonts.ready);
        }
        async function shot(name) {
            if (!output) return;
            fs.mkdirSync(output, { recursive: true });
            await page.screenshot({ path: path.join(output, name + '.png'), fullPage: true });
        }
        async function noOverflow() {
            assert.equal(await page.locator('#dcr-portal-main').evaluate(n => n.scrollWidth <= n.clientWidth + 1), true, 'the main area must not overflow horizontally');
        }
        await open('home');
        assert.equal(await page.locator('.dcr-sidebar').evaluate(n => n.getBoundingClientRect().width), 228);
        assert.equal(await page.locator('.dcr-payment-side tbody tr').count(), 2);
        assert.match(await page.locator('.dcr-overflow-row').innerText(), /2 more/);
        assert.match(await page.locator('.dcr-side-total').innerText(), /9,000/);
        assert.equal(await page.locator('.dcr-line-chart').count(), 1);
        assert.equal(await page.locator('.dcr-tabs').count(), 0);
        await noOverflow(); await shot('home-ready');
        await open('builds');
        assert.equal(await page.locator('input[type=search]').count(), 0);
        assert.equal(await page.locator('.dcr-tab').count(), 4);
        assert.doesNotMatch(await page.locator('#dcr-portal-view').innerText(), /Stale buyer/);
        assert.match(await page.locator('#dcr-portal-view').innerText(), /Alex Rivera/);
        await shot('builds');
        for (const tab of ['', '/details', '/documents', '/payments']) {
            await open('request/' + data.deals[0].name + tab);
            assert.equal(await page.locator('h1').innerText(), data.deals[0].name);
            assert.equal(await page.locator('.dcr-build-aside h2').count(), 2);
            assert.doesNotMatch(await page.locator('#dcr-portal-view').innerText(), /Interest \$|Principal \$|Interest owed|Total interest/);
            if (!tab) assert.equal(await page.locator('.dcr-line-chart [stroke-dasharray]').count(), 1);
            if (tab === '/details') assert.equal(await page.getByRole('link', { name: 'Edit', exact: true }).count(), 0);
            await noOverflow(); await shot('build-' + (tab.slice(1) || 'overview'));
        }
        await open('loans');
        assert.match(await page.locator('#dcr-portal-view').innerText(), /600,000/);
        await shot('loans');
        for (const tab of ['', '/schedule', '/bank']) {
            await open('payments' + tab);
            assert.equal(await page.locator('.dcr-tab').count(), 3);
            if (tab === '/bank') assert.match(await page.locator('#dcr-portal-view').innerText(), /Not set up/);
            if (tab === '/schedule') {
                assert.match(await page.locator('#dcr-portal-view').innerText(), /4,500.17/);
                assert.doesNotMatch(await page.locator('thead').innerText(), /Principal|Interest/);
            }
            await shot('payments-' + (tab.slice(1) || 'overview'));
        }
        const funded = structuredClone(data.deals);
        data.deals = data.deals.map(d => ({ ...d, loan: { source: null }, loan_stage: 'Not Started' }));
        data.finance = { available: true, funded_loans: 0, outstanding: 0 };
        await open('home');
        assert.equal(await page.locator('.dcr-chart, .dcr-payment-side').count(), 0);
        await shot('home-no-loans');
        data.onboarding_documents[1].uploaded = false;
        await open('home');
        assert.equal(await page.locator('h1').innerText(), 'Set up your account');
        assert.equal(await page.getByRole('link', { name: 'New build', exact: true }).count(), 1, 'setup must not enforce an unapproved build gate');
        assert.equal(await page.locator('.dcr-tab-count').count(), 0);
        await shot('setup-todo');
        await open('home/done'); await shot('setup-done');
        data.onboarding_documents[1].uploaded = true;
        data.deals = funded;
        data.finance = { available: true, outstanding: 900000, funded_loans: 4, principal_series: [{ date: '2026-10-01', amount: 900000 }] };
        await page.emulateMedia({ colorScheme: 'dark' });
        await open('home');
        assert.equal(await page.locator('#dcr-dealer-portal').evaluate(n => getComputedStyle(n).backgroundColor), 'rgb(17, 17, 17)');
        await shot('home-dark');
        await page.emulateMedia({ colorScheme: 'light' });
        await page.setViewportSize({ width: 390, height: 844 });
        for (const route of ['home', 'builds', 'request/' + data.deals[0].name, 'payments/schedule', 'payments/bank', 'settings']) {
            await open(route);
            assert.equal(await page.locator('.dcr-bottom-nav').isVisible(), true);
            assert.equal(await page.locator('.dcr-sidebar').isVisible(), false);
            assert.equal(await page.getByRole('heading', { name: 'Use a computer' }).count(), 0);
            await noOverflow(); await shot('phone-' + route.split('/')[0] + (route.startsWith('payments/') ? '-' + route.split('/')[1] : ''));
        }
        assert.deepEqual(errors, []);
        console.log('Portal redesign checks passed: setup, ready, no loans, all tabs, totals, capped rows, loan curtailments, dark mode, phone and edit locks.');
    } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
