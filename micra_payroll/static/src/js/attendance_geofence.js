/** @odoo-module **/

// Clean version: no geolocation, no fetch override

// Keep original fetch (no interception)
const originalFetch = window.fetch.bind(window);

window.fetch = function (input, init = {}) {
    return originalFetch(input, init);
};