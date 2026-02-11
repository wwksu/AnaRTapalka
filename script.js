// Инициализация Telegram WebApp
const tg = window.Telegram.WebApp;
tg.expand();
tg.ready();

// Получаем user_id из Telegram
const initData = tg.initDataUnsafe;
const userId = initData?.user?.id || 'test_user';

// Состояние игры
let gameState = {
    coins: 0,
    energy: 1000,
    max_energy: 1000,
    multi_tap_level: 1,
    energy_level: 1,
    auto_tap_level: 0,
    skin_bought: false,
    last_update: Date.now()
};

// Элементы DOM
const coinsEl = document.getElementById('coins');
const currentEnergyEl = document.getElementById('current-energy');
const maxEnergyEl = document.getElementById('max-energy');
const energyFillEl = document.getElementById('energy-fill');
const hamsterEl = document.getElementById('hamster');
const tapAnimationsEl = document.getElementById('tap-animations');

// Навигация
const tapScreen = document.getElementById('tap-screen');
const shopScreen = document.getElementById('shop-screen');
const leaderboardScreen = document.getElementById('leaderboard-screen');
const navTap = document.getElementById('nav-tap');
const navShop = document.getElementById('nav-shop');
const navLeaderboard = document.getElementById('nav-leaderboard');

// Кнопки магазина
const buyMultitapBtn = document.getElementById('buy-multitap');
const buyEnergyBtn = document.getElementById('buy-energy');
const buyAutotapBtn = document.getElementById('buy-autotap');
const buySkinBtn = document.getElementById('buy-skin');

// Загрузка данных пользователя
async function loadUserData() {
    try {
        const username = initData?.user?.username || 'Аноним';
        const firstName = initData?.user?.first_name || 'Игрок';
        const response = await fetch(`/api/user/${userId}?username=${encodeURIComponent(username)}&first_name=${encodeURIComponent(firstName)}`);
        const data = await response.json();
        gameState = data;
        updateUI();
    } catch (error) {
        console.error('Ошибка загрузки данных:', error);
    }
}

