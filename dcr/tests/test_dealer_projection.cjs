const assert = require("node:assert/strict");
const { dcrScheduledPrincipal } = require("../public/js/dealer_portal.js");
// An interest-only demand is still money due, but does not reduce principal.
assert.equal(dcrScheduledPrincipal(220000, [{date:"2026-10-31",principal:0,interest:2200,outstanding:2200}], "2026-10-31"), 220000);
assert.equal(dcrScheduledPrincipal(220000, [{date:"2026-10-31",principal:5000,interest:2200,outstanding:7200}], "2026-10-31"), 215000);
assert.equal(dcrScheduledPrincipal(220000, [{date:"2026-11-30",principal:5000}], "2026-10-31"), 220000);
assert.equal(dcrScheduledPrincipal(1000, [{date:"2026-10-31",principal:5000}], "2026-10-31"), 0);
console.log("4 principal projection scenarios passed");
