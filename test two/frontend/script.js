const API = 'http://localhost:8000';
let fitnessChart = null;

// ── Helpers ──────────────────────────────────
function show(id) { document.getElementById(id).classList.remove('hidden'); }
function hide(id) { document.getElementById(id).classList.add('hidden'); }
function $(id) { return document.getElementById(id); }
function toast(msg, isError = false) {
    const t = document.createElement('div');
    t.className = 'toast' + (isError ? ' error' : '');
    t.textContent = msg;
    $('toastContainer').appendChild(t);
    setTimeout(() => t.remove(), 3200);
}

const categoryIcons = {
    'Toys': 'fa-puzzle-piece', 'Clothes': 'fa-shirt', 'Perfumes': 'fa-spray-can-sparkles',
    'Sports': 'fa-futbol', 'Home Appliances': 'fa-blender', 'Books': 'fa-book',
    'Electronics': 'fa-microchip',
};
function catIcon(cat) { return categoryIcons[cat] || 'fa-box'; }

// ── Init ─────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    loadStats();
    loadUsers();
    $('userSelect').addEventListener('change', onUserChange);
    $('generateBtn').addEventListener('click', onGenerate);

});

// ── Load global stats ────────────────────────
async function loadStats() {
    try {
        const res = await fetch(`${API}/stats`);
        const data = await res.json();
        $('statUsers').textContent = data.total_users.toLocaleString();
        $('statProducts').textContent = data.total_products.toLocaleString();
        $('statRatings').textContent = data.total_ratings.toLocaleString();
    } catch { /* silent */ }
}

// ── Load users ───────────────────────────────
async function loadUsers() {
    try {
        const res = await fetch(`${API}/users`);
        const users = await res.json();
        const sel = $('userSelect');
        sel.innerHTML = '<option value="" disabled selected>— اختر مستخدماً —</option>';
        users.forEach(u => {
            const opt = document.createElement('option');
            opt.value = u.user_id;
            opt.textContent = `مستخدم #${u.user_id} — ${u.country} — العمر: ${u.age}`;
            sel.appendChild(opt);
        });
    } catch {
        toast('تعذّر تحميل المستخدمين — تأكد من تشغيل السيرفر', true);
    }
}

// ── On user change → load profile ────────────
async function onUserChange() {
    const uid = $('userSelect').value;
    if (!uid) return;
    $('generateBtn').disabled = false;

    try {
        const res = await fetch(`${API}/users/${uid}/profile`);
        const p = await res.json();

        $('profileName').textContent = `مستخدم #${p.user_id}`;
        $('profileMeta').textContent = `${p.country} — العمر: ${p.age}`;
        $('profileViews').textContent = p.total_views.toLocaleString();
        $('profileClicks').textContent = p.total_clicks.toLocaleString();
        $('profilePurchases').textContent = p.total_purchases.toLocaleString();
        $('profileAvgPrice').textContent = p.avg_price.toLocaleString();

        // Category preference bars
        const bars = $('prefsBars');
        bars.innerHTML = '';
        const prefs = p.category_preferences;
        const maxVal = Math.max(...Object.values(prefs), 1);
        Object.entries(prefs).sort((a, b) => b[1] - a[1]).forEach(([cat, val]) => {
            const pct = Math.round((val / maxVal) * 100);
            const row = document.createElement('div');
            row.className = 'pref-bar-row';
            row.innerHTML = `
                <span class="pref-bar-label">${cat}</span>
                <div class="pref-bar-track"><div class="pref-bar-fill" style="width:0%"></div></div>`;
            bars.appendChild(row);
            requestAnimationFrame(() => {
                row.querySelector('.pref-bar-fill').style.width = pct + '%';
            });
        });

        show('profilePanel');
    } catch {
        toast('تعذّر تحميل ملف المستخدم', true);
    }
}

// ── Generate recommendations ─────────────────
async function onGenerate() {
    const uid = $('userSelect').value;
    if (!uid) return;

    $('generateBtn').disabled = true;
    hide('resultsPanel');
    hide('comparePanel');
    hide('paramsPanel');
    show('evolutionPanel');

    // Reset chart
    initChart();

    try {
        const res = await fetch(`${API}/recommend/${uid}`);
        const data = await res.json();

        // Animate history generation by generation
        await animateEvolution(data.history);

        // Show final recommendations
        renderProducts($('productsGrid'), data.final_recommendations);
        show('resultsPanel');

        // Show params
        renderParams(data.params);
        show('paramsPanel');

        // Load comparison
        await loadComparison(uid);

        $('generateBtn').disabled = false;
        toast('تم توليد التوصيات بنجاح ✨');
    } catch (e) {
        toast('حدث خطأ أثناء التوليد: ' + e.message, true);
        $('generateBtn').disabled = false;
    }
}

