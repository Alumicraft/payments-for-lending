// Exercise the production portal shell and script with synthetic API responses.
// Requires Playwright; DCR_PLAYWRIGHT_MODULE may point at a bundled installation.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require(process.env.DCR_PLAYWRIGHT_MODULE || "playwright");
const app = path.resolve(__dirname, "../..");
const template = fs.readFileSync(path.join(app, "www/dealer_portal.html"), "utf8");
const block = (name) => template.match(new RegExp("{% block " + name + " %}([\\s\\S]*?){% endblock %}"))[1];
const html = ("<html><head><meta charset=\"utf-8\">" + block("head_include") + "</head><body>" + block("page_content") + "</body></html>").replace(/{{[^}]*}}/g, "");
const data = {
    customer: { name: "DEALER-A", label: "Pilot Dealer", email: "pilot@example.test" },
    factories: [], onboarding_documents: [], signatures: [{ name: "SIGN-A", document_type: "Flooring Packet", reference_name: "APP-A", status: "Sent", actionable: true }], ach: { accounts: [], available: false },
    deals: [{ name: "HBR-A", floor_plan: "Pilot home", home_type: "Inventory", financing_type: "Floored", property_type: "Private Property",
        docstatus: 1, portal_status: "Accepted", order_stage: "Pending", loan_stage: "Applied", offline_date: "2026-11-20", documents: { items: [] },
        loan: { source: "Loan Application", name: "APP-A", principal: 220000, interest_rate: 12, monthly_payment: 2200, total_interest: 26400, total_payable: 246400 } }],
};