// Сохранение данных пользователя
async function saveUserData() {
    try {
        await fetch(`/api/user/${userId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(gameState)
        });
    } catch (error) {
        console.error('Ошибка сохранения данных:', error);
    }
}

// Обновление UI
function updateUI() {
    coinsEl.textContent = Math.floor(gameState.coins);
    currentEnergyEl.textContent = Math.floor(gameState.energy);
    maxEnergyEl.textContent = gameState.max_energy;
    
    // Обновление полоски энергии
    const energyPercent = (gameState.energy / gameState.max_energy) * 100;
    energyFillEl.style.width = energyPercent + '%';
    
    // Обновление магазина
    updateShopUI();
    
    // Применение скина
    if (gameState.skin_bought) {
        hamsterEl.classList.add('golden');
    }
}

// Обновление UI магазина
function updateShopUI() {
    // Мульти-тап
    const multitapPrice = 100 * Math.pow(2, gameState.multi_tap_level - 1);
    document.getElementById('multitap-level').textContent = gameState.multi_tap_level;
    document.getElementById('multitap-price').textContent = multitapPrice;
    buyMultitapBtn.disabled = gameState.coins < multitapPrice;
    
    // Энергия+
    const energyPrice = 200 * Math.pow(2, gameState.energy_level - 1);
    document.getElementById('energy-level').textContent = gameState.energy_level;
    document.getElementById('energy-price').textContent = energyPrice;
    buyEnergyBtn.disabled = gameState.coins < energyPrice;
    
    // Авто-тап
    const autotapPrice = gameState.auto_tap_level === 0 ? 500 : 500 * Math.pow(2, gameState.auto_tap_level);
    document.getElementById('autotap-level').textContent = gameState.auto_tap_level;
    document.getElementById('autotap-price').textContent = autotapPrice;
    buyAutotapBtn.disabled = gameState.coins < autotapPrice;
    
    // Скин
    if (gameState.skin_bought) {
        document.getElementById('skin-status').textContent = 'Куплено ✓';
        buySkinBtn.disabled = true;
        buySkinBtn.textContent = 'Куплено';
    } else {
        buySkinBtn.disabled = gameState.coins < 1000;
    }
}

// Тап по хомяку
hamsterEl.addEventListener('click', (e) => {
    if (gameState.energy < 1) return;
    
    // Уменьшаем энергию
    gameState.energy -= 1;
    
    // Добавляем монеты (с учётом мульти-тапа)
    gameState.coins += gameState.multi_tap_level;
    
    // Анимация +X
    createTapAnimation(e, gameState.multi_tap_level);
    
    // Обновляем UI
    updateUI();
    
    // Сохраняем данные (с дебаунсом)
    debouncedSave();
});

// Создание анимации тапа
function createTapAnimation(e, amount) {
    const rect = hamsterEl.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    
    const animation = document.createElement('div');
    animation.className = 'tap-animation';
    animation.textContent = '+' + amount;
    animation.style.left = x + 'px';
    animation.style.top = y + 'px';
    
    tapAnimationsEl.appendChild(animation);
    
    setTimeout(() => {
        animation.remove();
    }, 1000);
}

// Восстановление энергии (1 в секунду)
setInterval(() => {
    if (gameState.energy < gameState.max_energy) {
        gameState.energy = Math.min(gameState.energy + 1, gameState.max_energy);
        updateUI();
    }
}, 1000);

// Авто-тап (пассивный доход)
setInterval(() => {
    if (gameState.auto_tap_level > 0) {
        gameState.coins += gameState.auto_tap_level;
        updateUI();
        debouncedSave();
    }
}, 1000);

// Дебаунс для сохранения
let saveTimeout;
function debouncedSave() {
    clearTimeout(saveTimeout);
    saveTimeout = setTimeout(() => {
        saveUserData();
    }, 2000);
}

// Навигация
navTap.addEventListener('click', () => {
    tapScreen.classList.add('active');
    shopScreen.classList.remove('active');
    leaderboardScreen.classList.remove('active');
    navTap.classList.add('active');
    navShop.classList.remove('active');
    navLeaderboard.classList.remove('active');
});

navShop.addEventListener('click', () => {
    shopScreen.classList.add('active');
    tapScreen.classList.remove('active');
    leaderboardScreen.classList.remove('active');
    navShop.classList.add('active');
    navTap.classList.remove('active');
    navLeaderboard.classList.remove('active');
});

navLeaderboard.addEventListener('click', () => {
    leaderboardScreen.classList.add('active');
    tapScreen.classList.remove('active');
    shopScreen.classList.remove('active');
    navLeaderboard.classList.add('active');
    navTap.classList.remove('active');
    navShop.classList.remove('active');
    loadLeaderboard();
});

// Покупка мульти-тапа
buyMultitapBtn.addEventListener('click', () => {
    const price = 100 * Math.pow(2, gameState.multi_tap_level - 1);
    if (gameState.coins >= price) {
        gameState.coins -= price;
        gameState.multi_tap_level += 1;
        updateUI();
        saveUserData();
    }
});

// Покупка энергии+
buyEnergyBtn.addEventListener('click', () => {
    const price = 200 * Math.pow(2, gameState.energy_level - 1);
    if (gameState.coins >= price) {
        gameState.coins -= price;
        gameState.energy_level += 1;
        gameState.max_energy += 500;
        gameState.energy = gameState.max_energy; // Полностью восстанавливаем энергию
        updateUI();
        saveUserData();
    }
});

// Покупка авто-тапа
buyAutotapBtn.addEventListener('click', () => {
    const price = gameState.auto_tap_level === 0 ? 500 : 500 * Math.pow(2, gameState.auto_tap_level);
    if (gameState.coins >= price) {
        gameState.coins -= price;
        gameState.auto_tap_level += 1;
        updateUI();
        saveUserData();
    }
});

// Покупка скина
buySkinBtn.addEventListener('click', () => {
    if (gameState.coins >= 1000 && !gameState.skin_bought) {
        gameState.coins -= 1000;
        gameState.skin_bought = true;
        hamsterEl.classList.add('golden');
        updateUI();
        saveUserData();
    }
});

// Загрузка лидерборда
async function loadLeaderboard() {
    try {
        const response = await fetch('/api/leaderboard');
        const leaderboard = await response.json();
        
        const listEl = document.getElementById('leaderboard-list');
        listEl.innerHTML = '';
        
        if (leaderboard.length === 0) {
            listEl.innerHTML = '<div class="loading">Пока нет игроков</div>';
            return;
        }
        
        leaderboard.forEach((player, index) => {
            const rank = index + 1;
            const isYou = player.user_id === String(userId);
            
            let rankClass = '';
            if (rank === 1) rankClass = 'top1';
            else if (rank === 2) rankClass = 'top2';
            else if (rank === 3) rankClass = 'top3';
            
            const item = document.createElement('div');
            item.className = 'leaderboard-item' + (isYou ? ' leaderboard-you' : '');
            item.innerHTML = `
                <div class="leaderboard-rank ${rankClass}">${rank}</div>
                <div class="leaderboard-info">
                    <div class="leaderboard-name">${player.first_name}${isYou ? ' (Вы)' : ''}</div>
                    <div class="leaderboard-stats">Уровень тапа: ${player.multi_tap_level}</div>
                </div>
                <div class="leaderboard-coins">${Math.floor(player.coins)} 🪙</div>
            `;
            listEl.appendChild(item);
        });
    } catch (error) {
        console.error('Ошибка загрузки лидерборда:', error);
        document.getElementById('leaderboard-list').innerHTML = '<div class="loading">Ошибка загрузки</div>';
    }
}

// Инициализация при загрузке
loadUserData();
