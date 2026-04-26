const API_BASE = 'http://localhost:8000';

document.addEventListener('DOMContentLoaded', () => {
    fetchUsers();

    document.getElementById('generateBtn').addEventListener('click', generateRecommendations);
});

async function fetchUsers() {
    try {
        const response = await fetch(`${API_BASE}/users`);
        const users = await response.json();
        
        const select = document.getElementById('userSelect');
        select.innerHTML = '<option value="" disabled selected>اختر مستخدماً...</option>';
        
        users.forEach(user => {
            const option = document.createElement('option');
            option.value = user.user_id;
            option.textContent = `مستخدم #${user.user_id} - العمر: ${user.age || 'غير محدد'} - الموقع: ${user.location || 'غير محدد'}`;
            select.appendChild(option);
        });
        
        document.getElementById('generateBtn').disabled = false;
    } catch (error) {
        console.error('Error fetching users:', error);
        document.getElementById('userSelect').innerHTML = '<option value="" disabled selected>خطأ في تحميل المستخدمين. تأكد من تشغيل الخادم.</option>';
    }
}

async function generateRecommendations() {
    const userId = document.getElementById('userSelect').value;
    if (!userId) return;

    // Reset UI
    document.getElementById('generateBtn').disabled = true;
    const processSection = document.getElementById('evolutionProcess');
    const recsSection = document.getElementById('recommendationsSection');
    
    processSection.classList.remove('hidden');
    recsSection.classList.add('hidden');
    
    document.getElementById('progressBar').style.width = '0%';
    document.getElementById('generationText').textContent = 'جاري الاتصال بالخادم...';
    document.getElementById('bestFitness').textContent = '0';

    try {
        const response = await fetch(`${API_BASE}/recommend/${userId}`);
        const data = await response.json();
        
        // Simulate Evolution Animation
        animateEvolution(data.history, data.final_recommendations);
    } catch (error) {
        console.error('Error fetching recommendations:', error);
        alert('حدث خطأ أثناء جلب التوصيات.');
        document.getElementById('generateBtn').disabled = false;
    }
}

function animateEvolution(history, finalRecommendations) {
    let currentGen = 0;
    const totalGens = history.length;
    const interval = 300; // ms per generation frame
    
    const timer = setInterval(() => {
        if (currentGen >= totalGens) {
            clearInterval(timer);
            showFinalRecommendations(finalRecommendations);
            document.getElementById('generateBtn').disabled = false;
            return;
        }
        
        const genData = history[currentGen];
        
        // Update UI
        const progress = ((currentGen + 1) / totalGens) * 100;
        document.getElementById('progressBar').style.width = `${progress}%`;
        document.getElementById('generationText').textContent = `الجيل: ${genData.generation} / ${totalGens}`;
        document.getElementById('bestFitness').textContent = genData.best_score;
        
        currentGen++;
    }, interval);
}

function getIconForCategory(category) {
    const map = {
        'أجهزة ذكية': 'fa-mobile-screen-button',
        'ملابس رياضية': 'fa-person-running',
        'مستحضرات تجميل': 'fa-wand-magic-sparkles',
        'كتب': 'fa-book',
        'أدوات منزلية': 'fa-house',
        'عطور': 'fa-spray-can',
        'ألعاب': 'fa-gamepad'
    };
    return map[category] || 'fa-box-open';
}

function showFinalRecommendations(products) {
    const grid = document.getElementById('productsGrid');
    grid.innerHTML = '';
    
    products.forEach((product, index) => {
        const card = document.createElement('div');
        card.className = 'product-card animate-fade-in';
        card.style.animationDelay = `${index * 0.1}s`;
        
        const iconClass = getIconForCategory(product.category);
        
        card.innerHTML = `
            <div class="product-icon">
                <i class="fa-solid ${iconClass}"></i>
            </div>
            <div class="product-id">منتج #${product.id}</div>
            <div class="product-category">${product.category}</div>
            <div class="product-price">${product.price} ر.س</div>
        `;
        
        grid.appendChild(card);
    });
    
    document.getElementById('recommendationsSection').classList.remove('hidden');
    
    // Scroll to recommendations
    setTimeout(() => {
        document.getElementById('recommendationsSection').scrollIntoView({ behavior: 'smooth' });
    }, 100);
}
