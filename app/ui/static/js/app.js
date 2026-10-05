/**
 * AutoWING 控制面板前端逻辑
 */

// ── DOM 引用 ─────────────────────────────

const $ = (id) => document.getElementById(id);
const windowStatus = $("windowStatus");
const taskStatus = $("taskStatus");
const statusBadge = $("statusBadge");
const logContainer = $("logContainer");
const windowTitle = $("windowTitle");

// ── 状态轮询 ─────────────────────────────

async function refreshStatus() {
    try {
        const res = await fetch("/api/status");
        const data = await res.json();

        // 窗口/Canvas 状态
        if (data.calibrated) {
            statusBadge.textContent = "● 已就绪";
            statusBadge.className = "badge connected";
            windowStatus.textContent = data.config.window_title || "已绑定";
        } else {
            statusBadge.textContent = "● 未连接";
            statusBadge.className = "badge";
            windowStatus.textContent = "未绑定";
        }

        // 任务状态
        if (data.task && data.task.name) {
            taskStatus.textContent =
                `${data.task.name} [${data.task.state}]`;
        } else {
            taskStatus.textContent = "空闲";
        }
    } catch (e) {
        console.error("状态刷新失败:", e);
    }
}

// 每 2 秒轮询一次
setInterval(refreshStatus, 2000);
refreshStatus();

// ── Canvas 检测 ──────────────────────────

async function detectCanvas() {
    setStatus("CDP 检测 Canvas...", "info");
    try {
        const res = await fetch("/api/detect-canvas", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ method: "cdp" }),
        });
        const data = await res.json();
        if (data.success) {
            addLog("info", `✅ CDP 检测成功: ${data.description}`);
            refreshStatus();
        } else {
            addLog("warning", `⚠️ ${data.error}`);
            addLog("info", "💡 点「重启浏览器(CDP)」自动重启带调试端口的浏览器");
        }
    } catch (e) {
        addLog("error", `❌ 请求失败: ${e.message}`);
    }
}

async function restartBrowserWithCDP() {
    if (!confirm("将关闭当前浏览器并以调试模式重启（标签页会自动恢复），确定？")) {
        return;
    }
    setStatus("重启浏览器并开启 CDP...", "info");
    try {
        const res = await fetch("/api/launch-browser", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ close_first: true }),
        });
        const data = await res.json();
        if (data.success) {
            addLog("info", "✅ 浏览器已重启（CDP 端口就绪）");
            addLog("info", "💡 打开游戏页面后，点击「CDP 检测」");
        } else {
            addLog("error", `❌ ${data.error}`);
        }
    } catch (e) {
        addLog("error", `❌ 请求失败: ${e.message}`);
    }
}

async function bindWindow() {
    setStatus("绑定窗口...", "info");
    try {
        const res = await fetch("/api/bind-window", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                window_title: windowTitle.value,
            }),
        });
        const data = await res.json();
        if (data.success) {
            addLog("info", `✅ 窗口已绑定: ${data.window?.width}×${data.window?.height}`);
            refreshStatus();
        } else {
            addLog("error", `❌ ${data.error || "绑定失败"}`);
        }
    } catch (e) {
        addLog("error", `❌ 请求失败: ${e.message}`);
    }
}

// ── 任务控制 ─────────────────────────────

async function startTask() {
    setStatus("启动任务...", "info");
    try {
        const res = await fetch("/api/start", { method: "POST" });
        const data = await res.json();
        if (data.success) {
            addLog("info", `🚀 任务已启动: ${data.task.name}`);
            refreshStatus();
        } else {
            addLog("error", `❌ ${data.error || "启动失败"}`);
        }
    } catch (e) {
        addLog("error", `❌ 请求失败: ${e.message}`);
    }
}

async function stopTask() {
    try {
        const res = await fetch("/api/stop", { method: "POST" });
        const data = await res.json();
        if (data.success) {
            addLog("warning", "⏹️ 任务已停止");
            refreshStatus();
        }
    } catch (e) {
        addLog("error", `❌ 请求失败: ${e.message}`);
    }
}