(async () => {
    const browser = await chromium.launch({ headless: true, channel: "chrome" });
    try {
        const page = await browser.newPage({ viewport: { width: 1366, height: 600 } });
        page.setDefaultTimeout(5000);
        const errors = [];
        page.on("pageerror", (error) => errors.push(error.message));
        await page.clock.install();
        let calls = 0;
        let responseStatus = 200;
        let pending;
        let acknowledgeHeld;
        let hold = false;
        let malformed = false;
        let releaseAction;
        let acknowledgeAction;
        const isContext = (response) => response.url().endsWith("get_portal_context");
        async function finish(response) {
            await (await response).finished();
            await page.evaluate(() => {});
        }
        async function advance() {
            const response = page.waitForResponse(isContext);
            response.catch(() => {});
            await page.clock.fastForward(10000);
            await finish(response);
        }
        await page.route("http://portal.test/**", async (route) => {
            const url = new URL(route.request().url());
            if (url.pathname.endsWith("get_portal_context")) {
                calls += 1;
                if (hold) await new Promise((resolve) => { pending = resolve; acknowledgeHeld(); });
                return route.fulfill({ status: responseStatus, json: responseStatus === 200 ? { message: malformed ? {} : data } : { message: "Service unavailable" } });
            }
            if (/start_signature|upload_document$/.test(url.pathname)) {
                await new Promise((resolve) => { releaseAction = resolve; acknowledgeAction(); });
                if (url.pathname.endsWith("upload_document")) {
                    Object.assign(data.deals[0].documents.items[0], { uploaded: true, complete: true, file_name: "pilot.pdf" });
                }
                return route.fulfill({ json: { message: { message: "Signing can be tried again later." } } });
            }
            if (url.pathname === "/portal") return route.fulfill({ contentType: "text/html; charset=utf-8", body: html });
            if (url.pathname.startsWith("/assets/dcr/")) {
                const asset = path.join(app, "public", url.pathname.slice("/assets/dcr/".length));
                return route.fulfill({ contentType: asset.endsWith(".js") ? "text/javascript" : "text/css", body: fs.readFileSync(asset) });
            }
            return route.fulfill({ status: 404, body: "" });
        });
        await page.goto("http://portal.test/portal?request=HBR-A");
        await page.getByRole("heading", { name: "Pilot home", exact: true }).waitFor();
        assert.equal(calls, 1);
        await advance();
        assert.equal(calls, 2, "a visible portal must refresh without a manual reload");

        // No data change must leave the existing DOM and focus in place.
        await page.evaluate(() => { window.__sameNode = document.querySelector("#dcr-portal-view h1"); });
        await advance();
        assert.equal(await page.evaluate(() => window.__sameNode === document.querySelector("#dcr-portal-view h1")), true);

        await page.locator('.dcr-btn-row[data-signature="SIGN-A"]').focus();
        const position = await page.locator("#dcr-portal-main").evaluate((node) => {
            node.scrollTop = Math.min(180, node.scrollHeight - node.clientHeight);
            return node.scrollTop;
        });
        assert.ok(position > 0, "the fixture must exercise a scrolled page");
        data.deals[0].loan_stage = "Funded";
        Object.assign(data.deals[0].loan, { source: "Loan", name: "LOAN-A", application_name: "APP-A", payments_summary: {
            funded: true, outstanding_principal: 220000, currency: "USD", upcoming: [{ date: "2026-11-01", total: 4400, principal: 2200, interest: 2200 }], history: [],
        } });
        data.deals[0].order_stage = "Ordered";
        await advance();
        assert.equal(await page.evaluate(() => document.activeElement.getAttribute("data-focus-key")), "sign|SIGN-A");
        assert.equal(await page.locator("#dcr-portal-main").evaluate((node) => node.scrollTop), position);
        assert.deepEqual(errors, [], "the portal should render updated data without a browser error");
        assert.match(await page.locator("#dcr-portal-view").innerText(), /Home ordered/, "the updated ordering step should be visible");
        assert.match(await page.locator("#dcr-portal-view").innerText(), /Next payment[\s\S]*\$4,400/);
        assert.doesNotMatch(await page.locator("#dcr-portal-view").innerText(), /Total interest|Total payable/);
        assert.match(await page.locator("#dcr-portal-view").innerText(), /TBD/);
        assert.match(await page.locator("#dcr-portal-view").innerText(), /Off Line Date/);
        assert.doesNotMatch(await page.locator("#dcr-portal-view").innerText(), /â€/, "the production script must be served as UTF-8");

        // An in-flight request must not produce overlapping interval reads.
        hold = true;
        const heldResponse = page.waitForResponse(isContext);
        heldResponse.catch(() => {});
        const heldRequest = new Promise((resolve) => { acknowledgeHeld = resolve; });
        await page.clock.fastForward(10000);
        await heldRequest;
        const inFlightCalls = calls;
        await page.clock.fastForward(20000);
        assert.equal(calls, inFlightCalls, "background reads must not overlap");
        hold = false;
        pending();
        await finish(heldResponse);

        // Hidden tabs stop polling; showing the tab catches up immediately.
        await page.evaluate(() => Object.defineProperty(document, "hidden", { configurable: true, value: true }));
        const hiddenCalls = calls;
        await page.clock.fastForward(30000);
        assert.equal(calls, hiddenCalls);
        const visibleResponse = page.waitForResponse(isContext);
        await page.evaluate(() => { Object.defineProperty(document, "hidden", { configurable: true, value: false }); document.dispatchEvent(new Event("visibilitychange")); });
        await finish(visibleResponse);
        assert.equal(calls, hiddenCalls + 1);

        // Signing actions keep their controls while waiting for the provider.
        const signingHeld = new Promise((resolve) => { acknowledgeAction = resolve; });
        await page.locator('.dcr-btn-row[data-signature="SIGN-A"]').click();
        await signingHeld;
        const signingCalls = calls;
        await page.clock.fastForward(20000);
        assert.equal(calls, signingCalls, "signing must suspend background refreshes");
        assert.equal(await page.locator('.dcr-btn-row[data-signature="SIGN-A"]').isDisabled(), true);
        releaseAction();
        await page.getByRole("alert").filter({ hasText: "Signing can be tried again later." }).waitFor();

        // Uploading a draft document suspends polling and refreshes after save.
        Object.assign(data.deals[0], { docstatus: 0, portal_status: "In review", order_stage: "Draft" });
        data.deals[0].documents.items = [{ document_type: "Factory Quote", uploaded: false, complete: false }];
        await advance();
        const uploadHeld = new Promise((resolve) => { acknowledgeAction = resolve; });
        await page.locator('.dcr-record-main input[type="file"]').setInputFiles({ name: "pilot.pdf", mimeType: "application/pdf", buffer: Buffer.from("synthetic fixture") });
        await uploadHeld;
        const uploadCalls = calls;
        await page.clock.fastForward(20000);
        assert.equal(calls, uploadCalls, "uploads must suspend background refreshes");
        assert.match(await page.locator("#dcr-portal-view").innerText(), /Uploading/);
        const uploadResponse = page.waitForResponse(isContext);
        releaseAction();
        await finish(uploadResponse);
        assert.match(await page.locator("#dcr-portal-view").innerText(), /pilot\.pdf/);
        assert.equal(await page.locator('input[type="file"]').count(), 0);

        responseStatus = 503;
        await advance();
        assert.match(await page.locator("#dcr-portal-view").innerText(), /Pilot home/);
        assert.equal(await page.locator("#dcr-portal-toast").isVisible(), false, "background failures must not interrupt the dealer");
        responseStatus = 200;
        Object.assign(data.deals[0], { docstatus: 1, portal_status: "Accepted" });
        data.deals[0].order_stage = "Delivered";
        await advance();
        assert.match(await page.locator("#dcr-portal-view").innerText(), /Home delivered/);

        malformed = true;
        await advance();
        assert.match(await page.locator("#dcr-portal-view").innerText(), /Home delivered/, "a malformed background response preserves the current view");
        malformed = false;
        Object.assign(data.deals[0], { home_type: "Customer Sold", end_buyer_name: "Pilot buyer", selling_price: 240000,
            installed_value: 260000, quoted_amount: 220000, quote_no: "QT-A", factory: { name: "PLANT-A", label: "Pilot plant" } });
        await advance();
        const soldSummary = await page.locator("#dcr-portal-view").innerText();
        for (const value of ["Pilot buyer", "$240,000.00", "$260,000.00", "QT-A", "Pilot plant"]) assert.ok(soldSummary.includes(value));
        data.deals[0].home_type = "Inventory";
        await advance();
        assert.doesNotMatch(await page.locator("#dcr-portal-view").innerText(), /Pilot buyer/, "inventory detail must not expose a stale buyer field");
        if (process.env.DCR_PORTAL_SCREENSHOT) {
            await page.setViewportSize({ width: 1366, height: 900 });
            await page.locator("#dcr-portal-main").evaluate((node) => { node.scrollTop = 0; });
            await page.clock.runFor(50);
            await page.screenshot({ path: process.env.DCR_PORTAL_SCREENSHOT });
        }
        responseStatus = 401;
        await advance();
        assert.doesNotMatch(await page.locator("#dcr-portal-view").innerText(), /Pilot home|Home delivered|220,000/, "an expired session clears cached dealer data");
        assert.equal(await page.getByRole("button", { name: "Try again", exact: true }).count(), 1);
        assert.deepEqual(errors, []);
        console.log("Portal browser checks passed: automatic updates, DOM/focus/scroll preservation, scheduled payment, serialized reads, visibility, signing/upload protection, transient recovery and expired sessions");
    } finally { await browser.close(); }
})().catch((error) => { console.error(error); process.exitCode = 1; });
