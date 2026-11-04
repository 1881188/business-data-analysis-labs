/* Presentation-only splitter. Filtering and chart calculations remain in Python. */
(function () {
    'use strict';
    const storageKey = 'olist-sidebar-width-v1';
    const defaultWidth = 280;

    function bindSplitter() {
        const handle = document.getElementById('sidebar-resizer');
        const shell = document.querySelector('.app-shell');
        if (!handle || !shell || handle.dataset.resizeBound) return false;
        handle.dataset.resizeBound = 'true';
        let desiredWidth = defaultWidth;
        let pointerId = null;
        let frame = null;
        try {
            const saved = Number(localStorage.getItem(storageKey));
            if (Number.isFinite(saved) && saved >= 240 && saved <= 440) desiredWidth = saved;
        } catch (_) { /* The splitter also works when browser storage is disabled. */ }

        function applyWidth(width) {
            const maximum = Math.max(240, Math.min(440, shell.clientWidth - 430));
            const actual = Math.round(Math.max(240, Math.min(maximum, width)));
            shell.style.setProperty('--sidebar-width', actual + 'px');
            handle.setAttribute('aria-valuenow', String(actual));
            handle.setAttribute('aria-valuemax', String(Math.round(maximum)));
            if (frame !== null) cancelAnimationFrame(frame);
            frame = requestAnimationFrame(function () {
                frame = null;
                window.dispatchEvent(new Event('resize'));
            });
            return actual;
        }
        function remember() {
            try { localStorage.setItem(storageKey, String(desiredWidth)); } catch (_) {}
        }
        function finish(event) {
            if (pointerId === null || event.pointerId !== pointerId) return;
            const captured = pointerId;
            pointerId = null;
            shell.classList.remove('is-resizing');
            if (handle.hasPointerCapture(captured)) handle.releasePointerCapture(captured);
            remember();
        }
        handle.addEventListener('pointerdown', function (event) {
            if (event.button !== 0 || window.innerWidth <= 720) return;
            event.preventDefault();
            pointerId = event.pointerId;
            handle.setPointerCapture(pointerId);
            handle.focus({preventScroll: true});
            shell.classList.add('is-resizing');
        });
        handle.addEventListener('pointermove', function (event) {
            if (event.pointerId !== pointerId || pointerId === null) return;
            desiredWidth = applyWidth(event.clientX - shell.getBoundingClientRect().left);
        });
        handle.addEventListener('pointerup', finish);
        handle.addEventListener('pointercancel', finish);
        handle.addEventListener('lostpointercapture', function () {
            pointerId = null;
            shell.classList.remove('is-resizing');
        });
        handle.addEventListener('dblclick', function () {
            desiredWidth = applyWidth(defaultWidth);
            remember();
        });
        handle.addEventListener('keydown', function (event) {
            const step = event.shiftKey ? 32 : 16;
            let next = Number(handle.getAttribute('aria-valuenow'));
            if (event.key === 'ArrowLeft') next -= step;
            else if (event.key === 'ArrowRight') next += step;
            else if (event.key === 'Home') next = defaultWidth;
            else if (event.key === 'End') next = 440;
            else return;
            event.preventDefault();
            desiredWidth = applyWidth(next);
            remember();
        });
        // Re-clamp on browser resizing without replacing the user's saved preference.
        window.addEventListener('resize', function (event) {
            if (event.isTrusted) applyWidth(desiredWidth);
        });
        applyWidth(desiredWidth);
        return true;
    }

    if (!bindSplitter()) {
        const observer = new MutationObserver(function () {
            if (bindSplitter()) observer.disconnect();
        });
        observer.observe(document.documentElement, {childList: true, subtree: true});
    }
})();