// ── 配置 ─────────────────────────────────

function clampNumber(v, min, max, fallback) {
    const n = parseFloat(v);
    if (isNaN(n)) return fallback;
    return Math.min(Math.max(n, min), max);
}

function getSettingsFromUI() {
    return {
        difficulty: $("cfgDifficulty").value,
        strategy_selection: $("cfgStrategy").value,
        max_runs: parseInt($("cfgMaxRuns").value) || 0,
        main_stat: $("cfgMainStat").value,
        use_energy_item: $("cfgEnergyItem").checked,
        energy_multiplier: parseInt($("cfgEnergyMultiplier").value) || 1,
        use_mem: $("cfgUseMem").checked,
        handle_agreement: $("cfgHandleAgreement").checked,
        auto_continuous_mining: $("cfgAutoContinuousMining").checked,
        browser_path: $("browserPath").value,
        wait_offset: clampNumber($("cfgWaitOffset").value, 0, 10, 0),
        pre_wait_offset: clampNumber($("cfgPreWaitOffset").value, 0, 10, 0),
        qte_interval_offset: clampNumber($("cfgQteIntervalOffset").value, -1, 1, 0),
        loop_interval: clampNumber($("cfgLoopInterval").value, 0.05, 1, 0.05),
        notifications_enabled: $("cfgNotificationsEnabled").checked,
        notification_urls: $("notificationUrls").value.split(/\r?\n/).map((url) => url.trim()).filter(Boolean),
        notification_min_level: $("cfgNotificationMinLevel").value,
        notification_dedup_seconds: clampNumber($("cfgNotificationDedup").value, 0, 86400, 60),
        notification_rate_limit_seconds: clampNumber($("cfgNotificationRateLimit").value, 0, 86400, 30),
        notification_queue_size: Math.round(clampNumber($("cfgNotificationQueueSize").value, 1, 1000, 100)),
    };
}

function setSettingsToUI(cfg) {
    if (cfg.difficulty) $("cfgDifficulty").value = cfg.difficulty;
    if (cfg.strategy_selection) $("cfgStrategy").value = cfg.strategy_selection;
    if (cfg.max_runs !== undefined) $("cfgMaxRuns").value = cfg.max_runs;
    if (cfg.main_stat) $("cfgMainStat").value = cfg.main_stat;
    if (cfg.use_energy_item !== undefined) $("cfgEnergyItem").checked = cfg.use_energy_item;
    if (cfg.energy_multiplier !== undefined) $("cfgEnergyMultiplier").value = cfg.energy_multiplier;
    if (cfg.use_mem !== undefined) $("cfgUseMem").checked = cfg.use_mem;
    if (cfg.handle_agreement !== undefined) $("cfgHandleAgreement").checked = cfg.handle_agreement;
    if (cfg.auto_continuous_mining !== undefined) $("cfgAutoContinuousMining").checked = cfg.auto_continuous_mining;
    if (cfg.browser_path !== undefined) $("browserPath").value = cfg.browser_path;
    if (cfg.wait_offset !== undefined) $("cfgWaitOffset").value = clampNumber(cfg.wait_offset, 0, 10, 0);
    if (cfg.pre_wait_offset !== undefined) $("cfgPreWaitOffset").value = clampNumber(cfg.pre_wait_offset, 0, 10, 0);
    if (cfg.qte_interval_offset !== undefined) $("cfgQteIntervalOffset").value = clampNumber(cfg.qte_interval_offset, -1, 1, 0);
    if (cfg.loop_interval !== undefined) $("cfgLoopInterval").value = clampNumber(cfg.loop_interval, 0.05, 1, 0.05);
    if (cfg.notifications_enabled !== undefined) $("cfgNotificationsEnabled").checked = cfg.notifications_enabled;
    if (cfg.notification_urls !== undefined) $("notificationUrls").value = (cfg.notification_urls || []).join("\n");
    if (cfg.notification_min_level) $("cfgNotificationMinLevel").value = cfg.notification_min_level;
    if (cfg.notification_dedup_seconds !== undefined) $("cfgNotificationDedup").value = clampNumber(cfg.notification_dedup_seconds, 0, 86400, 60);
    if (cfg.notification_rate_limit_seconds !== undefined) $("cfgNotificationRateLimit").value = clampNumber(cfg.notification_rate_limit_seconds, 0, 86400, 30);
    if (cfg.notification_queue_size !== undefined) $("cfgNotificationQueueSize").value = Math.round(clampNumber(cfg.notification_queue_size, 1, 1000, 100));
}

