const assert = require("node:assert/strict");
const showFilters = require("../public/js/hbr_board_filters.js");

(async () => {
    let shown = 0, moved = 0, built = 0;
    const filters = [["Home Build Request", "docstatus", "in", [0, 1]]];
    const pageForm = { show() { shown++; } };
    const board = {
        doctype: "Home Build Request", view_name: "Kanban", hide_page_form: true,
        page: { page_form: pageForm },
        $filter_section: { appendTo(target) { assert.equal(target, pageForm); moved++; } },
        filter_area: { make_standard_filters() { built++; return Promise.resolve(); }, get() { return filters; } }
    };
    await showFilters(board);
    await showFilters(board);
    assert.deepEqual([shown, moved, built], [1, 1, 1], "Repeated board renders must not duplicate controls");
    assert.equal(board.hide_page_form, false);
    assert.equal(board.filter_area.get(), filters, "Keep existing filter constraints");
    for (const variant of [{ doctype: "Purchase Order" }, { view_name: "List" }]) {
        await showFilters({ ...board, ...variant, __dcr_board_filters: undefined });
    }
    assert.deepEqual([shown, moved, built], [1, 1, 1], "Other documents and views stay untouched");
    assert.equal(showFilters({ doctype: "Home Build Request", view_name: "Kanban" }), undefined, "Wait for native filter setup");
    const broken = { ...board, __dcr_board_filters: undefined, filter_area: { make_standard_filters() { return Promise.reject(new Error("unavailable")); } } };
    await showFilters(broken);
    await showFilters(broken);
    assert.equal(broken.__dcr_board_filters, "failed", "Do not retry endlessly from the board observer");
    console.log("HBR board filters: native setup, retained constraints, scoped views, repeated renders and failed setup passed");
})().catch(error => { console.error(error); process.exitCode = 1; });
