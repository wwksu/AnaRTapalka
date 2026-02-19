const tg = window.Telegram?.WebApp;
if (tg) {
    tg.expand();
    tg.ready();
}

const initDataUnsafe = tg?.initDataUnsafe || {};
const initDataRaw = tg?.initData || "";
const userId = initDataUnsafe?.user?.id ? String(initDataUnsafe.user.id) : null;

let gameState = {
    coins: 0,
    energy: 1000,
    max_energy: 1000,
    multi_tap_level: 1,
    energy_level: 1,
    skin_bought: false,
    last_update: Date.now(),
    ban_end_time: 0,
};
let userDataLoading = false;

const coinsEl = document.getElementById("coins");
const currentEnergyEl = document.getElementById("current-energy");
const maxEnergyEl = document.getElementById("max-energy");
const energyFillEl = document.getElementById("energy-fill");
const hamsterEl = document.getElementById("hamster");
const tapAnimationsEl = document.getElementById("tap-animations");

const tapScreen = document.getElementById("tap-screen");
const shopScreen = document.getElementById("shop-screen");
const leaderboardScreen = document.getElementById("leaderboard-screen");
const navTap = document.getElementById("nav-tap");
const navShop = document.getElementById("nav-shop");
const navLeaderboard = document.getElementById("nav-leaderboard");

const buyMultitapBtn = document.getElementById("buy-multitap");
const buyEnergyBtn = document.getElementById("buy-energy");
const buySkinBtn = document.getElementById("buy-skin");
const autoTapItemEl = document.getElementById("buy-autotap")?.closest(".shop-item");
if (autoTapItemEl) {
    autoTapItemEl.style.display = "none";
}

function apiHeaders() {
    const headers = { "Content-Type": "application/json" };
    if (initDataRaw) {
        headers["X-Telegram-Init-Data"] = initDataRaw;
    }
    return headers;
}

async function apiGet(path) {
    const response = await fetch(path, { headers: apiHeaders() });
    if (!response.ok) {
        throw new Error(`API ${response.status}`);
    }
    return response.json();
}

async function apiPost(path, body) {
    const response = await fetch(path, {
        method: "POST",
        headers: apiHeaders(),
        body: JSON.stringify(body),
    });
    if (!response.ok) {
        throw new Error(`API ${response.status}`);
    }
    return response.json();
}

function setGameState(nextState) {
    gameState = {
        ...gameState,
        ...nextState,
    };
    updateUI();
}

function showSetupError(message) {
    const listEl = document.getElementById("leaderboard-list");
    listEl.textContent = message;
    hamsterEl.style.pointerEvents = "none";
    buyMultitapBtn.disabled = true;
    buyEnergyBtn.disabled = true;
    buySkinBtn.disabled = true;
}

async function loadUserData() {
    if (!userId || !initDataRaw) {
        showSetupError("Запускайте приложение только внутри Telegram WebApp");
        return;
    }
    if (userDataLoading) {
        return;
    }

    userDataLoading = true;
    try {
        const data = await apiGet(`/api/user/${encodeURIComponent(userId)}`);
        setGameState(data);
    } catch (error) {
        console.error("Ошибка загрузки данных:", error);
        if (String(error.message || "").includes("401")) {
            showSetupError("Сессия Telegram истекла. Перезапустите мини-приложение.");
        }
    } finally {
        userDataLoading = false;
    }
}

async function performAction(action) {
    if (!userId || !initDataRaw) {
        return null;
    }

    try {
        const result = await apiPost(`/api/action/${encodeURIComponent(userId)}`, { action });
        if (result?.data) {
            setGameState(result.data);
        }
        return result;
    } catch (error) {
        console.error("Ошибка действия:", error);
        return null;
    }
}

function updateUI() {
    coinsEl.textContent = Math.floor(gameState.coins);
    currentEnergyEl.textContent = Math.floor(gameState.energy);
    maxEnergyEl.textContent = gameState.max_energy;

    const energyPercent = (gameState.energy / gameState.max_energy) * 100;
    energyFillEl.style.width = `${Math.max(0, Math.min(100, energyPercent))}%`;

    updateShopUI();

    if (gameState.skin_bought) {
        hamsterEl.classList.add("golden");
    } else {
        hamsterEl.classList.remove("golden");
    }
}

function updateShopUI() {
    const multitapPrice = Math.floor(100 * Math.pow(1.2, gameState.multi_tap_level - 1));
    document.getElementById("multitap-level").textContent = gameState.multi_tap_level;
    document.getElementById("multitap-price").textContent = multitapPrice;
    buyMultitapBtn.disabled = gameState.coins < multitapPrice;

    const energyPrice = Math.floor(200 * Math.pow(1.2, gameState.energy_level - 1));
    document.getElementById("energy-level").textContent = gameState.energy_level;
    document.getElementById("energy-price").textContent = energyPrice;
    buyEnergyBtn.disabled = gameState.coins < energyPrice;

    const skinStatusEl = document.getElementById("skin-status");
    if (gameState.skin_bought) {
        skinStatusEl.textContent = "Куплено";
        buySkinBtn.disabled = true;
        buySkinBtn.textContent = "Куплено";
    } else {
        skinStatusEl.textContent = "Не куплено";
        buySkinBtn.disabled = gameState.coins < 1000;
        buySkinBtn.textContent = "1000 🪙";
    }
}

function createTapAnimation(e, amount) {
    const rect = hamsterEl.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    const animation = document.createElement("div");
    animation.className = "tap-animation";
    animation.textContent = `+${amount}`;
    animation.style.left = `${x}px`;
    animation.style.top = `${y}px`;

    tapAnimationsEl.appendChild(animation);
    setTimeout(() => animation.remove(), 1000);
}