function toggleCard(cardId) {
    const card = $(cardId);
    if (!card) return;
    const body = card.querySelector(".collapsible-body");
    const button = card.querySelector(".collapse-btn");
    if (!body) return;
    const collapsed = body.classList.toggle("is-collapsed");
    if (button) {
        button.setAttribute("aria-expanded", String(!collapsed));
    }
}

async function sendNotificationTest() {
    try {
        const response = await fetch("/api/notifications/test", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
        });
        const data = await response.json();
        if (data.success && data.queued) {
            addLog("info", "🔔 测试通知已进入发送队列");
        } else if (data.success) {
            addLog("warning", "⚠️ 测试通知未入队，请检查通知是否启用及 URL 配置");
        } else {
            addLog("error", `❌ ${data.error || "测试通知失败"}`);
        }
    } catch (e) {
        addLog("error", `❌ ${e.message}`);
    }
}

async function saveStrategyConfig() {
    const cfg = getSettingsFromUI();
    cfg.skill_learn_order = _learnOrder;
    cfg.skill_priority = _skillPriority;
    try {
        const r = await fetch("/api/strategy-config", { method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ config: cfg }) });
        const d = await r.json();
        if (d.success) { addLog("info", "💾 所有配置已保存"); setSettingsToUI(d.config); }
        else { addLog("error", "❌ 保存失败"); }
    } catch (e) { addLog("error", `❌ ${e.message}`); }
}

async function loadStrategyConfig() {
    try {
        const res = await fetch("/api/strategy-config");
        const data = await res.json();
        if (data.success && data.config) {
            const cfg = data.config;
            setSettingsToUI(cfg);
            _learnOrder = cfg.skill_learn_order || [];
            _skillPriority = cfg.skill_priority || [];
            renderLearnOrder();
            renderSkillPriority();
            addLog("info", "📂 已读取策略配置");
        }
    } catch (e) {
        addLog("error", `❌ ${e.message}`);
    }
}

async function resetStrategyConfig() {
    if (!confirm("重置所有策略配置？")) return;
    try {
        const res = await fetch("/api/strategy-config/reset", { method: "POST" });
        const data = await res.json();
        if (data.success) {
            setSettingsToUI({});
            _learnOrder = [];
            _skillPriority = [];
            renderLearnOrder();
            renderSkillPriority();
            addLog("info", "↺ 策略配置已重置");
        }
    } catch (e) {
        addLog("error", `❌ ${e.message}`);
    }
}

// ── 技能学习顺序 ─────────────────────────

let _learnOrder = [];

function renderLearnOrder() {
    const el = $("learnOrderList");
    if (!_learnOrder.length) {
        el.innerHTML = '<span style="color:var(--text-dim)">(空)</span>';
        return;
    }
    el.innerHTML = _learnOrder.map((item, i) =>
        `<div style="padding:2px 0;font-size:11px">
            <strong>#${i + 1}</strong> (${item.x}, ${item.y})
            ${item.label || ''}
            <span style="color:var(--text-dim)">${item.wait || 0.3}s</span>
        </div>`
    ).join("");
}

// ── 录制状态 ──
let _recordingPoints = [];

