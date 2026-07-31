/**
 * Home Build Request Kanban is a read-only operational view.
 *
 * Its columns are derived from submitted Purchase Orders and Purchase
 * Receipts, so manual dragging or editing the hardwired columns would make
 * the board disagree with the source documents.
 */
(function() {
    var observer = null;
    var apply_timer = null;

    function is_hbr_kanban() {
        if (!window.frappe || !frappe.get_route) return false;
        var route = frappe.get_route() || [];
        return route[0] === 'List'
            && route[1] === 'Home Build Request'
            && route[2] === 'Kanban';
    }

    function disable_sortable(element) {
        if (!element || !window.Sortable || !Sortable.get) return;
        var sortable = Sortable.get(element);
        if (sortable) sortable.option('disabled', true);
    }

    function append_hbr_number(card) {
        var $card = $(card);
        var $properties = $card.find('.kanban-card-doc').first();
        if (!$properties.length || $properties.find('.dcr-hbr-number').length) return;

        var href = $card
            .find('a[href*="/desk/home-build-request/"]')
            .first()
            .attr('href');
        if (!href) return;

        var hbr_number = decodeURIComponent(href.split('/').filter(Boolean).pop() || '');
        if (!hbr_number) return;

        $('<div>', {
            class: 'text-muted text-truncate dcr-hbr-number'
        }).append($('<span>').text(hbr_number)).appendTo($properties);
    }

    function apply_lock() {
        apply_timer = null;
        if (!is_hbr_kanban()) return;

        $('.kanban, .kanban-cards').each(function() {
            disable_sortable(this);
        });
        $('.kanban-card:not(.new-card-area)').each(function() {
            append_hbr_number(this);
        });
        // Frappe must group by stored backend values. Present those values as
        // the four business lifecycle labels users expect.
        $('.kanban-column[data-column-value="Draft"] .kanban-title')
            .text(__('Pending'));
        $('.kanban-column[data-column-value="Pending"] .kanban-title')
            .text(__('Not Ordered'));
        $('.kanban .add-new-column, .kanban .column-options').remove();
        $('.kanban-card-body, .kanban-column-title').css('cursor', 'default');
    }

    function schedule_lock() {
        if (apply_timer) clearTimeout(apply_timer);
        apply_timer = setTimeout(apply_lock, 0);
    }

    function watch_route() {
        if (observer) {
            observer.disconnect();
            observer = null;
        }
        if (!is_hbr_kanban()) return;

        apply_lock();
        setTimeout(apply_lock, 100);
        setTimeout(apply_lock, 500);
        setTimeout(apply_lock, 1500);

        var root = document.querySelector('.layout-main-section') || document.body;
        observer = new MutationObserver(schedule_lock);
        observer.observe(root, { childList: true, subtree: true });
    }

    document.addEventListener('dragstart', function(event) {
        if (is_hbr_kanban() && event.target.closest('.kanban')) {
            event.preventDefault();
        }
    }, true);

    if (window.frappe && frappe.router && frappe.router.on) {
        frappe.router.on('change', watch_route);
    }
    $(document).ready(watch_route);
})();
