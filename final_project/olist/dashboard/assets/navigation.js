/* Keep the active navigation item in sync with clicks and pane scrolling. */
(function () {
    'use strict';
    function bindNavigation() {
        const main = document.getElementById('dashboard-main');
        const nav = document.querySelector('.sidebar nav');
        if (!main || !nav || nav.dataset.navigationBound) return false;
        const links = Array.from(nav.querySelectorAll('a[href^="#"]'));
        const entries = links.map(function (link) {
            return {link: link, target: document.getElementById(link.getAttribute('href').slice(1))};
        }).filter(function (entry) { return entry.target; });
        if (!entries.length) return false;
        nav.dataset.navigationBound = 'true';
        let frame = null;
        let clickedTarget = null;
        let releaseTimer = null;

        function markCurrent(target) {
            entries.forEach(function (entry) {
                const active = entry.target === target;
                entry.link.classList.toggle('active', active);
                if (active) entry.link.setAttribute('aria-current', 'location');
                else entry.link.removeAttribute('aria-current');
            });
        }
        function updateFromScroll() {
            frame = null;
            if (clickedTarget) return;
            const paneTop = window.innerWidth > 720 ? main.getBoundingClientRect().top : 0;
            let current = entries[0].target;
            entries.forEach(function (entry) {
                if (entry.target.getBoundingClientRect().top <= paneTop + 100) current = entry.target;
            });
            const atBottom = window.innerWidth > 720
                ? main.scrollTop + main.clientHeight >= main.scrollHeight - 4
                : window.scrollY + window.innerHeight >= document.documentElement.scrollHeight - 4;
            if (atBottom && entries[entries.length - 1].target.getBoundingClientRect().top < window.innerHeight) {
                current = entries[entries.length - 1].target;
            }
            markCurrent(current);
        }
        function schedule() {
            if (frame === null) frame = requestAnimationFrame(updateFromScroll);
        }
        function release() {
            clickedTarget = null;
            clearTimeout(releaseTimer);
            schedule();
        }
        function goTo(entry, updateHash) {
            clickedTarget = entry.target;
            clearTimeout(releaseTimer);
            markCurrent(entry.target);
            if (updateHash && window.location.hash !== entry.link.getAttribute('href')) {
                window.history.pushState(null, '', entry.link.getAttribute('href'));
            }
            if (window.innerWidth > 720) {
                const top = main.scrollTop + entry.target.getBoundingClientRect().top - main.getBoundingClientRect().top - 20;
                main.scrollTo({top: Math.max(0, top), behavior: 'smooth'});
            } else {
                entry.target.scrollIntoView({behavior: 'smooth', block: 'start'});
            }
            releaseTimer = setTimeout(release, 900);
        }
        entries.forEach(function (entry) {
            entry.link.addEventListener('click', function (event) {
                if (event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
                event.preventDefault();
                goTo(entry, true);
            });
        });
        main.addEventListener('scroll', schedule, {passive: true});
        window.addEventListener('scroll', schedule, {passive: true});
        window.addEventListener('resize', schedule);
        main.addEventListener('wheel', release, {passive: true});
        main.addEventListener('touchstart', release, {passive: true});
        function followHash() {
            const entry = entries.find(function (item) { return item.link.getAttribute('href') === window.location.hash; });
            if (entry) goTo(entry, false);
            else release();
        }
        window.addEventListener('hashchange', followHash);
        window.addEventListener('popstate', followHash);
        if (entries.some(function (entry) { return entry.link.getAttribute('href') === window.location.hash; })) followHash();
        else updateFromScroll();
        return true;
    }
    if (!bindNavigation()) {
        const observer = new MutationObserver(function () {
            if (bindNavigation()) observer.disconnect();
        });
        observer.observe(document.documentElement, {childList: true, subtree: true});
    }
})();