function recordLearnOrder() {
    _recordingPoints = [];
    const modal = $("recordModal");
    modal.style.display = "flex";
    const img = $("recordCanvasImg");

    if (!img) {
        addLog("error", "❌ 找不到 recordCanvasImg 元素！");
        return;
    }
    
    addLog("✅ 找到 img 元素:", img);

    addLog("info", "🔗 点击事件已绑定到截图");

    img.src = "/api/capture-canvas?" + Date.now(); // 加时间戳防缓存
    $("recordCount").textContent = "0";
    $("recordedPoints").innerHTML = '<span style="color:var(--text-dim)">(还没有记录点)</span>';
    $("recordMarkers").innerHTML = "";
    addLog("info", "📸 打开录制面板，点击截图记录技能节点位置");
}

function closeRecordModal() {
    $("recordModal").style.display = "none";
    _recordingPoints = [];
}

function handleRecordClick(e) {
    const img = $("recordCanvasImg");
    if (!img.complete || img.naturalWidth === 0) {
        addLog("warning", "⏳ 截图未加载完成");
        return;
    }

    const rect = img.getBoundingClientRect();
    const scaleX = img.naturalWidth / rect.width;
    const scaleY = img.naturalHeight / rect.height;
    
    const imgX = Math.round((e.clientX - rect.left) * scaleX);
    const imgY = Math.round((e.clientY - rect.top) * scaleY);

    // 转换为 1600x902 参考坐标
    const refX = Math.round(imgX * 1600 / img.naturalWidth);
    const refY = Math.round(imgY * 902 / img.naturalHeight);

    addRecordedPoint(refX, refY);
}

function addRecordedPoint(x, y, wait) {
    wait = wait || parseFloat($("manualRecWait").value) || 0.3;
    const idx = _recordingPoints.length;
    _recordingPoints.push({ x, y, wait, label: "" });
    renderRecordedPoints();

    // 在截图上画标记
    const markers = $("recordMarkers");
    const img = $("recordCanvasImg");
    
    // ✅ 1600x902 坐标 → 实际图片坐标 → 百分比
    // 实际图片尺寸 = img.naturalWidth x img.naturalHeight (如 1136x640)
    const pctX = (x / 1600) * (img.naturalWidth / 1600) * 100;  // 简化为 (x / 1600) * 100
    const pctY = (y / 902) * (img.naturalHeight / 902) * 100;   // 简化为 (y / 902) * 100
    
    // 实际上因为比例相同 (1600:902 ≈ 1136:640)，直接用百分比即可
    const dot = document.createElement("div");
    dot.className = "record-marker";
    dot.style.left = (x / 1600 * 100) + "%";
    dot.style.top = (y / 902 * 100) + "%";
    dot.textContent = idx + 1;
    markers.appendChild(dot);
}

function renderRecordedPoints() {
    const el = $("recordedPoints");
    $("recordCount").textContent = _recordingPoints.length;
    if (!_recordingPoints.length) {
        el.innerHTML = '<span style="color:var(--text-dim)">(还没有记录点)</span>';
        return;
    }
    el.innerHTML = _recordingPoints.map((p, i) =>
        `<div class="point-item">
            <span class="point-num">#${i + 1}</span>
            <span>(${p.x}, ${p.y})</span>
            <span style="color:var(--text-dim)">${p.wait}s</span>
            <span class="point-del" onclick="removeRecordedPoint(${i})">✕</span>
        </div>`
    ).join("");
}

function removeRecordedPoint(i) {
    _recordingPoints.splice(i, 1);
    $("recordMarkers").innerHTML = "";
    _recordingPoints.forEach((p, idx) => {
        const markers = $("recordMarkers");
        const dot = document.createElement("div");
        dot.className = "record-marker";
        dot.style.left = (p.x / 1600 * 100) + "%";
        dot.style.top = (p.y / 902 * 100) + "%";
        dot.textContent = idx + 1;
        markers.appendChild(dot);
    });
    renderRecordedPoints();
}