function createComboAnimation(e, amount) {
    const rect = hamsterEl.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    const animation = document.createElement("div");
    animation.className = "tap-animation combo-tap";

    const comboText = document.createElement("div");
    comboText.className = "combo-text";
    comboText.textContent = "COMBO!";

    const comboAmount = document.createElement("div");
    comboAmount.className = "combo-amount";
    comboAmount.textContent = `+${amount}`;

    animation.appendChild(comboText);
    animation.appendChild(comboAmount);
    animation.style.left = `${x}px`;
    animation.style.top = `${y}px`;

    tapAnimationsEl.appendChild(animation);

    for (let i = 0; i < 8; i += 1) {
        const particle = document.createElement("div");
        particle.className = "combo-particle";
        particle.style.left = `${x}px`;
        particle.style.top = `${y}px`;
        particle.style.setProperty("--angle", `${i * 45}deg`);
        tapAnimationsEl.appendChild(particle);
        setTimeout(() => particle.remove(), 800);
    }

    hamsterEl.classList.add("combo-shake");
    setTimeout(() => hamsterEl.classList.remove("combo-shake"), 500);
    setTimeout(() => animation.remove(), 1500);
}

function showBanAlert(banEndTime) {
    const now = Date.now();
    const remaining = Math.max(0, Math.ceil((banEndTime - now) / 1000));
    const minutes = Math.floor(remaining / 60);
    const seconds = remaining % 60;
    alert(`⛔ Вы временно заблокированы за слишком быстрые клики. Осталось: ${minutes}:${String(seconds).padStart(2, "0")}`);
}

let tapInFlight = false;
hamsterEl.addEventListener("click", async (e) => {
    if (tapInFlight) {
        return;
    }

    tapInFlight = true;
    const result = await performAction("tap");
    tapInFlight = false;

    if (!result || !result.event) {
        return;
    }

    if (result.event.status === "ok") {
        const amount = result.event.coins_earned || 0;
        if (result.event.is_combo) {
            createComboAnimation(e, amount);
        } else {
            createTapAnimation(e, amount);
        }
    } else if (result.event.status === "banned") {
        showBanAlert(result.event.ban_end_time || gameState.ban_end_time);
    }
});

navTap.addEventListener("click", () => {
    tapScreen.classList.add("active");
    shopScreen.classList.remove("active");
    leaderboardScreen.classList.remove("active");
    navTap.classList.add("active");
    navShop.classList.remove("active");
    navLeaderboard.classList.remove("active");
});

navShop.addEventListener("click", () => {
    shopScreen.classList.add("active");
    tapScreen.classList.remove("active");
    leaderboardScreen.classList.remove("active");
    navShop.classList.add("active");
    navTap.classList.remove("active");
    navLeaderboard.classList.remove("active");
});

navLeaderboard.addEventListener("click", () => {
    leaderboardScreen.classList.add("active");
    tapScreen.classList.remove("active");
    shopScreen.classList.remove("active");
    navLeaderboard.classList.add("active");
    navTap.classList.remove("active");
    navShop.classList.remove("active");
    loadLeaderboard();
});

buyMultitapBtn.addEventListener("click", async () => {
    await performAction("buy_multitap");
});

buyEnergyBtn.addEventListener("click", async () => {
    await performAction("buy_energy");
});

buySkinBtn.addEventListener("click", async () => {
    await performAction("buy_skin");
});

function createLeaderboardItem(player, rank) {
    const isYou = String(player.user_id) === String(userId);
    const item = document.createElement("div");
    item.className = `leaderboard-item${isYou ? " leaderboard-you" : ""}`;

    const rankEl = document.createElement("div");
    rankEl.className = "leaderboard-rank";
    if (rank === 1) rankEl.classList.add("top1");
    if (rank === 2) rankEl.classList.add("top2");
    if (rank === 3) rankEl.classList.add("top3");
    rankEl.textContent = String(rank);

    const infoEl = document.createElement("div");
    infoEl.className = "leaderboard-info";

    const nameEl = document.createElement("div");
    nameEl.className = "leaderboard-name";
    nameEl.textContent = `${player.first_name || "Игрок"}${isYou ? " (Вы)" : ""}`;

    const statsEl = document.createElement("div");
    statsEl.className = "leaderboard-stats";
    statsEl.textContent = `Уровень тапа: ${player.multi_tap_level}`;

    infoEl.appendChild(nameEl);
    infoEl.appendChild(statsEl);

    const coinsElLocal = document.createElement("div");
    coinsElLocal.className = "leaderboard-coins";
    coinsElLocal.textContent = `${Math.floor(player.coins || 0)} 🪙`;

    item.appendChild(rankEl);
    item.appendChild(infoEl);
    item.appendChild(coinsElLocal);

    return item;
}

async function loadLeaderboard() {
    const listEl = document.getElementById("leaderboard-list");
    try {
        const leaderboard = await apiGet("/api/leaderboard");
        listEl.innerHTML = "";

        if (!Array.isArray(leaderboard) || leaderboard.length === 0) {
            listEl.textContent = "Пока нет игроков";
            return;
        }

        leaderboard.forEach((player, index) => {
            const item = createLeaderboardItem(player, index + 1);
            listEl.appendChild(item);
        });
    } catch (error) {
        console.error("Ошибка загрузки лидерборда:", error);
        listEl.textContent = "Ошибка загрузки";
    }
}

setInterval(() => {
    if (!document.hidden) {
        loadUserData();
    }
}, 15000);

document.addEventListener("visibilitychange", () => {
    if (!document.hidden) {
        loadUserData();
    }
});

loadUserData();
