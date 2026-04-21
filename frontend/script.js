document.addEventListener('DOMContentLoaded', () => {
    const errorFeed   = document.getElementById('error-feed');
    const loading     = document.getElementById('loading');
    const refreshBtn  = document.getElementById('refresh-btn');
    const clearAllBtn = document.getElementById('clear-all-btn');

    const queuePanel  = document.getElementById('queue-panel');
    const queueCount  = document.getElementById('queue-count');
    const queueList   = document.getElementById('queue-list');
    const queuePulse  = document.getElementById('queue-pulse');

    const exclModal         = document.getElementById('exclusion-modal');
    const exclContainerInput = document.getElementById('excl-container');
    const exclPatternInput  = document.getElementById('excl-pattern');
    const saveExclBtn       = document.getElementById('save-exclusion');
    const activeExclModal   = document.getElementById('active-exclusions-modal');
    const exclusionsList    = document.getElementById('exclusions-list');
    const containerFilters  = document.getElementById('container-filters');

    document.querySelectorAll('.close-btn').forEach(b =>
        b.addEventListener('click', () => exclModal.classList.add('hidden')));
    document.querySelectorAll('.close-btn-active').forEach(b =>
        b.addEventListener('click', () => activeExclModal.classList.add('hidden')));

    // ── State ─────────────────────────────────────────────────────────────
    const knownCards = new Map();       // id -> DOM element
    let activeContainers = new Set();   // containers currently checked
    let lastQueueKey = '';              // change-detection for queue

    // ── Markdown renderer ─────────────────────────────────────────────────
    function renderMarkdown(text) {
        if (!text) return '';
        let html = escapeHtml(text);
        html = html.replace(/\*\*([\s\S]+?)\*\*/g, '<strong>$1</strong>');
        html = html.replace(/(?<!\*)\*(?!\*)([\s\S]+?)(?<!\*)\*(?!\*)/g, '<em>$1</em>');
        html = html.replace(/^#{2}\s+(.+)$/gm, '<h4>$1</h4>');
        html = html.replace(/^#{1}\s+(.+)$/gm, '<h3>$1</h3>');
        html = html.replace(/^\d+\.\s+(.+)$/gm, '<li>$1</li>');
        html = html.replace(/^[\*\-]\s+(.+)$/gm, '<li>$1</li>');
        html = html.replace(/((?:<li>.*<\/li>\s*)+)/g, '<ul>$1</ul>');
        html = html.replace(/\n\n/g, '</p><p>');
        html = html.replace(/\n/g, '<br>');
        return `<p>${html}</p>`;
    }

    // ── Summary helpers ───────────────────────────────────────────────────
    function normaliseSummary(raw) {
        // LLM sometimes wraps the whole thing in **…**, strip those
        return (raw || '').replace(/^\*+\s*/, '').replace(/\s*\*+$/, '').trim();
    }

    function getSummaryMeta(raw) {
        const text = normaliseSummary(raw).toUpperCase();
        if (text.startsWith('NEEDS INTERVENTION'))
            return { cls: 'summary-intervention', label: 'NEEDS INTERVENTION', icon: '⚠', type: 'intervention' };
        if (text.startsWith('LIKELY TRANSIENT'))
            return { cls: 'summary-transient', label: 'LIKELY TRANSIENT', icon: '✓', type: 'transient' };
        return { cls: 'summary-unknown', label: 'ANALYZED', icon: '·', type: 'unknown' };
    }

    function makeSummaryBody(raw) {
        if (!raw) return '<em>No summary available.</em>';
        const clean = normaliseSummary(raw)
            .replace(/^(NEEDS INTERVENTION|LIKELY TRANSIENT)\s*:\s*/i, '');
        return escapeHtml(clean);
    }

    // ── Collapsible helper ────────────────────────────────────────────────
    function createCollapsible(titleHtml, contentHtml) {
        const wrap = document.createElement('div');
        wrap.className = 'collapsible-section';
        wrap.innerHTML = `
            <button class="collapsible-toggle">
                <span class="toggle-arrow">▶</span>${titleHtml}
            </button>
            <div class="collapsible-body hidden">${contentHtml}</div>
        `;
        wrap.querySelector('.collapsible-toggle').addEventListener('click', () => {
            const body  = wrap.querySelector('.collapsible-body');
            const arrow = wrap.querySelector('.toggle-arrow');
            body.classList.toggle('hidden');
            arrow.textContent = body.classList.contains('hidden') ? '▶' : '▼';
        });
        return wrap;
    }

    // ── Card builder ──────────────────────────────────────────────────────
    function createErrorCard(data) {
        const div  = document.createElement('div');
        div.className = 'glass-card';
        div.dataset.id   = data.id;
        div.dataset.type = getSummaryMeta(data.llm_executive_summary).type;
        div.dataset.container = data.container_name;

        const date = new Date(data.timestamp).toLocaleString();
        const meta = getSummaryMeta(data.llm_executive_summary);

        const signalChips = (data.signal_types || '')
            .split(',')
            .filter(Boolean)
            .map(s => `<span class="signal-chip signal-${s.toLowerCase().replace('_', '-')}">${escapeHtml(s.replace('_', ' '))}</span>`)
            .join('');

        const windowRange = (data.window_start && data.window_end)
            ? (() => {
                const fmt = iso => new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
                const cnt = data.error_count != null ? ` · ${data.error_count} errors` : '';
                const cls = data.fingerprint_count != null ? ` · ${data.fingerprint_count} clusters` : '';
                return `<div class="window-range">${fmt(data.window_start)} → ${fmt(data.window_end)}${cnt}${cls}</div>`;
            })()
            : '';

        div.innerHTML = `
            <div class="card-header">
                <span class="container-badge">${escapeHtml(data.container_name)}</span>
                <span class="timestamp">${date}</span>
            </div>
            ${windowRange}
            ${signalChips ? `<div class="signal-chips">${signalChips}</div>` : `<div class="error-snippet">${escapeHtml(data.error_line)}</div>`}
            <div class="executive-summary ${meta.cls}">
                <span class="exec-icon">${meta.icon}</span>
                <span class="exec-label">${meta.label}</span>
                <span class="exec-body">${makeSummaryBody(data.llm_executive_summary)}</span>
            </div>
            <div class="collapsibles-container"></div>
            <div class="card-actions">
                <button class="btn resolve resolve-btn">✓ Resolve</button>
                <button class="btn danger exclude-action-btn">Exclude Pattern</button>
            </div>
        `;

        const cc = div.querySelector('.collapsibles-container');
        cc.appendChild(createCollapsible(
            'Cluster Summary',
            `<div class="context-box">${escapeHtml(data.context_log)}</div>`
        ));
        cc.appendChild(createCollapsible(
            'Investigation',
            `<div class="content-box llm-investigation">${renderMarkdown(data.llm_investigation)}</div>`
        ));
        cc.appendChild(createCollapsible(
            'Resolution',
            `<div class="content-box llm-resolution">${renderMarkdown(data.llm_resolution)}</div>`
        ));

        div.querySelector('.resolve-btn').addEventListener('click', async () => {
            try {
                await fetch(`/api/analyses/${data.id}`, { method: 'DELETE' });
                div.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
                div.style.opacity = '0';
                div.style.transform = 'translateY(-8px)';
                setTimeout(() => {
                    knownCards.delete(data.id);
                    div.remove();
                    refreshContainerFilter();
                }, 300);
            } catch (e) { console.error('Failed to resolve:', e); }
        });

        div.querySelector('.exclude-action-btn').addEventListener('click', () => {
            exclContainerInput.value = data.container_name;
            exclPatternInput.value = '';
            exclModal.classList.remove('hidden');
        });

        return div;
    }

    // ── Incremental data load ─────────────────────────────────────────────
    async function loadData() {
        try {
            const res  = await fetch('/api/analyses');
            const data = await res.json();

            if (data.length === 0) {
                knownCards.forEach(el => el.remove());
                knownCards.clear();
                errorFeed.classList.add('hidden');
                loading.classList.remove('hidden');
                loading.textContent = 'No errors detected — all quiet!';
                refreshContainerFilter();
                return;
            }

            loading.classList.add('hidden');
            errorFeed.classList.remove('hidden');

            const incomingIds = new Set(data.map(d => d.id));

            // Remove cards no longer in the API response
            knownCards.forEach((el, id) => {
                if (!incomingIds.has(id)) {
                    el.remove();
                    knownCards.delete(id);
                }
            });

            // Prepend new cards (newest first in API, so iterate reversed to keep order)
            [...data].reverse().forEach(item => {
                if (!knownCards.has(item.id)) {
                    const card = createErrorCard(item);
                    errorFeed.prepend(card);
                    knownCards.set(item.id, card);
                }
            });

            refreshContainerFilter();
            applyFilters();
        } catch (e) {
            loading.textContent = 'Error loading data.';
            console.error(e);
        }
    }

    // ── Filter logic ──────────────────────────────────────────────────────
    function getActiveTypes() {
        return new Set(
            [...document.querySelectorAll('.type-filter:checked')].map(c => c.value)
        );
    }

    function applyFilters() {
        const activeTypes = getActiveTypes();
        knownCards.forEach(card => {
            const typeMatch      = activeTypes.has(card.dataset.type);
            const containerMatch = activeContainers.size === 0 ||
                                   activeContainers.has(card.dataset.container);
            card.classList.toggle('hidden', !(typeMatch && containerMatch));
        });
    }

    function refreshContainerFilter() {
        const names = new Set();
        knownCards.forEach(card => names.add(card.dataset.container));

        // Preserve checked state
        const checked = new Set(
            [...containerFilters.querySelectorAll('input:checked')].map(i => i.value)
        );

        containerFilters.innerHTML = '';
        if (names.size === 0) {
            containerFilters.innerHTML = '<span class="filter-empty">No data yet</span>';
            activeContainers = new Set();
            return;
        }

        names.forEach(name => {
            const isChecked = checked.size === 0 || checked.has(name); // default: all on
            const label = document.createElement('label');
            label.className = 'filter-chip';
            label.innerHTML = `
                <input type="checkbox" class="container-filter" value="${escapeHtml(name)}"
                    ${isChecked ? 'checked' : ''}>
                <span class="chip container-chip">${escapeHtml(name)}</span>
            `;
            label.querySelector('input').addEventListener('change', () => {
                activeContainers = new Set(
                    [...containerFilters.querySelectorAll('input:checked')].map(i => i.value)
                );
                applyFilters();
            });
            containerFilters.appendChild(label);
        });

        activeContainers = new Set(
            [...containerFilters.querySelectorAll('input:checked')].map(i => i.value)
        );
    }

    document.querySelectorAll('.type-filter').forEach(cb =>
        cb.addEventListener('change', applyFilters)
    );

    // ── Clear All ─────────────────────────────────────────────────────────
    clearAllBtn.addEventListener('click', async () => {
        if (!confirm('Clear all analyzed errors? This cannot be undone.')) return;
        try {
            await fetch('/api/analyses', { method: 'DELETE' });
            knownCards.forEach(el => el.remove());
            knownCards.clear();
            errorFeed.classList.add('hidden');
            loading.classList.remove('hidden');
            loading.textContent = 'No errors detected — all quiet!';
            refreshContainerFilter();
        } catch (e) {
            alert('Failed to clear errors.');
            console.error(e);
        }
    });

    // ── Exclusion save ────────────────────────────────────────────────────
    saveExclBtn.addEventListener('click', async () => {
        const cname   = exclContainerInput.value;
        const pattern = exclPatternInput.value;
        if (!pattern) return;
        try {
            await fetch('/api/exclusions', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ container_name: cname, pattern })
            });
            exclModal.classList.add('hidden');
            alert('Exclusion saved!');
        } catch (e) {
            alert('Error saving exclusion');
            console.error(e);
        }
    });

    // ── View Exclusions ───────────────────────────────────────────────────
    document.getElementById('view-exclusions-btn').addEventListener('click', async () => {
        try {
            const data = await fetch('/api/exclusions').then(r => r.json());
            exclusionsList.innerHTML = '';
            if (data.length === 0) {
                exclusionsList.innerHTML = '<li>No active exclusions.</li>';
            } else {
                data.forEach(ex => {
                    const li = document.createElement('li');
                    li.innerHTML = `<strong>${escapeHtml(ex.container_name)}</strong>: ${escapeHtml(ex.pattern)}`;
                    exclusionsList.appendChild(li);
                });
            }
            activeExclModal.classList.remove('hidden');
        } catch (e) { console.error(e); }
    });

    refreshBtn.addEventListener('click', loadData);

    // ── Queue polling (no-flicker) ────────────────────────────────────────
    async function loadQueue() {
        try {
            const data    = await fetch('/api/queue').then(r => r.json());
            const windows = data.active_windows || [];

            const key = windows.map(w => w.container + w.error_count).join('|');
            if (key === lastQueueKey) return;
            lastQueueKey = key;

            if (windows.length > 0) {
                queuePanel.classList.remove('hidden');
                queuePanel.classList.add('active');
                queuePulse.classList.add('active');
                queueCount.classList.remove('empty');
                queueCount.textContent = `${windows.length} active`;

                queueList.innerHTML = '';
                windows.forEach(w => {
                    const mins = Math.ceil(w.seconds_remaining / 60);
                    const li = document.createElement('li');
                    li.innerHTML = `<span class="q-container">${escapeHtml(w.container)}</span>`
                        + `<span class="q-line">${w.error_count} errors · ${w.fingerprint_count} clusters · ${mins}m left</span>`;
                    queueList.appendChild(li);
                });
            } else {
                queuePanel.classList.add('hidden');
                queuePanel.classList.remove('active');
                queuePulse.classList.remove('active');
                queueList.innerHTML = '';
            }
        } catch (e) { console.warn('Queue fetch failed:', e); }
    }

    // ── Utilities ─────────────────────────────────────────────────────────
    function escapeHtml(unsafe) {
        if (!unsafe) return '';
        return unsafe.toString()
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }

    // ── Bootstrap ─────────────────────────────────────────────────────────
    loadData();
    loadQueue();
    setInterval(loadData,  30000);
    setInterval(loadQueue,  5000);
});