function clearRecordedPoints() {
    _recordingPoints = [];
    $("recordMarkers").innerHTML = "";
    renderRecordedPoints();
    addLog("info", "🗑️ 录制点已清空");
}

function addManualPoint() {
    const x = parseFloat($("manualRecX").value);
    const y = parseFloat($("manualRecY").value);
    if (isNaN(x) || isNaN(y)) {
        addLog("warning", "⚠️ 请输入有效的 X, Y 坐标");
        return;
    }
    addRecordedPoint(x, y);
    $("manualRecX").value = "";
    $("manualRecY").value = "";
}

function saveRecordedPoints() {
    if (!_recordingPoints.length) {
        addLog("warning", "⚠️ 没有录制到任何点");
        closeRecordModal();
        return;
    }
    _learnOrder = [..._recordingPoints];
    renderLearnOrder();
    // 保存到后端
    saveSkillPriority();
    addLog("info", `💾 已保存 ${_learnOrder.length} 个技能学习点`);
    closeRecordModal();
}

function clearLearnOrder() {
    _learnOrder = [];
    renderLearnOrder();
    addLog("info", "🗑️ 学习顺序已清空");
}

async function exportLearnOrder() {
    if (!_learnOrder.length) { addLog("warning", "⚠️ 学习顺序为空"); return; }
    setStatus("导出学习顺序...", "info");
    try {
        const r = await fetch("/api/learn-order/export", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ data: _learnOrder }),
        });
        const d = await r.json();
        if (d.success) addLog("info", `📤 已导出: ${d.path}`);
        else addLog("warning", `⚠️ ${d.error || "导出失败"}`);
    } catch (e) {
        addLog("error", `❌ ${e.message}`);
    }
}

async function importLearnOrder() {
    setStatus("导入学习顺序...", "info");
    try {
        const r = await fetch("/api/learn-order/import", { method: "POST" });
        const d = await r.json();
        if (d.success && Array.isArray(d.data)) {
            _learnOrder = d.data;
            renderLearnOrder();
            await saveSkillPriority();  // 导入后持久化到策略配置
            addLog("info", `📥 已导入并保存 ${_learnOrder.length} 个点`);
        } else {
            addLog("warning", `⚠️ ${d.error || "导入失败"}`);
        }
    } catch (e) {
        addLog("error", `❌ ${e.message}`);
    }
}

async function browseBrowserPath() {
    try {
        const r = await fetch("/api/browse-file", { method: "POST" });
        const d = await r.json();
        if (d.success) {
            $("browserPath").value = d.path;
        } else if (d.error) {
            addLog("warning", `⚠️ ${d.error}`);
        }
    } catch (e) {
        addLog("error", `❌ ${e.message}`);
    }
}

// ── 技能优先级 ───────────────────────────

let _allSkills = [];
let _skillPriority = [];
let _prioSaveTimer = null;

async function loadSkillList() {
    try {
        const r = await fetch("/api/strategy-config/skills");
        const d = await r.json();
        if (d.success) _allSkills = d.skills || [];
    } catch (e) {}
}

function skillName(skill) {
    return skill.name || skill.file || skill;
}

function skillFile(skill) {
    return skill.file || skill;
}