// ── Chart ────────────────────────────────────
function initChart() {
    const ctx = $('fitnessChart').getContext('2d');
    if (fitnessChart) fitnessChart.destroy();
    fitnessChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [
                {
                    label: 'أعلى ملاءمة (Best)',
                    data: [],
                    borderColor: '#7c3aed',
                    backgroundColor: 'rgba(124,58,237,0.1)',
                    fill: true,
                    tension: 0.35,
                    pointRadius: 4,
                    pointBackgroundColor: '#7c3aed',
                    borderWidth: 2.5,
                },
                {
                    label: 'متوسط الملاءمة (Avg)',
                    data: [],
                    borderColor: '#06b6d4',
                    backgroundColor: 'rgba(6,182,212,0.05)',
                    fill: true,
                    tension: 0.35,
                    pointRadius: 3,
                    pointBackgroundColor: '#06b6d4',
                    borderWidth: 2,
                    borderDash: [5, 3],
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: { duration: 300 },
            plugins: {
                legend: { labels: { color: '#94a3b8', font: { family: 'Cairo' } } },
            },
            scales: {
                x: {
                    title: { display: true, text: 'الجيل', color: '#64748b', font: { family: 'Cairo' } },
                    ticks: { color: '#64748b' },
                    grid: { color: 'rgba(124,58,237,0.06)' },
                },
                y: {
                    title: { display: true, text: 'الملاءمة (Fitness)', color: '#64748b', font: { family: 'Cairo' } },
                    ticks: { color: '#64748b' },
                    grid: { color: 'rgba(124,58,237,0.06)' },
                },
            },
        },
    });
}

// ── Animate evolution ────────────────────────
function animateEvolution(history) {
    return new Promise(resolve => {
        let i = 0;
        const total = history.length;
        function step() {
            if (i >= total) { resolve(); return; }
            const h = history[i];
            fitnessChart.data.labels.push(h.generation);
            fitnessChart.data.datasets[0].data.push(h.best_score);
            fitnessChart.data.datasets[1].data.push(h.avg_score);
            fitnessChart.update();
            $('currentGen').textContent = `${h.generation} / ${total}`;
            $('bestFitness').textContent = h.best_score.toLocaleString();
            $('avgFitness').textContent = h.avg_score.toLocaleString();
            $('mutationRate').textContent = h.mutation_rate;
            i++;
            setTimeout(step, 120);
        }
        step();
    });
}

// ── Render products ──────────────────────────
function renderProducts(container, products) {
    container.innerHTML = '';
    products.forEach((p, idx) => {
        const card = document.createElement('div');
        card.className = 'product-card';
        card.style.animationDelay = `${idx * 0.08}s`;
        card.innerHTML = `
            <div class="card-icon"><i class="fa-solid ${catIcon(p.category)}"></i></div>
            <div class="card-id">Product #${p.id}</div>
            <div class="card-category">${p.category}</div>
            <div class="card-price">${p.price.toLocaleString()} ل.س</div>`;
        container.appendChild(card);
    });
}

// ── Render params ────────────────────────────
function renderParams(params) {
    const labels = {
        population_size: 'حجم المجتمع',
        chromosome_length: 'طول الكروموسوم',
        generations: 'عدد الأجيال',
        tournament_size: 'حجم البطولة',
        elite_count: 'عدد النخبة',
        initial_mutation_rate: 'طفرة (بداية)',
        final_mutation_rate: 'طفرة (نهاية)',
    };
    const grid = $('paramsGrid');
    grid.innerHTML = '';
    Object.entries(params).forEach(([k, v]) => {
        const div = document.createElement('div');
        div.className = 'param-card';
        div.innerHTML = `<span class="param-label">${labels[k] || k}</span><span class="param-value">${v}</span>`;
        grid.appendChild(div);
    });
}

// ── Comparison ───────────────────────────────
async function loadComparison(uid) {
    try {
        const res = await fetch(`${API}/recommend/${uid}/compare`);
        const data = await res.json();

        $('improvementPct').textContent = data.improvement_percent;
        $('gaScore').textContent = data.ga.score.toLocaleString();
        $('randomScore').textContent = data.random.score.toLocaleString();

        renderCompareList($('gaProducts'), data.ga.products);
        renderCompareList($('randomProducts'), data.random.products);

        show('comparePanel');
    } catch { /* silent */ }
}

function renderCompareList(container, products) {
    container.innerHTML = '';
    products.forEach(p => {
        const div = document.createElement('div');
        div.className = 'compare-item';
        div.innerHTML = `<span class="ci-cat"><i class="fa-solid ${catIcon(p.category)}"></i> ${p.category}</span><span class="ci-price">${p.price.toLocaleString()} ل.س</span>`;
        container.appendChild(div);
    });
}
