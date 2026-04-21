document.addEventListener('DOMContentLoaded', () => {
    const errorFeed = document.getElementById('error-feed');
    const loading = document.getElementById('loading');
    const refreshBtn = document.getElementById('refresh-btn');

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

    async function loadData() {
        loading.classList.remove('hidden');
        errorFeed.classList.add('hidden');
        errorFeed.innerHTML = '';

        try {
            const res = await fetch('/api/analyses');
            const data = await res.json();
            
            if (data.length === 0) {
                loading.textContent = "No errors detected recently.";
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

    function createErrorCard(data) {
        const div = document.createElement('div');
        div.className = 'glass-card';
        
        const date = new Date(data.timestamp).toLocaleString();
        
        div.innerHTML = `
            <div class="card-header">
                <span class="container-badge">${data.container_name}</span>
                <span class="timestamp">${date}</span>
            </div>
            
            <div class="error-snippet">${escapeHtml(data.error_line)}</div>
            
            <div class="section-title">Context (+/- 100ms)</div>
            <div class="context-box">${escapeHtml(data.context_log)}</div>

            <div class="section-title">LLM Investigation</div>
            <div class="content-box llm-investigation">${escapeHtml(data.llm_investigation)}</div>
            
            <div class="section-title">LLM Resolution</div>
            <div class="content-box llm-resolution">${escapeHtml(data.llm_resolution)}</div>

            <div class="card-actions">
                <button class="btn danger exclude-action-btn" data-cname="${data.container_name}" data-line="${escapeHtml(data.error_line)}">Exclude Pattern</button>
            </div>
        `;

        // Attach event
        const btn = div.querySelector('.exclude-action-btn');
        btn.addEventListener('click', () => {
            exclContainerInput.value = data.container_name;
            // Provide a good default substring for exclusion
            let line = data.error_line;
            // Trim timestamps if present
            if(line.includes("Z ")) {
                line = line.split("Z ")[1];
            }
            exclPatternInput.value = line;
            exclModal.classList.remove('hidden');
        });

        return div;
    }

    saveExclBtn.addEventListener('click', async () => {
        const cname = exclContainerInput.value;
        const pattern = exclPatternInput.value;
        if(!pattern) return;

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

    document.getElementById('view-exclusions-btn').addEventListener('click', async () => {
        try {
            const res = await fetch('/api/exclusions');
            const data = await res.json();
            
            exclusionsList.innerHTML = '';
            if(data.length === 0) {
                exclusionsList.innerHTML = '<li>No active exclusions.</li>';
            } else {
                data.forEach(ex => {
                    const li = document.createElement('li');
                    li.innerHTML = `<strong>${ex.container_name}</strong>: ${escapeHtml(ex.pattern)}`;
                    exclusionsList.appendChild(li);
                });
            }
            activeExclModal.classList.remove('hidden');
        } catch(e) {
            console.error(e);
        }
    });

    refreshBtn.addEventListener('click', loadData);

    async function loadQueue() {
        try {
            const res = await fetch('/api/queue');
            const data = await res.json();
            const total = data.total || 0;
            const recent = data.recent || [];

            // Toggle panel visibility
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
                // Keep panel visible for 5 more seconds after draining
                // then hide
                setTimeout(() => {
                    if (queueList.children.length === 0) {
                        queuePanel.classList.add('hidden');
                    }
                }, 5000);
            }

            // Render last 5 items
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

    function escapeHtml(unsafe) {
        if(!unsafe) return "";
        return unsafe.toString()
             .replace(/&/g, "&amp;")
             .replace(/</g, "&lt;")
             .replace(/>/g, "&gt;")
             .replace(/"/g, "&quot;")
             .replace(/'/g, "&#039;");
    }

    // Initial load
    loadData();
    loadQueue();
    // Auto refresh every 30 seconds
    setInterval(loadData, 30000);
    // Queue status every 5 seconds
    setInterval(loadQueue, 5000);
});
