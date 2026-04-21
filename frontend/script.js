document.addEventListener('DOMContentLoaded', () => {
    const errorFeed = document.getElementById('error-feed');
    const loading = document.getElementById('loading');
    const refreshBtn = document.getElementById('refresh-btn');
    const clearAllBtn = document.getElementById('clear-all-btn');

    // Queue panel
    const queuePanel = document.getElementById('queue-panel');
    const queueCount = document.getElementById('queue-count');
    const queueList  = document.getElementById('queue-list');
    const queuePulse = document.getElementById('queue-pulse');
    
    // Modals
    const exclModal = document.getElementById('exclusion-modal');
    const exclContainerInput = document.getElementById('excl-container');
    const exclPatternInput = document.getElementById('excl-pattern');
    const saveExclBtn = document.getElementById('save-exclusion');
    
    const activeExclModal = document.getElementById('active-exclusions-modal');
    const exclusionsList = document.getElementById('exclusions-list');

    // Close buttons
    document.querySelectorAll('.close-btn').forEach(btn => {
        btn.addEventListener('click', () => exclModal.classList.add('hidden'));
    });
    document.querySelectorAll('.close-btn-active').forEach(btn => {
        btn.addEventListener('click', () => activeExclModal.classList.add('hidden'));
    });

    // ── Markdown renderer ──────────────────────────────────────────────────
    function renderMarkdown(text) {
        if (!text) return '';
        let html = escapeHtml(text);
        // bold: **text**
        html = html.replace(/\*\*([\s\S]+?)\*\*/g, '<strong>$1</strong>');
        // italic: *text* (single, not already consumed above)
        html = html.replace(/(?<!\*)\*(?!\*)([\s\S]+?)(?<!\*)\*(?!\*)/g, '<em>$1</em>');
        // headings: lines starting with ## or #
        html = html.replace(/^#{2}\s+(.+)$/gm, '<h4>$1</h4>');
        html = html.replace(/^#{1}\s+(.+)$/gm, '<h3>$1</h3>');
        // numbered list items
        html = html.replace(/^\d+\.\s+(.+)$/gm, '<li>$1</li>');
        // bullet points
        html = html.replace(/^[\*\-]\s+(.+)$/gm, '<li>$1</li>');
        // Wrap consecutive <li> in <ul>
        html = html.replace(/(<li>[\s\S]*?<\/li>)(\s*<li>)/g, '$1$2');
        html = html.replace(/((?:<li>.*<\/li>\s*)+)/g, '<ul>$1</ul>');
        // line breaks
        html = html.replace(/\n\n/g, '</p><p>');
        html = html.replace(/\n/g, '<br>');
        return `<p>${html}</p>`;
    }

    // ── Data loading ───────────────────────────────────────────────────────
    async function loadData() {
        loading.classList.remove('hidden');
        errorFeed.classList.add('hidden');
        errorFeed.innerHTML = '';

        try {
            const res = await fetch('/api/analyses');
            const data = await res.json();
            
            if (data.length === 0) {
                loading.textContent = "No errors detected — all quiet!";
                return;
            }

            data.forEach(item => {
                const card = createErrorCard(item);
                errorFeed.appendChild(card);
            });

            loading.classList.add('hidden');
            errorFeed.classList.remove('hidden');
        } catch (e) {
            loading.textContent = "Error loading data.";
            console.error(e);
        }
    }

    // ── Card builder ───────────────────────────────────────────────────────
    function createErrorCard(data) {
        const div = document.createElement('div');
        div.className = 'glass-card';
        div.dataset.id = data.id;
        
        const date = new Date(data.timestamp).toLocaleString();
        
        div.innerHTML = `
            <div class="card-header">
                <span class="container-badge">${escapeHtml(data.container_name)}</span>
                <span class="timestamp">${date}</span>
            </div>
            
            <div class="error-snippet">${escapeHtml(data.error_line)}</div>
            
            <div class="section-title">Context (+/- 100ms)</div>
            <div class="context-box">${escapeHtml(data.context_log)}</div>

            <div class="section-title">LLM Investigation</div>
            <div class="content-box llm-investigation">${renderMarkdown(data.llm_investigation)}</div>
            
            <div class="section-title">LLM Resolution</div>
            <div class="content-box llm-resolution">${renderMarkdown(data.llm_resolution)}</div>

            <div class="card-actions">
                <button class="btn resolve resolve-btn">✓ Resolve</button>
                <button class="btn danger exclude-action-btn">Exclude Pattern</button>
            </div>
        `;

        // Resolve button
        div.querySelector('.resolve-btn').addEventListener('click', async () => {
            try {
                await fetch(`/api/analyses/${data.id}`, { method: 'DELETE' });
                div.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
                div.style.opacity = '0';
                div.style.transform = 'translateY(-8px)';
                setTimeout(() => div.remove(), 300);
            } catch (e) {
                console.error('Failed to resolve:', e);
            }
        });

        // Exclude button
        div.querySelector('.exclude-action-btn').addEventListener('click', () => {
            exclContainerInput.value = data.container_name;
            let line = data.error_line;
            if (line.includes("Z ")) line = line.split("Z ")[1];
            exclPatternInput.value = line;
            exclModal.classList.remove('hidden');
        });

        return div;
    }

    // ── Clear All ──────────────────────────────────────────────────────────
    clearAllBtn.addEventListener('click', async () => {
        if (!confirm('Clear all analyzed errors? This cannot be undone.')) return;
        try {
            await fetch('/api/analyses', { method: 'DELETE' });
            errorFeed.innerHTML = '';
            errorFeed.classList.add('hidden');
            loading.classList.remove('hidden');
            loading.textContent = "No errors detected — all quiet!";
        } catch (e) {
            alert('Failed to clear errors.');
            console.error(e);
        }
    });

    // ── Exclusion save ─────────────────────────────────────────────────────
    saveExclBtn.addEventListener('click', async () => {
        const cname = exclContainerInput.value;
        const pattern = exclPatternInput.value;
        if (!pattern) return;

        try {
            await fetch('/api/exclusions', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({container_name: cname, pattern: pattern})
            });
            exclModal.classList.add('hidden');
            alert('Exclusion saved!');
        } catch (e) {
            alert('Error saving exclusion');
            console.error(e);
        }
    });

    // ── View Exclusions ────────────────────────────────────────────────────
    document.getElementById('view-exclusions-btn').addEventListener('click', async () => {
        try {
            const res = await fetch('/api/exclusions');
            const data = await res.json();
            
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
        } catch(e) {
            console.error(e);
        }
    });

    refreshBtn.addEventListener('click', loadData);

    // ── Queue polling ──────────────────────────────────────────────────────
    async function loadQueue() {
        try {
            const res = await fetch('/api/queue');
            const data = await res.json();
            const total = data.total || 0;
            const recent = data.recent || [];

            if (total > 0 || recent.length > 0) {
                queuePanel.classList.remove('hidden');
                queuePanel.classList.add('active');
                queuePulse.classList.add('active');
                queueCount.classList.remove('empty');
                queueCount.textContent = `${total} pending`;
            } else {
                queuePanel.classList.remove('active');
                queuePulse.classList.remove('active');
                queueCount.classList.add('empty');
                queueCount.textContent = '0 pending';
                setTimeout(() => {
                    if (!queuePanel.classList.contains('active')) {
                        queuePanel.classList.add('hidden');
                    }
                }, 5000);
            }

            queueList.innerHTML = '';
            recent.forEach(item => {
                const li = document.createElement('li');
                li.innerHTML = `<span class="q-container">${escapeHtml(item.container)}</span><span class="q-line">${escapeHtml(item.line)}</span>`;
                queueList.appendChild(li);
            });
        } catch (e) {
            console.warn('Queue fetch failed:', e);
        }
    }

    // ── Utilities ──────────────────────────────────────────────────────────
    function escapeHtml(unsafe) {
        if (!unsafe) return "";
        return unsafe.toString()
             .replace(/&/g, "&amp;")
             .replace(/</g, "&lt;")
             .replace(/>/g, "&gt;")
             .replace(/"/g, "&quot;")
             .replace(/'/g, "&#039;");
    }

    // ── Bootstrap ──────────────────────────────────────────────────────────
    loadData();
    loadQueue();
    setInterval(loadData, 30000);
    setInterval(loadQueue, 5000);
});