function renderSkillPriority() {
    const el = $("skillPriorityList");
    if (!el) return;
    const unused = _allSkills.filter(s => !_skillPriority.includes(skillFile(s)));
    let html = '<div style="margin-bottom:4px;font-size:11px;color:var(--text-dim)">优先级顺序</div>';
    if (_skillPriority.length) {
        html += _skillPriority.map((fn, i) => {
            const info = _allSkills.find(s => skillFile(s) === fn);
            const name = info ? skillName(info) : fn;
            return `<div class="skill-prio-item">
                <span class="skill-prio-num">#${i+1}</span>
                <img class="skill-thumb" src="/api/skill-image/${fn}" alt="" loading="lazy">
                <span class="skill-prio-name">${name}</span>
                <button class="btn btn-sm btn-outline skill-btn-up" onclick="movePrio(${i},-1)">↑</button>
                <button class="btn btn-sm btn-outline skill-btn-down" onclick="movePrio(${i},1)">↓</button>
                <button class="btn btn-sm btn-outline skill-btn-remove" onclick="removePrio(${i})">×</button>
            </div>`;
        }).join("");
    } else {
        html += '<div style="color:var(--text-dim);font-size:11px;padding:4px 0">(未设置, 点下方添加)</div>';
    }
    if (unused.length) {
        html += '<div style="margin-top:6px;margin-bottom:2px;font-size:11px;color:var(--text-dim)">可用技能</div>';
        html += unused.map(s => {
            const fn = skillFile(s);
            const name = skillName(s);
            return `<button class="btn btn-sm btn-outline skill-add-btn" onclick="addPrio('${fn}')">
                <img class="skill-thumb-sm" src="/api/skill-image/${fn}" alt="" loading="lazy">
                <span>+${name}</span>
            </button>`;
        }).join("");
    }
    el.innerHTML = html;
}

function addPrio(n) {
    if (!_skillPriority.includes(n)) {
        _skillPriority.push(n);
        renderSkillPriority();
        autoSavePrio();
    }
}
function removePrio(i) {
    _skillPriority.splice(i, 1);
    renderSkillPriority();
    autoSavePrio();
}
function movePrio(i, d) {
    const ni = i + d;
    if (ni < 0 || ni >= _skillPriority.length) return;
    [_skillPriority[i], _skillPriority[ni]] = [_skillPriority[ni], _skillPriority[i]];
    renderSkillPriority();
    autoSavePrio();
}

function autoSavePrio() {
    clearTimeout(_prioSaveTimer);
    _prioSaveTimer = setTimeout(() => saveSkillPriority(), 800);
}

async function saveSkillPriority() {
    const cfg = getSettingsFromUI();
    cfg.skill_priority = _skillPriority;
    cfg.skill_learn_order = _learnOrder;
    try {
        const r = await fetch("/api/strategy-config", { method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ config: cfg }) });
        const d = await r.json();
        if (d.success) addLog("info", "💾 技能设置已保存");
    } catch (e) { addLog("error", `❌ ${e.message}`); }
}

// 页面加载时读取配置
setTimeout(loadStrategyConfig, 500);
setTimeout(async () => {
    await loadSkillList();
    try {
        const r = await fetch("/api/strategy-config");
        const d = await r.json();
        if (d.success && d.config) {
            _learnOrder = d.config.skill_learn_order || [];
            _skillPriority = d.config.skill_priority || [];
            renderLearnOrder();
            renderSkillPriority();
        }
    } catch (e) {}
}, 1000);

// ── 日志 ─────────────────────────────────

function addLog(level, message) {
    const el = document.createElement("div");
    el.className = `log-entry level-${level}`;
    const time = new Date().toLocaleTimeString("zh-CN", { hour12: false });
    el.innerHTML = `<span class="log-time">[${time}]</span><span class="log-msg">${escapeHtml(message)}</span>`;
    logContainer.appendChild(el);
    logContainer.scrollTop = logContainer.scrollHeight;

    // 移除占位
    const empty = logContainer.querySelector(".log-empty");
    if (empty) empty.remove();
}

function clearLog() {
    logContainer.innerHTML = `<div class="log-empty">日志已清除</div>`;
}

function setStatus(text, level) {
    addLog(level, text);
}

function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}

// ── SSE 日志流 ───────────────────────────

function connectSSE() {
    const evtSource = new EventSource("/api/logs/stream");
    evtSource.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            if (data.type === "log") {
                addLog(data.level, data.message);
            }
        } catch (e) {
            // 心跳包忽略
        }
    };
    evtSource.onerror = () => {
        console.warn("SSE 断线，3 秒后重连...");
        setTimeout(connectSSE, 3000);
    };
}

// 启动 SSE
connectSSE();
