"""
HTML dashboard template for the Owlet Dream Logger.

This module contains the complete HTML/CSS/JavaScript for the real-time
monitoring dashboard that displays vitals and diagnostics.
"""

HTML_CONTENT = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Owlet Dream Logger</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&family=JetBrains+Mono:wght@400&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg: #f0f2f5;
            --card-bg: #ffffff;
            --text-main: #1f2937;
            --text-sub: #6b7280;
            --accent-hr: #ef4444;
            --accent-ox: #3b82f6;
            --accent-ok: #10b981;
            --accent-warn: #f59e0b;
            --border: #e5e7eb;
        }
        body { font-family: 'Inter', sans-serif; background: var(--bg); color: var(--text-main); margin: 0; padding: 20px; }
        .container { max-width: 1200px; margin: 0 auto; }
        
        header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 25px; }
        h1 { font-size: 1.8rem; font-weight: 800; margin: 0; letter-spacing: -0.025em; }
        .status-badge { background: #e5e7eb; padding: 6px 16px; border-radius: 99px; font-size: 0.85rem; font-weight: 600; }
        .status-connected { background: #d1fae5; color: #065f46; }
        .status-disconnected { background: #fee2e2; color: #991b1b; }
        
        .header-right { display: flex; align-items: center; gap: 15px; }
        .btn-logout {
            background: #ef4444;
            color: white;
            border: none;
            padding: 8px 18px;
            border-radius: 8px;
            font-size: 0.85rem;
            font-weight: 600;
            cursor: pointer;
            transition: background 0.2s;
        }
        .btn-logout:hover {
            background: #dc2626;
        }
        .btn-quit {
            background: #7c3aed;
            color: white;
            border: none;
            padding: 8px 18px;
            border-radius: 8px;
            font-size: 0.85rem;
            font-weight: 600;
            cursor: pointer;
            transition: background 0.2s;
        }
        .btn-quit:hover {
            background: #6d28d9;
        }


        .section-title { font-size: 0.95rem; font-weight: 700; color: var(--text-sub); text-transform: uppercase; margin: 30px 0 10px 0; letter-spacing: 0.05em; }

        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 15px; }
        
        .card { background: var(--card-bg); padding: 20px; border-radius: 16px; box-shadow: 0 1px 2px rgba(0,0,0,0.05); border: 1px solid var(--border); display: flex; flex-direction: column; }
        
        .card-label { font-size: 0.75rem; color: var(--text-sub); font-weight: 600; text-transform: uppercase; margin-bottom: 5px; }
        .card-value { font-size: 2rem; font-weight: 800; line-height: 1.1; }
        .card-sub { font-size: 0.85rem; color: var(--text-sub); margin-top: auto; padding-top: 10px; font-weight: 500; }
        .unit { font-size: 1rem; color: var(--text-sub); font-weight: 600; }

        .tech-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 10px; }
        .tech-card { background: var(--card-bg); padding: 15px; border-radius: 12px; border: 1px solid var(--border); }
        .tech-val { font-family: 'JetBrains Mono', monospace; font-size: 1.1rem; font-weight: 700; color: #374151; margin-top: 4px; }

        /* Wiggle Slider */
        .wiggle-container { margin-top: 10px; margin-bottom: 5px; position: relative; }
        .wiggle-track {
            height: 12px;
            width: 100%;
            border-radius: 6px;
            background: linear-gradient(90deg, #4ade80 0%, #fbbf24 50%, #f87171 100%);
            position: relative;
        }
        .wiggle-thumb {
            position: absolute;
            top: 50%;
            left: 0%; 
            transform: translate(-50%, -50%);
            width: 18px;
            height: 18px;
            background: white;
            border: 3px solid #374151;
            border-radius: 50%;
            box-shadow: 0 2px 4px rgba(0,0,0,0.2);
            transition: left 0.3s ease-out;
        }
        .wiggle-labels { display: flex; justify-content: space-between; font-size: 0.75rem; color: var(--text-sub); margin-top: 6px; font-weight: 600; }

        .c-hr { color: var(--accent-hr); }
        .c-ox { color: var(--accent-ox); }
        .c-ok { color: var(--accent-ok); }
        .c-warn { color: var(--accent-warn); }

        .table-wrap { margin-top: 30px; background: white; border-radius: 16px; border: 1px solid var(--border); overflow: hidden; }
        .table-header-row { padding: 15px 20px; background: #f9fafb; border-bottom: 1px solid var(--border); font-weight: 700; font-size: 0.9rem; }
        table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
        td, th { padding: 12px 20px; text-align: left; border-bottom: 1px solid var(--border); }
        th { background: #f9fafb; color: var(--text-sub); font-weight: 600; text-transform: uppercase; font-size: 0.75rem; }
        
        .json-block { font-family: 'JetBrains Mono', monospace; font-size: 0.75rem; color: #374151; white-space: pre-wrap; word-break: break-all; max-width: 450px; }
        
        .quality-badge {
            display: inline-block;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 0.7rem;
            font-weight: 700;
            text-transform: uppercase;
            margin-left: 10px;
            vertical-align: middle;
        }
        
        /* Warning Banner */
        .warning-banner {
            background: #fef3c7;
            border: 2px solid #f59e0b;
            border-radius: 12px;
            padding: 15px 20px;
            margin-bottom: 20px;
            display: none;
            align-items: center;
            gap: 12px;
        }
        .warning-banner.show {
            display: flex;
        }
        .warning-banner.critical {
            background: #fee2e2;
            border-color: #ef4444;
        }

        .warning-icon {
            font-size: 1.5rem;
            flex-shrink: 0;
        }
        .warning-content {
            flex: 1;
        }
        .warning-title {
            font-weight: 700;
            font-size: 0.95rem;
            margin-bottom: 4px;
            color: #92400e;
        }
        .warning-banner.critical .warning-title {
            color: #991b1b;
        }

        .warning-message {
            font-size: 0.85rem;
            color: #78350f;
        }
        .warning-banner.critical .warning-message {
            color: #7f1d1d;
        }

        /* Alert Banner */
        .alert-banner {
            border-radius: 12px;
            padding: 12px 20px;
            margin-bottom: 10px;
            display: none;
            align-items: center;
            gap: 10px;
            font-weight: 600;
            font-size: 0.9rem;
        }
        .alert-banner.show { display: flex; }
        .alert-banner.alert-critical {
            background: #fee2e2; border: 2px solid #ef4444; color: #991b1b;
        }
        .alert-banner.alert-warning {
            background: #fef3c7; border: 2px solid #f59e0b; color: #92400e;
        }
        .alert-banner.alert-info {
            background: #dbeafe; border: 2px solid #3b82f6; color: #1e40af;
        }
        .alert-icon { font-size: 1.3rem; flex-shrink: 0; }
        .alert-text { flex: 1; }

    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>Owlet Dream Logger</h1>
            <div class="header-right">
                <div id="status" class="status-badge">Connecting...</div>
                <button id="logoutBtn" class="btn-logout">Logout</button>
                <button id="quitBtn" class="btn-quit">Quit App</button>
            </div>
        </header>

        <!-- Device Alert Banner -->
        <div id="alertBanner" class="alert-banner">
            <div class="alert-icon">🚨</div>
            <div class="alert-text" id="alertText"></div>
        </div>

        <!-- Warning Banner for Stale Data -->
        <div id="warningBanner" class="warning-banner">
            <div class="warning-icon">⚠️</div>
            <div class="warning-content">
                <div class="warning-title">Connection Issue Detected</div>
                <div class="warning-message" id="warningMessage">Data may be stale</div>
            </div>
        </div>

        <div class="section-title">Live Vitals</div>
        <div class="grid">
            <div class="card">
                <div class="card-label">Heart Rate</div>
                <div class="card-value c-hr">
                    <span id="hr">--</span> <span class="unit">BPM</span>
                    <span id="hr-quality" class="quality-badge" style="display:none">--</span>
                </div>
                <div class="card-sub">
                    <span style="color: #10b981;">●</span> 100-160 Normal
                    <span style="color: #f59e0b; margin-left: 8px;">●</span> 90-99, 161-180 Alert
                    <span style="color: #ef4444; margin-left: 8px;">●</span> &lt;90, &gt;180 Low/High
                </div>
            </div>
            
            <div class="card">
                <div class="card-label">Oxygen (SpO2)</div>
                <div class="card-value c-ox"><span id="ox">--</span> <span class="unit">%</span></div>
                <div class="card-sub">
                    Avg: <span id="oxta">--</span>% 
                    <span style="margin-left: 10px;">
                        <span style="color: #3b82f6;">●</span> ≥95 Normal
                        <span style="color: #f59e0b; margin-left: 8px;">●</span> 90-94 Low
                        <span style="color: #ef4444; margin-left: 8px;">●</span> &lt;90 Very Low
                    </span>
                </div>
            </div>

            <div class="card">
                <div class="card-label">Baby Status</div>
                <div class="wiggle-container">
                    <div class="wiggle-track">
                        <div id="wiggle-thumb" class="wiggle-thumb"></div>
                    </div>
                    <div class="wiggle-labels">
                        <span>Peaceful</span>
                        <span>Wiggling</span>
                    </div>
                </div>
                <div class="card-sub">
                    Raw Intensity (mv): <span id="mv">--</span>
                </div>
            </div>

            <div class="card">
                <div class="card-label">Data Freshness</div>
                <div class="card-value"><span id="lag">--</span> <span class="unit">sec</span></div>
                <div class="card-sub">Connection Health</div>
            </div>
        </div>

        <div class="section-title">Technical Diagnostics</div>
        <div class="tech-grid">
            <div class="tech-card">
                <div class="card-label">Monitoring Status</div>
                <div class="tech-val" id="onm">--</div>
            </div>
            <div class="tech-card">
                <div class="card-label">Band Placement</div>
                <div class="tech-val" id="bp">--</div>
            </div>
            <div class="tech-card">
                <div class="card-label">Monitor Ready</div>
                <div class="tech-val" id="mrs">--</div>
            </div>
            <div class="tech-card">
                <div class="card-label">Base Station</div>
                <div class="tech-val" id="bso">--</div>
            </div>
            <div class="tech-card">
                <div class="card-label">Movement %</div>
                <div class="tech-val" id="mvb">--</div>
            </div>
            <div class="tech-card">
                <div class="card-label">Sleep State</div>
                <div class="tech-val" id="ss">--</div>
            </div>
            <div class="tech-card">
                <div class="card-label">WiFi Signal</div>
                <div class="tech-val" id="rsi">--</div>
            </div>
            <div class="tech-card">
                <div class="card-label">Sock Conn</div>
                <div class="tech-val" id="sc">--</div>
            </div>
            <div class="tech-card">
                <div class="card-label">Charging</div>
                <div class="tech-val" id="chg">--</div>
            </div>
            <div class="tech-card">
                <div class="card-label">Battery</div>
                <div class="tech-val" id="bat">--</div>
            </div>
            <div class="tech-card">
                <div class="card-label">Skin Temp</div>
                <div class="tech-val" id="st">--</div>
            </div>
            <div class="tech-card">
                <div class="card-label">Sock Off</div>
                <div class="tech-val" id="sock-off">--</div>
            </div>
        </div>

        <div class="section-title">Alert History Summary</div>
        <div class="tech-grid">
            <div class="tech-card"><div class="card-label">Total Alerts</div><div class="tech-val" id="sum-total">--</div></div>
            <div class="tech-card"><div class="card-label">Alert Types</div><div class="tech-val" id="sum-types" style="font-size:0.85rem">--</div></div>
            <div class="tech-card"><div class="card-label">HR During Alerts</div><div class="tech-val" id="sum-hr">--</div></div>
            <div class="tech-card"><div class="card-label">SpO2 During Alerts</div><div class="tech-val" id="sum-ox">--</div></div>
        </div>

        <div class="section-title">Device &amp; Firmware</div>
        <div class="tech-grid">
            <div class="tech-card"><div class="card-label">Base Firmware</div><div class="tech-val" id="info-base-fw">--</div></div>
            <div class="tech-card"><div class="card-label">Sock Firmware</div><div class="tech-val" id="info-sock-fw">--</div></div>
            <div class="tech-card"><div class="card-label">Base Hardware</div><div class="tech-val" id="info-base-hw">--</div></div>
            <div class="tech-card"><div class="card-label">Flash Version</div><div class="tech-val" id="info-flash" style="font-size:0.75rem">--</div></div>
            <div class="tech-card"><div class="card-label">Sock MAC</div><div class="tech-val" id="info-sock-mac">--</div></div>
            <div class="tech-card"><div class="card-label">Base MAC</div><div class="tech-val" id="info-base-mac">--</div></div>
            <div class="tech-card"><div class="card-label">FW Update</div><div class="tech-val" id="info-fw-update">--</div></div>
            <div class="tech-card"><div class="card-label">Battery Raw</div><div class="tech-val" id="info-battery-raw">--</div></div>
        </div>

        <div class="section-title">Monitoring Settings</div>
        <div class="tech-grid">
            <div class="tech-card"><div class="card-label">Monitor Mode</div><div class="tech-val" id="info-onm-setting">--</div></div>
            <div class="tech-card"><div class="card-label">SpO2 Baseline</div><div class="tech-val" id="info-ox-baseline">--</div></div>
            <div class="tech-card"><div class="card-label">HR Baseline</div><div class="tech-val" id="info-hr-baseline">--</div></div>
            <div class="tech-card"><div class="card-label">Sleep State</div><div class="tech-val" id="info-sleep-state">--</div></div>
        </div>

        <div class="table-wrap">
            <div class="table-header-row">Alert History <span id="alert-history-count" style="font-weight:400; color:#6b7280; margin-left:10px;"></span></div>
            <div style="max-height: 400px; overflow-y: auto;">
            <table>
                <thead>
                    <tr>
                        <th width="8%">#</th>
                        <th width="15%">Heart Rate</th>
                        <th width="15%">SpO2</th>
                        <th width="12%">Duration</th>
                        <th width="25%">Alert Type</th>
                    </tr>
                </thead>
                <tbody id="alert-history-body"></tbody>
            </table>
            </div>
        </div>
    </div>

<script>
    // Establish WebSocket connection to receive real-time data from the server
    const ws = new WebSocket("ws://" + window.location.host + "/ws");

    // Update connection status badge when WebSocket opens
    ws.onopen = () => {
        document.getElementById("status").innerText = "Connected";
        document.getElementById("status").className = "status-badge status-connected";
    };
    // Update connection status badge when WebSocket closes
    ws.onclose = () => {
        document.getElementById("status").innerText = "Disconnected";
        document.getElementById("status").className = "status-badge status-disconnected";
    };

    // Process incoming data messages from the server
    ws.onmessage = (event) => {
        const payload = JSON.parse(event.data);
        if (payload.error) return;

        const v = payload.vitals || {};
        const props = payload.all_properties || [];
        const meta = payload.meta || {};
        const alerts = payload.alerts || {};

        // --- DEVICE ALERTS ---
        const alertBanner = document.getElementById("alertBanner");
        const alertText = document.getElementById("alertText");
        const activeAlerts = [];

        if (alerts.critical_oxygen) activeAlerts.push("🔴 Critical Oxygen Level");
        if (alerts.low_oxygen) activeAlerts.push("🟡 Low Oxygen Alert");
        if (alerts.low_heart_rate) activeAlerts.push("🔴 Low Heart Rate");
        if (alerts.high_heart_rate) activeAlerts.push("🔴 High Heart Rate");
        if (alerts.critical_battery) activeAlerts.push("🔴 Critical Battery");
        if (alerts.low_battery) activeAlerts.push("🟡 Low Battery");
        if (alerts.sock_disconnected) activeAlerts.push("🟠 Sock Disconnected");
        if (alerts.sock_off) activeAlerts.push("🟠 Sock Off");
        if (alerts.lost_power) activeAlerts.push("🔴 Lost Power");

        if (activeAlerts.length > 0) {
            const hasCritical = alerts.critical_oxygen || alerts.low_heart_rate
                || alerts.high_heart_rate || alerts.critical_battery || alerts.lost_power;
            alertBanner.className = "alert-banner show " + (hasCritical ? "alert-critical" : "alert-warning");
            alertText.innerText = activeAlerts.join("  •  ");
        } else {
            alertBanner.className = "alert-banner";
        }

        // --- STALE DATA WARNING BANNER ---
        const warningBanner = document.getElementById("warningBanner");
        const warningMessage = document.getElementById("warningMessage");
        
        if (meta.stale_warning) {
            warningBanner.classList.add("show");
            warningMessage.innerText = meta.stale_message || "Data may be stale";
            
            if (meta.stale_critical) {
                warningBanner.classList.add("critical");
            } else {
                warningBanner.classList.remove("critical");
            }
        } else {
            warningBanner.classList.remove("show", "critical");
        }

        // --- 1. STALE DATA DETECTOR ---
        // Tracks if heart rate value hasn't changed to detect frozen/stale data
        if (typeof window.lastHrValue === 'undefined') {
            window.lastHrValue = -1;
            window.hrStaleCount = 0;
        }
        const currentHr = v.hr;
        if (currentHr === window.lastHrValue) {
            window.hrStaleCount++;
        } else {
            window.hrStaleCount = 0;
            window.lastHrValue = currentHr;
        }

        // --- 2. MAIN CARD UPDATES ---
        // Update primary vitals display (heart rate, oxygen saturation)
        const hrElement = document.getElementById("hr");
        hrElement.innerText = currentHr ?? "--";
        
        // Dynamic heart rate color coding based on baby heart rate ranges
        if (currentHr && currentHr !== "--") {
            if (currentHr >= 100 && currentHr <= 160) {
                // Normal range - green
                hrElement.parentElement.style.color = "#10b981";
            } else if ((currentHr >= 90 && currentHr < 100) || (currentHr > 160 && currentHr <= 180)) {
                // Slightly concerning - orange/yellow
                hrElement.parentElement.style.color = "#f59e0b";
            } else {
                // Very concerning - red
                hrElement.parentElement.style.color = "#ef4444";
            }
        } else {
            // No data - default gray
            hrElement.parentElement.style.color = "#6b7280";
        }
        
        document.getElementById("ox").innerText = v.ox ?? "--";
        
        // Dynamic oxygen saturation color coding
        const oxElement = document.getElementById("ox");
        if (v.ox && v.ox !== "--") {
            if (v.ox >= 95) {
                // Normal range - blue (keeping brand color)
                oxElement.parentElement.style.color = "#3b82f6";
            } else if (v.ox >= 90 && v.ox < 95) {
                // Slightly low - orange/yellow
                oxElement.parentElement.style.color = "#f59e0b";
            } else {
                // Concerning - red
                oxElement.parentElement.style.color = "#ef4444";
            }
        } else {
            // No data - default gray
            oxElement.parentElement.style.color = "#6b7280";
        }

        if (v.oxta && v.oxta !== 255) {
            document.getElementById("oxta").innerText = v.oxta;
        } else {
            document.getElementById("oxta").innerText = "--";
        }

        // --- 3. QUALITY / STATUS BADGE ---
        // Display signal quality/placement status with color coding
        // Special handling for charging state and frozen data detection
        const qualEl = document.getElementById("hr-quality");
        const bp = v.bp;
        const isCharging = (v.chg === 1);
        let showStaleWarning = false;

        // If BP is 6 (Degraded) AND HR has been identical for >10 sec (5 updates)
        if (bp === 6 && window.hrStaleCount > 5 && !isCharging) {
            showStaleWarning = true;
        }

        // RESET DISPLAY
        qualEl.style.display = "inline-block";

        if (isCharging) {
            qualEl.innerText = "DOCKED";
            qualEl.style.backgroundColor = "#ede9fe"; // Light Purple
            qualEl.style.color = "#5b21b6";
        } else if (showStaleWarning) {
            qualEl.innerText = "FROZEN"; 
            qualEl.style.backgroundColor = "#fee2e2"; 
            qualEl.style.color = "#991b1b";
        } else if (bp === 10) {
            qualEl.innerText = "LIVE";
            qualEl.style.backgroundColor = "#d1fae5";
            qualEl.style.color = "#065f46";
        } else if (bp === 1) {
            qualEl.innerText = "CALIBRATING";
            qualEl.style.backgroundColor = "#fef3c7";
            qualEl.style.color = "#92400e";
        } else if (bp === 6) {
            qualEl.innerText = "WEAK";
            qualEl.style.backgroundColor = "#fee2e2";
            qualEl.style.color = "#991b1b";
        } else if (bp === 7) {
            qualEl.innerText = "IDLE";
            qualEl.style.backgroundColor = "#ede9fe";
            qualEl.style.color = "#5b21b6";
        } else {
            qualEl.style.display = "none";
        }


        // --- 4. LAG DISPLAY ---
        // Show data freshness lag and color code based on severity
        const lagEl = document.getElementById("lag");
        lagEl.innerText = meta.lag_seconds ?? "--";
        if (meta.lag_seconds > 60) {
            lagEl.style.color = "#ef4444"; 
        } else {
            lagEl.style.color = "#10b981"; 
        }

        // --- 5. WIGGLE SLIDER ---
        // Visual representation of baby movement intensity (0-100 scale)
        const movementScore = v.mvb ?? 0;
        const clampScore = Math.max(0, Math.min(100, movementScore));
        document.getElementById("wiggle-thumb").style.left = clampScore + "%";
        document.getElementById("mv").innerText = v.mv ?? "--";

        // --- 6. TECH CARDS ---
        // Update technical diagnostic cards with color-coded status indicators
        
        // Monitoring Status (onm) - Shows if sock is actively monitoring
        const onmEl = document.getElementById("onm");
        if (v.onm === 3) {
            onmEl.innerText = "ACTIVE (3)";
            onmEl.style.color = "#10b981";
        } else if (v.onm === 0) {
            onmEl.innerText = "PAUSED (0)";
            onmEl.style.color = "#9ca3af";
        } else {
            onmEl.innerText = "Status " + v.onm;
            onmEl.style.color = "#374151";
        }

        // Monitor Ready Status (mrs) - Indicates monitoring subsystem initialized
        const mrsEl = document.getElementById("mrs");
        if (v.mrs === 1) {
            mrsEl.innerText = "READY";
            mrsEl.style.color = "#10b981";
        } else {
            mrsEl.innerText = "NOT READY";
            mrsEl.style.color = "#f59e0b";
        }

        // Band Placement (bp) - Shows sock sensor signal quality state
        // REVISED LOGIC WITH CHARGING CHECK
        const bpEl = document.getElementById("bp");
        const bpVal = v.bp;
        let bpText = "Unknown";
        let bpColor = "#374151";

        if (isCharging) {
            bpText = "Docked/Charging";
            bpColor = "#8b5cf6";
        } else {
            if (bpVal === 1) {
                bpText = "Calibrating (1)";
                bpColor = "#f59e0b";
            } else if (bpVal === 6) {
                bpText = "Degraded (6)";
                bpColor = "#ef4444";
            } else if (bpVal === 7) {
                bpText = "Idle/Docked (7)";
                bpColor = "#8b5cf6";
            } else if (bpVal === 8) {
                bpText = "Docked (8)";
                bpColor = "#8b5cf6";
            } else if (bpVal === 10) {
                bpText = "Monitoring (10)";
                bpColor = "#10b981";
            } else {
                bpText = `Code ${bpVal}`;
            }
        }
        
        bpEl.innerText = bpText;
        bpEl.style.color = bpColor;

        // Base Station (bso) - Shows if base station is powered on
        const bsoEl = document.getElementById("bso");
        if (v.bso === 1) {
            bsoEl.innerText = "POWER ON";
            bsoEl.style.color = "#10b981";
        } else {
            bsoEl.innerText = "OFF";
            bsoEl.style.color = "#ef4444";
        }

        // Update remaining technical diagnostic values
        document.getElementById("mvb").innerText = v.mvb != null ? v.mvb + "%" : "-";
        const ssLabels = {0: "Inactive", 1: "Awake", 8: "Light Sleep", 15: "Deep Sleep"};
        const ssColors = {0: "#9ca3af", 1: "#f59e0b", 8: "#3b82f6", 15: "#10b981"};
        const ssEl = document.getElementById("ss");
        ssEl.innerText = v.ss != null ? (ssLabels[v.ss] || "State " + v.ss) : "-";
        ssEl.style.color = ssColors[v.ss] || "#374151";
        document.getElementById("rsi").innerText = v.rsi ? v.rsi + "%" : "-";
        
        const scEl = document.getElementById("sc");
        scEl.innerText = v.sc === 2 ? "Connected" : "Code " + v.sc;
        
        const chgEl = document.getElementById("chg");
        chgEl.innerText = v.chg === 1 ? "⚡ Yes" : "No";
        chgEl.style.color = v.chg === 1 ? "#d97706" : "#374151";
        
        document.getElementById("bat").innerText = (v.bat ?? "--") + "%";
        
        // Skin Temperature
        const stEl = document.getElementById("st");
        if (v.st && v.st > 0) {
            stEl.innerText = v.st + "°";
            stEl.style.color = "#374151";
        } else {
            stEl.innerText = "--";
            stEl.style.color = "#9ca3af";
        }

        // Sock Off indicator
        const sockOffEl = document.getElementById("sock-off");
        if (alerts.sock_off) {
            sockOffEl.innerText = "YES";
            sockOffEl.style.color = "#ef4444";
        } else {
            sockOffEl.innerText = "No";
            sockOffEl.style.color = "#10b981";
        }

        // --- CHARGE STATE CONTEXT ---
        // When sock is charging, add context to vitals
        if (isCharging) {
            const hrEl2 = document.getElementById("hr");
            if (hrEl2.innerText !== "--") {
                // Vitals may not be reliable while charging
            }
        }

        // --- 7. DEVICE INFO & ALERT HISTORY ---
        const info = payload.device_info || {};
        const alertHistory = payload.alert_history || [];

        // --- Alert History Summary (on main page) ---
        const sumTotal = document.getElementById("sum-total");
        const sumTypes = document.getElementById("sum-types");
        const sumHr = document.getElementById("sum-hr");
        const sumOx = document.getElementById("sum-ox");
        if (alertHistory.length > 0) {
            sumTotal.innerText = alertHistory.length;
            sumTotal.style.color = alertHistory.length > 50 ? "#ef4444" : "#f59e0b";
            // Count types
            const tc = {};
            alertHistory.forEach(r => { tc[r.type_name] = (tc[r.type_name]||0) + 1; });
            const typeStr = Object.entries(tc).map(([k,v]) => v + " " + k).join(", ");
            sumTypes.innerText = typeStr.length <= 35 ? typeStr : Object.keys(tc).length + " types";
            // HR range
            const aHrs = alertHistory.filter(r => r.hr >= 40 && r.hr <= 250).map(r => r.hr);
            sumHr.innerText = aHrs.length ? Math.min(...aHrs) + "-" + Math.max(...aHrs) + " BPM" : "--";
            // SpO2 range
            const aOxs = alertHistory.filter(r => r.ox >= 50 && r.ox <= 100).map(r => r.ox);
            if (aOxs.length) {
                const minOx = Math.min(...aOxs);
                sumOx.innerText = minOx + "-" + Math.max(...aOxs) + "%";
                sumOx.style.color = minOx < 90 ? "#ef4444" : minOx < 95 ? "#f59e0b" : "#3b82f6";
            } else {
                sumOx.innerText = "--";
            }
        } else {
            sumTotal.innerText = "0"; sumTotal.style.color = "#10b981";
            sumTypes.innerText = "None"; sumTypes.style.color = "#9ca3af";
            sumHr.innerText = "--"; sumOx.innerText = "--";
        }

        // Device & Firmware info cards
        const setInfo = (id, val, color) => {
            const el = document.getElementById(id);
            if (el) {
                el.innerText = val ?? "--";
                if (color) el.style.color = color;
            }
        };
        setInfo("info-base-fw", info.base_fw);
        setInfo("info-sock-fw", info.sock_fw);
        setInfo("info-base-hw", info.base_hw);
        setInfo("info-flash", info.flash_version);
        setInfo("info-sock-mac", info.sock_mac);
        setInfo("info-base-mac", info.base_mac);
        setInfo("info-fw-update", info.fw_update, info.fw_update === "IDLE" ? "#10b981" : "#f59e0b");
        setInfo("info-battery-raw", info.battery_raw);

        // Monitoring Settings
        if (info.onm_setting === 3) {
            setInfo("info-onm-setting", "Active (3)", "#10b981");
        } else if (info.onm_setting === 0) {
            setInfo("info-onm-setting", "Paused (0)", "#9ca3af");
        } else {
            setInfo("info-onm-setting", info.onm_setting != null ? "Mode " + info.onm_setting : "--");
        }
        setInfo("info-ox-baseline", info.ox_baseline);
        setInfo("info-hr-baseline", info.hr_baseline);
        setInfo("info-sleep-state", info.sleep_state);

        // Alert History table
        const alertCountEl = document.getElementById("alert-history-count");
        alertCountEl.innerText = alertHistory.length + " events";

        // Only rebuild table if count changed
        if (window._lastAlertCount !== alertHistory.length) {
            window._lastAlertCount = alertHistory.length;
            const atbody = document.getElementById("alert-history-body");
            atbody.innerHTML = "";
            alertHistory.forEach((rec, i) => {
                const tr = document.createElement("tr");

                // Row number
                const tdNum = document.createElement("td");
                tdNum.innerText = i + 1;
                tdNum.style.color = "#6b7280";

                // HR with color
                const tdHr = document.createElement("td");
                tdHr.style.fontWeight = "600";
                if (rec.hr > 0) {
                    tdHr.innerText = rec.hr + " BPM";
                    if (rec.hr >= 100 && rec.hr <= 160) tdHr.style.color = "#10b981";
                    else if (rec.hr > 160 || rec.hr < 90) tdHr.style.color = "#ef4444";
                    else tdHr.style.color = "#f59e0b";
                } else {
                    tdHr.innerText = "-";
                    tdHr.style.color = "#9ca3af";
                }

                // SpO2 with color
                const tdOx = document.createElement("td");
                tdOx.style.fontWeight = "600";
                if (rec.ox > 0) {
                    tdOx.innerText = rec.ox + "%";
                    if (rec.ox >= 95) tdOx.style.color = "#3b82f6";
                    else if (rec.ox >= 90) tdOx.style.color = "#f59e0b";
                    else tdOx.style.color = "#ef4444";
                } else {
                    tdOx.innerText = "-";
                    tdOx.style.color = "#9ca3af";
                }

                // Duration
                const tdDur = document.createElement("td");
                tdDur.innerText = rec.duration;

                // Type
                const tdType = document.createElement("td");
                tdType.innerText = rec.type_name;
                if (rec.type_name.includes("Critical")) {
                    tdType.style.color = "#ef4444";
                    tdType.style.fontWeight = "600";
                }

                tr.appendChild(tdNum);
                tr.appendChild(tdHr);
                tr.appendChild(tdOx);
                tr.appendChild(tdDur);
                tr.appendChild(tdType);
                atbody.appendChild(tr);
            });
        }
    };
    
    // Logout button handler
    document.getElementById('logoutBtn').addEventListener('click', async () => {
        try {
            const response = await fetch('/logout', {
                method: 'POST'
            });
            
            if (response.ok) {
                // Close WebSocket connection
                ws.close();
                // Redirect to login page
                window.location.href = '/';
            }
        } catch (error) {
            console.error('Logout error:', error);
            // Force redirect even on error
            window.location.href = '/';
        }
    });
    
    // Quit App button handler
    document.getElementById('quitBtn').addEventListener('click', async () => {
        if (confirm('Are you sure you want to quit the application?')) {
            try {
                const response = await fetch('/shutdown', {
                    method: 'POST'
                });
                
                if (response.ok) {
                    document.body.innerHTML = '<div style="display:flex;justify-content:center;align-items:center;height:100vh;font-size:24px;color:#6d28d9;">Application closed. You can close this window.</div>';
                }
            } catch (error) {
                // Expected - server shuts down immediately
                document.body.innerHTML = '<div style="display:flex;justify-content:center;align-items:center;height:100vh;font-size:24px;color:#6d28d9;">Application closed. You can close this window.</div>';
            }
        }
    });
</script>
</body>
</html>
"""
