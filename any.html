<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
  <title>Echelon Analytics Pulse</title>
  
  <!-- Telegram WebApp SDK -->
  <script src="https://telegram.org/js/telegram-web-app.js"></script>

  <!-- Tailwind CSS -->
  <script src="https://cdn.tailwindcss.com"></script>

  <!-- Chart.js for High-Fidelity Visualizations -->
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>

  <!-- Google Fonts: Plus Jakarta Sans -->
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">

  <!-- Lucide Icons -->
  <script src="https://unpkg.com/lucide@latest"></script>

  <style>
    :root {
      --bg-base-warm: #FAF6F0;
      --bg-blush-tint: #FDF1EA;
      --bg-yellow-tint: #FEF9EB;
      --blue-heavy: #0B2545;
      --blue-deep: #133E87;
      --blue-accent: #1D4ED8;
      --blue-light: #EBF3FA;
      --border-liquid: rgba(230, 214, 198, 0.65);
    }

    * {
      font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
      -webkit-tap-highlight-color: transparent;
      box-sizing: border-box;
    }

    body {
      background: radial-gradient(circle at 10% 10%, #FFFDF9 0%, #FAF4EB 45%, #FBF0E9 100%);
      min-height: 100vh;
      color: #0B2545;
      overflow-x: hidden;
    }

    /* Liquid Card Glassmorphism */
    .liquid-card {
      background: rgba(255, 255, 255, 0.72);
      backdrop-filter: blur(20px);
      -webkit-backdrop-filter: blur(20px);
      border: 1px solid rgba(240, 224, 210, 0.75);
      border-radius: 1.25rem;
      box-shadow: 0 10px 30px -8px rgba(180, 140, 110, 0.12),
                  0 4px 10px -2px rgba(11, 37, 69, 0.03);
      transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
    }

    .liquid-card:active {
      transform: scale(0.99);
    }

    .liquid-card-glow {
      background: linear-gradient(135deg, rgba(255, 255, 255, 0.9) 0%, rgba(254, 248, 240, 0.75) 100%);
      border: 1px solid rgba(246, 210, 185, 0.85);
      box-shadow: 0 14px 35px -8px rgba(220, 150, 110, 0.18);
    }

    /* Subtle Animated Pulse Shimmer */
    .shimmer-badge {
      background: linear-gradient(90deg, rgba(29, 78, 216, 0.08) 0%, rgba(29, 78, 216, 0.18) 50%, rgba(29, 78, 216, 0.08) 100%);
      background-size: 200% 100%;
      animation: shimmer 3s infinite;
    }

    @keyframes shimmer {
      0% { background-position: 200% 0; }
      100% { background-position: -200% 0; }
    }

    /* Floating Pill Navigation */
    .liquid-nav {
      background: rgba(255, 255, 255, 0.85);
      backdrop-filter: blur(24px);
      -webkit-backdrop-filter: blur(24px);
      border: 1px solid rgba(235, 215, 200, 0.8);
      box-shadow: 0 12px 40px -10px rgba(11, 37, 69, 0.12);
    }

    /* Custom Scrollbar hide */
    .no-scrollbar::-webkit-scrollbar {
      display: none;
    }
    .no-scrollbar {
      -ms-overflow-style: none;
      scrollbar-width: none;
    }


    /* Dashboard detail layers */
    .detail-card {
      background: rgba(255,255,255,.78);
      border: 1px solid rgba(230,214,198,.65);
      border-radius: 1rem;
      box-shadow: 0 8px 24px -12px rgba(11,37,69,.12);
    }
    .metric-mini {
      background: rgba(248,250,252,.78);
      border: 1px solid rgba(226,232,240,.85);
      border-radius: .9rem;
    }
    .transaction-scroll {
      max-height: 58vh;
      overflow-y: auto;
      overscroll-behavior: contain;
      -webkit-overflow-scrolling: touch;
    }
    .transaction-scroll::-webkit-scrollbar { width: 4px; }
    .transaction-scroll::-webkit-scrollbar-thumb {
      background: rgba(148,163,184,.35);
      border-radius: 999px;
    }
    .status-dot { width: .42rem; height: .42rem; border-radius: 999px; display:inline-block; }
    .setting-value { word-break: break-word; }

  </style>
</head>
<body class="pb-28 antialiased selection:bg-blue-100 selection:text-blue-900">

  <!-- Main Container -->
  <div id="appContainer" class="max-w-md mx-auto px-4 pt-4 transition-opacity duration-300">
    
    <!-- Top Header Bar -->
    <header class="flex items-center justify-between py-2 mb-3">
      <div class="flex items-center space-x-3">
        <div class="w-11 h-11 rounded-2xl bg-gradient-to-tr from-blue-900 via-blue-800 to-indigo-600 flex items-center justify-center text-white shadow-md shadow-blue-900/20">
          <i data-lucide="activity" class="w-5 h-5"></i>
        </div>
        <div>
          <div class="flex items-center space-x-1.5">
            <h1 class="text-lg font-bold tracking-tight text-[#0B2545]" id="headerUserName">Analytics</h1>
            <span id="superAdminBadge" class="hidden px-2 py-0.5 text-[10px] font-bold rounded-full bg-amber-100 text-amber-900 border border-amber-300/80 uppercase tracking-wider">Super Admin</span>
          </div>
          <p class="text-xs text-slate-500 flex items-center gap-1.5 font-medium">
            <span class="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
            <span id="serverStatusText">System Live • 0ms</span>
          </p>
        </div>
      </div>

      <button id="refreshBtn" onclick="triggerRefresh()" class="w-10 h-10 rounded-2xl liquid-card flex items-center justify-center text-[#133E87] hover:text-blue-600 transition-transform active:rotate-180">
        <i data-lucide="rotate-cw" class="w-4 h-4"></i>
      </button>
    </header>

    <!-- Controls Section: Bot Dropdown & Time Filter Chips -->
    <div class="space-y-2.5 mb-4">
      
      <!-- Bot Selector -->
      <div class="relative">
        <div class="liquid-card px-3.5 py-2.5 flex items-center justify-between cursor-pointer" onclick="toggleBotDropdown()">
          <div class="flex items-center space-x-2.5 min-w-0">
            <div class="w-7 h-7 rounded-xl bg-blue-50 text-blue-800 flex items-center justify-center flex-shrink-0">
              <i data-lucide="bot" class="w-4 h-4"></i>
            </div>
            <div class="truncate">
              <p class="text-[10px] uppercase font-bold tracking-wider text-slate-400">Monitoring Target</p>
              <p class="text-sm font-bold text-[#0B2545] truncate" id="selectedBotLabel">Loading bots...</p>
            </div>
          </div>
          <i data-lucide="chevron-down" id="botChevron" class="w-4 h-4 text-slate-400 transition-transform duration-200"></i>
        </div>

        <!-- Bot Dropdown Menu -->
        <div id="botDropdownMenu" class="hidden absolute top-full left-0 right-0 mt-1.5 liquid-card p-2 z-50 shadow-2xl max-h-56 overflow-y-auto no-scrollbar border border-amber-200/60">
          <div id="botOptionsList" class="space-y-1">
            <!-- Dynamic bot items injected here -->
          </div>
        </div>
      </div>

      <!-- Time Filter Chips (1h, 6h, 24h, 7d) -->
      <div class="flex items-center p-1 rounded-2xl liquid-card space-x-1 text-xs font-semibold text-slate-600">
        <button class="time-filter-btn flex-1 py-1.5 rounded-xl transition-all text-center" data-filter="1h" onclick="setTimeFilter('1h')">1 Hour</button>
        <button class="time-filter-btn flex-1 py-1.5 rounded-xl transition-all text-center" data-filter="6h" onclick="setTimeFilter('6h')">6 Hours</button>
        <button class="time-filter-btn flex-1 py-1.5 rounded-xl transition-all text-center active-filter bg-[#133E87] text-white shadow-sm" data-filter="24h" onclick="setTimeFilter('24h')">24 Hours</button>
        <button class="time-filter-btn flex-1 py-1.5 rounded-xl transition-all text-center" data-filter="7d" onclick="setTimeFilter('7d')">7 Days</button>
      </div>
    </div>

    <!-- TAB 1: EXECUTIVE OVERVIEW -->
    <div id="tabOverview" class="tab-content space-y-4">

      <!-- Hero KPI Banner (Server Load & Live Pulse) -->
      <div class="liquid-card liquid-card-glow p-4 relative overflow-hidden">
        <div class="absolute -right-6 -top-6 w-28 h-28 bg-gradient-to-br from-amber-300/25 to-pink-300/20 rounded-full blur-2xl pointer-events-none"></div>
        <div class="flex items-center justify-between mb-3">
          <span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-bold bg-blue-100/70 text-[#133E87]">
            <i data-lucide="zap" class="w-3.5 h-3.5"></i> Live Load Pulse
          </span>
          <span class="text-xs font-bold text-slate-500" id="liveTimestamp">Just now</span>
        </div>
        
        <div class="grid grid-cols-2 gap-3">
          <div>
            <p class="text-xs font-semibold text-slate-500">Live Active Load</p>
            <div class="flex items-baseline space-x-1.5">
              <span class="text-3xl font-extrabold text-[#0B2545]" id="metricLiveConcurrency">0</span>
              <span class="text-xs text-slate-400 font-medium">concurrent</span>
            </div>
            <p class="text-[11px] text-emerald-600 font-semibold mt-0.5 flex items-center gap-1">
              <i data-lucide="shield-check" class="w-3 h-3"></i> Server Healthy
            </p>
          </div>
          <div class="border-l border-amber-200/60 pl-3">
            <p class="text-xs font-semibold text-slate-500">Avg Delivery Time</p>
            <div class="flex items-baseline space-x-1.5">
              <span class="text-3xl font-extrabold text-[#133E87]" id="metricAvgDelivery">0</span>
              <span class="text-xs text-slate-400 font-medium">ms</span>
            </div>
            <p class="text-[11px] text-slate-500 font-medium mt-0.5" id="metricP95Delivery">P95: 0ms</p>
          </div>
        </div>
      </div>

      <!-- Core Activity Matrix (Clicks, Views, Users) -->
      <div class="grid grid-cols-2 gap-3">
        <!-- Total Clicks -->
        <div class="liquid-card p-3.5">
          <div class="flex items-center justify-between text-slate-400 mb-1.5">
            <span class="text-xs font-bold uppercase tracking-wider text-slate-500">Clicks Today</span>
            <div class="w-7 h-7 rounded-lg bg-orange-50 text-orange-600 flex items-center justify-center">
              <i data-lucide="mouse-pointer-click" class="w-3.5 h-3.5"></i>
            </div>
          </div>
          <p class="text-2xl font-extrabold text-[#0B2545]" id="metricTodayClicks">0</p>
          <p class="text-[11px] text-slate-400 font-medium mt-1">Lifetime: <span class="font-bold text-slate-600" id="metricTotalClicks">0</span></p>
        </div>

        <!-- File Views Today -->
        <div class="liquid-card p-3.5">
          <div class="flex items-center justify-between text-slate-400 mb-1.5">
            <span class="text-xs font-bold uppercase tracking-wider text-slate-500">Files / Content Views Today</span>
            <div class="w-7 h-7 rounded-lg bg-blue-50 text-blue-600 flex items-center justify-center">
              <i data-lucide="eye" class="w-3.5 h-3.5"></i>
            </div>
          </div>
          <p class="text-2xl font-extrabold text-[#0B2545]" id="metricTodayViews">0</p>
          <p class="text-[11px] text-slate-400 font-medium mt-1">Lifetime: <span class="font-bold text-slate-600" id="metricTotalViews">0</span> • Tracked</p>
        </div>

        <!-- Active Users Today -->
        <div class="liquid-card p-3.5">
          <div class="flex items-center justify-between text-slate-400 mb-1.5">
            <span class="text-xs font-bold uppercase tracking-wider text-slate-500">Active Users</span>
            <div class="w-7 h-7 rounded-lg bg-emerald-50 text-emerald-600 flex items-center justify-center">
              <i data-lucide="user-check" class="w-3.5 h-3.5"></i>
            </div>
          </div>
          <p class="text-2xl font-extrabold text-[#0B2545]" id="metricActiveUsers">0</p>
          <p class="text-[11px] text-slate-400 font-medium mt-1">Unique active today</p>
        </div>

        <!-- Total Users Base -->
        <div class="liquid-card p-3.5">
          <div class="flex items-center justify-between text-slate-400 mb-1.5">
            <span class="text-xs font-bold uppercase tracking-wider text-slate-500">Total Users</span>
            <div class="w-7 h-7 rounded-lg bg-purple-50 text-purple-600 flex items-center justify-center">
              <i data-lucide="users" class="w-3.5 h-3.5"></i>
            </div>
          </div>
          <p class="text-2xl font-extrabold text-[#0B2545]" id="metricTotalUsers">0</p>
          <p class="text-[11px] text-slate-400 font-medium mt-1">Registered audience</p>
        </div>
      </div>

      <!-- Quick Revenue Summary Card -->
      <div class="liquid-card p-4">
        <div class="flex items-center justify-between mb-3">
          <div class="flex items-center space-x-2">
            <div class="w-8 h-8 rounded-xl bg-amber-50 text-amber-700 flex items-center justify-center">
              <i data-lucide="wallet" class="w-4 h-4"></i>
            </div>
            <div>
              <p class="text-xs font-bold text-slate-400 uppercase tracking-wider">Revenue Snapshot</p>
              <h3 class="text-sm font-bold text-[#0B2545]">Monetization Pulse</h3>
            </div>
          </div>
          <button onclick="switchTab('revenue')" class="text-xs font-bold text-blue-700 hover:text-blue-900 flex items-center gap-1">
            Details <i data-lucide="arrow-right" class="w-3.5 h-3.5"></i>
          </button>
        </div>

        <div class="grid grid-cols-2 gap-3 pt-2 border-t border-slate-100">
          <div>
            <p class="text-[11px] font-semibold text-slate-400">Today's Earnings</p>
            <p class="text-xl font-extrabold text-emerald-700" id="metricTodayRev">₹0.00</p>
          </div>
          <div class="border-l border-slate-100 pl-3">
            <p class="text-[11px] font-semibold text-slate-400">Total Lifetime</p>
            <p class="text-xl font-extrabold text-[#0B2545]" id="metricTotalRev">₹0.00</p>
          </div>
        </div>
      </div>

      <!-- Quick Mini Chart: Traffic Overview -->
      <div class="liquid-card p-4">
        <div class="flex items-center justify-between mb-2">
          <span class="text-xs font-bold text-slate-600 uppercase tracking-wider flex items-center gap-1.5">
            <i data-lucide="trending-up" class="w-3.5 h-3.5 text-blue-700"></i> Traffic Rate (RPM)
          </span>
          <span class="text-xs font-semibold text-slate-400" id="rpmStatusBadge">5-Min Batches</span>
        </div>
        <div class="h-44 w-full">
          <canvas id="quickTrafficChart"></canvas>
        </div>
      </div>
    </div>

    <!-- TAB 2: LATENCY & SERVER HEALTH -->
    <div id="tabLatency" class="tab-content hidden space-y-4">
      
      <!-- Latency Metric Cards -->
      <div class="grid grid-cols-3 gap-2.5">
        <div class="liquid-card p-3 text-center">
          <p class="text-[10px] uppercase font-bold text-slate-400">Average</p>
          <p class="text-lg font-extrabold text-[#133E87] mt-0.5" id="latCardAvg">0ms</p>
        </div>
        <div class="liquid-card p-3 text-center">
          <p class="text-[10px] uppercase font-bold text-slate-400">95th %ile</p>
          <p class="text-lg font-extrabold text-indigo-700 mt-0.5" id="latCardP95">0ms</p>
        </div>
        <div class="liquid-card p-3 text-center">
          <p class="text-[10px] uppercase font-bold text-slate-400">Peak Spike</p>
          <p class="text-lg font-extrabold text-rose-600 mt-0.5" id="latCardMax">0ms</p>
        </div>
      </div>

      <!-- Detailed Latency Breakdown Chart -->
      <div class="liquid-card p-4">
        <div class="flex items-center justify-between mb-2">
          <div>
            <h3 class="text-sm font-bold text-[#0B2545]">Delivery Latency Dynamics</h3>
            <p class="text-xs text-slate-400">Time from user click to media delivered</p>
          </div>
          <span class="px-2 py-0.5 text-[10px] font-bold bg-blue-50 text-blue-800 rounded-full border border-blue-200">ms / 5m</span>
        </div>
        <div class="h-60 w-full mt-2">
          <canvas id="detailedLatencyChart"></canvas>
        </div>
      </div>

      <!-- Server Concurrency Load Chart -->
      <div class="liquid-card p-4">
        <div class="flex items-center justify-between mb-2">
          <div>
            <h3 class="text-sm font-bold text-[#0B2545]">Simultaneous Processing Load</h3>
            <p class="text-xs text-slate-400">Peak concurrent requests handling capacity</p>
          </div>
          <span class="px-2 py-0.5 text-[10px] font-bold bg-amber-50 text-amber-800 rounded-full border border-amber-200">Active</span>
        </div>
        <div class="h-48 w-full mt-2">
          <canvas id="concurrencyChart"></canvas>
        </div>
      </div>

      <!-- Performance Insights Banner -->
      <div class="liquid-card p-3.5 flex items-start space-x-3 bg-gradient-to-r from-blue-50/50 to-amber-50/50">
        <div class="w-8 h-8 rounded-xl bg-blue-100 text-blue-800 flex items-center justify-center flex-shrink-0 mt-0.5">
          <i data-lucide="gauge" class="w-4 h-4"></i>
        </div>
        <div class="text-xs">
          <p class="font-bold text-[#0B2545]">High-Speed In-Memory Pipeline</p>
          <p class="text-slate-500 mt-0.5 leading-relaxed">Aggregated smoothly every 5 minutes directly in server RAM, zero database latency locks.</p>
        </div>
      </div>
    </div>

    <!-- TAB 3: AUDIENCE & ACTIVITY -->
    <div id="tabAudience" class="tab-content hidden space-y-4">
      
      <!-- Clicks & Views Conversion Bar -->
      <div class="liquid-card p-4">
        <h3 class="text-sm font-bold text-[#0B2545] mb-1">Conversion Efficiency</h3>
        <p class="text-xs text-slate-400 mb-3">Ratio of link clicks to tracked content views / deliveries</p>
        
        <div class="space-y-3">
          <div>
            <div class="flex justify-between text-xs font-semibold mb-1">
              <span class="text-slate-600">Links Clicked (Today)</span>
              <span class="text-[#0B2545]" id="convClicksVal">0</span>
            </div>
            <div class="w-full h-2.5 bg-slate-100 rounded-full overflow-hidden">
              <div id="convClicksBar" class="h-full bg-gradient-to-r from-orange-400 to-amber-500 rounded-full" style="width: 100%"></div>
            </div>
          </div>

          <div>
            <div class="flex justify-between text-xs font-semibold mb-1">
              <span class="text-slate-600">Tracked Content Views / Deliveries (Today)</span>
              <span class="text-[#133E87]" id="convViewsVal">0</span>
            </div>
            <div class="w-full h-2.5 bg-slate-100 rounded-full overflow-hidden">
              <div id="convViewsBar" class="h-full bg-gradient-to-r from-blue-600 to-indigo-600 rounded-full" style="width: 0%"></div>
            </div>
          </div>
        </div>

        <div class="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between text-xs">
          <span class="text-slate-500 font-medium">Delivery Conversion Rate:</span>
          <span class="font-extrabold text-emerald-600 text-sm" id="convRatePercent">0%</span>
        </div>
      </div>

      <!-- Activity Timeline Chart -->
      <div class="liquid-card p-4">
        <div class="flex items-center justify-between mb-2">
          <div>
            <h3 class="text-sm font-bold text-[#0B2545]">Requests Dispersion</h3>
            <p class="text-xs text-slate-400">Total requests processed over time</p>
          </div>
        </div>
        <div class="h-56 w-full mt-2">
          <canvas id="audienceRequestsChart"></canvas>
        </div>
      </div>

      <!-- Audience Details Breakdown -->
      <div class="grid grid-cols-2 gap-3">
        <div class="liquid-card p-3.5 text-center">
          <p class="text-xs font-semibold text-slate-500">Premium Members</p>
          <p class="text-2xl font-extrabold text-amber-600 mt-1" id="metricTotalPremium">0</p>
          <p class="text-[10px] text-slate-400 mt-0.5">Ad-Free Subscriptions</p>
        </div>
        <div class="liquid-card p-3.5 text-center">
          <p class="text-xs font-semibold text-slate-500">Shared Links</p>
          <p class="text-2xl font-extrabold text-[#133E87] mt-1" id="metricTotalLinks">0</p>
          <p class="text-[10px] text-slate-400 mt-0.5">Files & Albums Active</p>
        </div>
      </div>
    </div>

    <!-- TAB 4: REVENUE & MONETIZATION -->
    <div id="tabRevenue" class="tab-content hidden space-y-4">
      
      <!-- Big Earnings Highlight -->
      <div class="liquid-card liquid-card-glow p-5 text-center relative overflow-hidden">
        <span class="inline-block px-3 py-1 rounded-full text-xs font-bold bg-emerald-100 text-emerald-800 border border-emerald-300/80 mb-2">
          Lifetime Net Revenue
        </span>
        <h2 class="text-4xl font-extrabold text-[#0B2545] tracking-tight" id="revHeroTotal">₹0.00</h2>
        <p class="text-xs text-slate-500 mt-1">Across Subscriptions & Paid Messages</p>

        <div class="grid grid-cols-2 gap-3 mt-4 pt-4 border-t border-amber-200/60 text-left">
          <div>
            <p class="text-[11px] font-bold text-slate-400 uppercase">Today Earned</p>
            <p class="text-lg font-bold text-emerald-700 mt-0.5" id="revHeroToday">₹0.00</p>
          </div>
          <div class="border-l border-amber-200/60 pl-3">
            <p class="text-[11px] font-bold text-slate-400 uppercase">Platform Tier</p>
            <p class="text-lg font-bold text-[#133E87] mt-0.5">8% Comm. Cap</p>
          </div>
        </div>
      </div>

      <!-- Monetization Channels Overview -->
      <div class="liquid-card p-4 space-y-3">
        <h3 class="text-sm font-bold text-[#0B2545]">Active Payment Gateways</h3>
        
        <div class="flex items-center justify-between p-2.5 rounded-xl bg-slate-50/80 border border-slate-100">
          <div class="flex items-center space-x-2.5 min-w-0">
            <div class="w-8 h-8 rounded-lg bg-blue-100 text-blue-800 flex items-center justify-center font-bold text-xs flex-shrink-0">UPI</div>
            <div class="min-w-0">
              <p class="text-xs font-bold text-[#0B2545]">Instant UPI QR & Gateway</p>
              <p class="text-[10px] text-slate-400 truncate" id="gatewayUpiText">UPI status loading…</p>
            </div>
          </div>
          <span id="gatewayUpiBadge" class="px-2 py-0.5 text-[10px] font-bold bg-slate-100 text-slate-600 rounded-full">—</span>
        </div>

        <div class="flex items-center justify-between p-2.5 rounded-xl bg-slate-50/80 border border-slate-100">
          <div class="flex items-center space-x-2.5 min-w-0">
            <div class="w-8 h-8 rounded-lg bg-amber-100 text-amber-800 flex items-center justify-center font-bold text-xs flex-shrink-0">⭐</div>
            <div class="min-w-0">
              <p class="text-xs font-bold text-[#0B2545]">Telegram Stars (XTR)</p>
              <p class="text-[10px] text-slate-400 truncate" id="gatewayStarsText">Stars status loading…</p>
            </div>
          </div>
          <span id="gatewayStarsBadge" class="px-2 py-0.5 text-[10px] font-bold bg-slate-100 text-slate-600 rounded-full">—</span>
        </div>

        <div class="flex items-center justify-between p-2.5 rounded-xl bg-slate-50/80 border border-slate-100">
          <div class="flex items-center space-x-2.5 min-w-0">
            <div class="w-8 h-8 rounded-lg bg-emerald-100 text-emerald-800 flex items-center justify-center font-bold text-xs flex-shrink-0">CF</div>
            <div class="min-w-0">
              <p class="text-xs font-bold text-[#0B2545]">Cashfree</p>
              <p class="text-[10px] text-slate-400 truncate">Gateway configuration</p>
            </div>
          </div>
          <span id="gatewayCashfreeBadge" class="px-2 py-0.5 text-[10px] font-bold bg-slate-100 text-slate-600 rounded-full">—</span>
        </div>
      </div>

      <!-- Billing / pending bills -->
      <div class="liquid-card p-4">
        <div class="flex items-center justify-between mb-3">
          <div>
            <p class="text-[10px] uppercase font-bold tracking-wider text-slate-400">Billing</p>
            <h3 class="text-sm font-bold text-[#0B2545]">Commission & Pending Bills</h3>
          </div>
          <span id="billingLockBadge" class="px-2 py-0.5 text-[10px] font-bold bg-slate-100 text-slate-600 rounded-full">—</span>
        </div>
        <div id="billingGrid" class="grid grid-cols-2 gap-2.5"></div>
        <p id="billingNote" class="text-[10px] text-slate-400 mt-3 hidden"></p>
      </div>

      <!-- Live transactions with infinite scroll -->
      <div class="liquid-card p-4">
        <div class="flex items-center justify-between mb-3">
          <div class="min-w-0">
            <p class="text-[10px] uppercase font-bold tracking-wider text-slate-400">Orders</p>
            <h3 class="text-sm font-bold text-[#0B2545]">Latest Transactions</h3>
            <p class="text-[10px] text-slate-400" id="transactionSummary">0 loaded</p>
          </div>
          <span class="px-2 py-0.5 text-[10px] font-bold bg-emerald-100 text-emerald-800 rounded-full flex items-center gap-1">
            <span class="status-dot bg-emerald-500"></span> Live
          </span>
        </div>
        <div id="transactionScroller" class="transaction-scroll pr-1 space-y-2">
          <div id="transactionList" class="space-y-2"></div>
          <div id="transactionLoader" class="hidden py-3 text-center text-[11px] text-slate-400">Loading more…</div>
          <div id="transactionEnd" class="hidden py-3 text-center text-[10px] text-slate-400">No more transactions</div>
          <div id="transactionEmpty" class="hidden py-6 text-center text-xs text-slate-400">No completed transactions found.</div>
        </div>
      </div>

      <!-- Bot settings / configuration -->
      <div class="liquid-card p-4">
        <div class="flex items-center justify-between mb-3">
          <div>
            <p class="text-[10px] uppercase font-bold tracking-wider text-slate-400">Configuration</p>
            <h3 class="text-sm font-bold text-[#0B2545]">Bot Settings</h3>
          </div>
          <span id="settingsBotLabel" class="text-[10px] font-bold text-blue-700 truncate max-w-[140px]">—</span>
        </div>
        <div id="settingsPanel" class="space-y-2"></div>
      </div>

      <!-- Super Admin network leaderboard -->
      <div id="superAdminLeaderboardCard" class="liquid-card p-4 hidden">
        <div class="flex items-center justify-between mb-3">
          <div>
            <p class="text-[10px] uppercase font-bold tracking-wider text-amber-700">Super Admin</p>
            <h3 class="text-sm font-bold text-[#0B2545]">Top Bot Leaderboards</h3>
          </div>
          <span class="text-[10px] text-slate-400">Top 100</span>
        </div>
        <div class="space-y-2.5">
          <div>
            <div class="flex items-center justify-between mb-1.5">
              <span class="text-xs font-bold text-slate-700 flex items-center gap-1.5"><i data-lucide="mouse-pointer-click" class="w-3.5 h-3.5"></i> Top Clicks Today</span>
              <span class="text-[10px] text-slate-400">Tap a bot for detail</span>
            </div>
            <div id="leaderboardClicks" class="space-y-1.5"></div>
          </div>
          <div>
            <div class="flex items-center justify-between mb-1.5 mt-3">
              <span class="text-xs font-bold text-slate-700 flex items-center gap-1.5"><i data-lucide="wallet" class="w-3.5 h-3.5"></i> Top Earnings</span>
              <span class="text-[10px] text-slate-400">Backend ranking</span>
            </div>
            <div id="leaderboardEarnings" class="space-y-1.5"></div>
          </div>
          <div>
            <div class="flex items-center justify-between mb-1.5 mt-3">
              <span class="text-xs font-bold text-slate-700 flex items-center gap-1.5"><i data-lucide="package-check" class="w-3.5 h-3.5"></i> Top Delivered / Views Today</span>
              <span class="text-[10px] text-slate-400">Backend ranking</span>
            </div>
            <div id="leaderboardViews" class="space-y-1.5"></div>
          </div>
        </div>
      </div>
    </div>

    <!-- ZERO BOTS EMPTY STATE (Shows when user has 0 bots and is not super admin) -->
    <div id="noBotsView" class="hidden py-8 px-2 text-center space-y-5">
      <div class="w-20 h-20 mx-auto rounded-3xl bg-gradient-to-tr from-amber-200 via-orange-100 to-rose-200 flex items-center justify-center text-[#133E87] shadow-lg shadow-amber-200/50">
        <i data-lucide="bot-off" class="w-10 h-10"></i>
      </div>
      
      <div class="space-y-2">
        <h2 class="text-xl font-extrabold text-[#0B2545]">No Cloned Bots Found</h2>
        <p class="text-xs text-slate-500 max-w-xs mx-auto leading-relaxed">
          Aapne abhi tak koi bot clone nahi kiya hai. Apne files share karne aur audience/earnings track karne ke liye pehle ek bot create karein!
        </p>
      </div>

      <div class="liquid-card p-4 text-left space-y-2.5 text-xs text-slate-600">
        <p class="font-bold text-[#0B2545] flex items-center gap-1.5">
          <i data-lucide="sparkles" class="w-4 h-4 text-amber-600"></i> Kaise Clone Karein?
        </p>
        <ol class="list-decimal list-inside space-y-1 text-slate-500 pl-1">
          <li>Telegram ke <span class="font-bold text-blue-700">@BotFather</span> se ek naya bot banayein.</li>
          <li>Apna API Token copy karein.</li>
          <li>Main bot me jakar <code class="bg-amber-100/70 px-1 py-0.5 rounded text-amber-900">/clone</code> send karein.</li>
        </ol>
      </div>

      <button onclick="openMainBotClone()" class="w-full py-3.5 px-4 rounded-2xl bg-gradient-to-r from-[#133E87] to-blue-700 text-white font-bold text-sm shadow-xl shadow-blue-900/20 active:scale-95 transition-transform flex items-center justify-center gap-2">
        <i data-lucide="plus-circle" class="w-4 h-4"></i> Create Your Clone Bot Now
      </button>
    </div>

    <!-- Error Toast Notification -->
    <div id="toastNotification" class="fixed bottom-24 left-1/2 -translate-x-1/2 w-[90%] max-w-xs liquid-card p-3 text-center text-xs font-bold text-rose-800 border-rose-300/80 bg-rose-50/95 shadow-xl transition-all duration-300 opacity-0 pointer-events-none translate-y-3 z-50">
      <span id="toastMessage">An error occurred</span>
    </div>

  </div>

  <!-- Floating Bottom Liquid Navigation Bar -->
  <nav id="bottomNav" class="fixed bottom-4 left-4 right-4 max-w-md mx-auto z-40">
    <div class="liquid-nav rounded-3xl p-1.5 flex items-center justify-around text-slate-400">
      
      <button onclick="switchTab('overview')" class="nav-item flex-1 py-2 rounded-2xl flex flex-col items-center justify-center text-xs font-bold transition-all text-[#133E87] bg-blue-50/90" data-tab="overview">
        <i data-lucide="layout-dashboard" class="w-4 h-4 mb-0.5"></i>
        <span>Overview</span>
      </button>

      <button onclick="switchTab('latency')" class="nav-item flex-1 py-2 rounded-2xl flex flex-col items-center justify-center text-xs font-bold transition-all hover:text-[#133E87]" data-tab="latency">
        <i data-lucide="zap" class="w-4 h-4 mb-0.5"></i>
        <span>Latency</span>
      </button>

      <button onclick="switchTab('audience')" class="nav-item flex-1 py-2 rounded-2xl flex flex-col items-center justify-center text-xs font-bold transition-all hover:text-[#133E87]" data-tab="audience">
        <i data-lucide="users" class="w-4 h-4 mb-0.5"></i>
        <span>Activity</span>
      </button>

      <button onclick="switchTab('revenue')" class="nav-item flex-1 py-2 rounded-2xl flex flex-col items-center justify-center text-xs font-bold transition-all hover:text-[#133E87]" data-tab="revenue">
        <i data-lucide="badge-indian-rupee" class="w-4 h-4 mb-0.5"></i>
        <span>Revenue</span>
      </button>

    </div>
  </nav>

  <script>
    // Global Application State
    const AppState = {
      tg: window.Telegram?.WebApp,
      initData: window.Telegram?.WebApp?.initData || "",
      user: null,
      isSuperAdmin: false,
      userBots: [],
      selectedBot: "all",
      currentTimeFilter: "24h",
      currentTab: "overview",
      tabHistory: ['overview'],
      charts: {},
      isDropdownOpen: false,
      isRefreshing: false,
      transactionPage: 1,
      transactionLimit: 20,
      transactionHasMore: false,
      transactionLoading: false,
      transactionItems: [],
      lastDashboardData: null,
      dashboardRequestSeq: 0
    };

    // Infinite-scroll listener for the transaction panel.
    window.addEventListener('load', () => {
      const scroller = document.getElementById('transactionScroller');
      if (!scroller) return;
      scroller.addEventListener('scroll', () => {
        const remaining = scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight;
        if (remaining < 120) loadMoreTransactions();
      }, { passive: true });
    });

    // Initialize on Window Load
    window.addEventListener('DOMContentLoaded', async () => {
      // Configure Telegram Mini App Defaults
      if (AppState.tg) {
        AppState.tg.ready();
        AppState.tg.expand();
        AppState.tg.enableClosingConfirmation();
        
        // Setup Telegram Native Back Button handler
        setupTelegramBackButton();
      }

      // Initialize Lucide Icons
      lucide.createIcons();

      // Authenticate & Load Dashboard
      await authenticateAndBootstrap();
    });

    function setupTelegramBackButton() {
      if (!AppState.tg?.BackButton) return;

      AppState.tg.BackButton.onClick(() => {
        // Provide gentle haptic tap
        AppState.tg.HapticFeedback?.impactOccurred('light');

        if (AppState.isDropdownOpen) {
          toggleBotDropdown(false);
          return;
        }

        // Pop navigation history
        if (AppState.tabHistory.length > 1) {
          AppState.tabHistory.pop(); // Remove current
          const previousTab = AppState.tabHistory[AppState.tabHistory.length - 1];
          applyTabSwitch(previousTab, false);
        } else {
          // At root 'overview' tab -> hide back button so default Telegram behavior applies
          AppState.tg.BackButton.hide();
        }
      });
    }

    function updateBackButtonVisibility() {
      if (!AppState.tg?.BackButton) return;
      if (AppState.tabHistory.length > 1 || AppState.currentTab !== 'overview') {
        AppState.tg.BackButton.show();
      } else {
        AppState.tg.BackButton.hide();
      }
    }

    async function authenticateAndBootstrap() {
      try {
        const response = await fetch('/api/auth', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ initData: AppState.initData })
        });

        const authData = await response.json();

        if (!authData.success) {
          throw new Error(authData.error || "Authentication failed");
        }

        AppState.user = authData;
        AppState.isSuperAdmin = authData.is_super_admin;
        AppState.userBots = authData.bots || [];

        // Update UI Header
        document.getElementById('headerUserName').textContent = authData.first_name ? `${authData.first_name}'s Stats` : "Analytics Pulse";
        if (AppState.isSuperAdmin) {
          document.getElementById('superAdminBadge').classList.remove('hidden');
        }

        // Check if user has zero bots
        if (!AppState.isSuperAdmin && AppState.userBots.length === 0) {
          showZeroBotsState();
          return;
        }

        // Set default bot selection
        if (AppState.isSuperAdmin) {
          AppState.selectedBot = "all";
        } else {
          AppState.selectedBot = AppState.userBots[0] || "none";
        }

        renderBotDropdownOptions();
        await fetchDashboardMetrics();

      } catch (err) {
        console.error("Auth error:", err);
        showToast("Session authentication error: " + err.message);
      }
    }

    function showZeroBotsState() {
      document.getElementById('tabOverview').classList.add('hidden');
      document.getElementById('tabLatency').classList.add('hidden');
      document.getElementById('tabAudience').classList.add('hidden');
      document.getElementById('tabRevenue').classList.add('hidden');
      document.getElementById('bottomNav').classList.add('hidden');
      document.getElementById('noBotsView').classList.remove('hidden');
      lucide.createIcons();
    }

    function openMainBotClone() {
      if (AppState.tg?.openTelegramLink) {
        AppState.tg.openTelegramLink('https://t.me/Echelon_File_Store_Bot');
      } else {
        window.open('https://t.me/Echelon_File_Store_Bot', '_blank');
      }
    }

    function renderBotDropdownOptions() {
      const container = document.getElementById('botOptionsList');
      container.innerHTML = '';

      // Super Admin "All Server" Option
      if (AppState.isSuperAdmin) {
        const allBtn = document.createElement('button');
        allBtn.className = `w-full text-left px-3 py-2 rounded-xl text-xs font-bold transition-all flex items-center justify-between ${AppState.selectedBot === 'all' ? 'bg-blue-800 text-white' : 'hover:bg-slate-100 text-slate-700'}`;
        allBtn.innerHTML = `<span>🌐 All Server Network</span> ${AppState.selectedBot === 'all' ? '<i data-lucide="check" class="w-3.5 h-3.5"></i>' : ''}`;
        allBtn.onclick = () => selectBot('all', '🌐 All Server Network');
        container.appendChild(allBtn);
      }

      // Individual Bots Options
      AppState.userBots.forEach(bot => {
        const btn = document.createElement('button');
        const isSel = AppState.selectedBot === bot;
        btn.className = `w-full text-left px-3 py-2 rounded-xl text-xs font-bold transition-all flex items-center justify-between ${isSel ? 'bg-blue-800 text-white' : 'hover:bg-slate-100 text-slate-700'}`;
        btn.innerHTML = `<span>@${bot}</span> ${isSel ? '<i data-lucide="check" class="w-3.5 h-3.5"></i>' : ''}`;
        btn.onclick = () => selectBot(bot, `@${bot}`);
        container.appendChild(btn);
      });

      // Update Label
      if (AppState.selectedBot === 'all') {
        document.getElementById('selectedBotLabel').textContent = "🌐 All Server Network";
      } else {
        document.getElementById('selectedBotLabel').textContent = `@${AppState.selectedBot}`;
      }

      lucide.createIcons();
    }

    function toggleBotDropdown(forceState) {
      const menu = document.getElementById('botDropdownMenu');
      const chevron = document.getElementById('botChevron');
      
      AppState.isDropdownOpen = typeof forceState === 'boolean' ? forceState : !AppState.isDropdownOpen;

      if (AppState.isDropdownOpen) {
        menu.classList.remove('hidden');
        chevron.style.transform = 'rotate(180deg)';
      } else {
        menu.classList.add('hidden');
        chevron.style.transform = 'rotate(0deg)';
      }
    }

    async function selectBot(botUsername, label) {
      AppState.selectedBot = botUsername;
      document.getElementById('selectedBotLabel').textContent = label;
      toggleBotDropdown(false);
      renderBotDropdownOptions();
      AppState.tg?.HapticFeedback?.impactOccurred('medium');
      await fetchDashboardMetrics({ resetTransactions: true });
    }

    async function setTimeFilter(filterKey) {
      AppState.currentTimeFilter = filterKey;
      document.querySelectorAll('.time-filter-btn').forEach(btn => {
        if (btn.getAttribute('data-filter') === filterKey) {
          btn.className = "time-filter-btn flex-1 py-1.5 rounded-xl transition-all text-center active-filter bg-[#133E87] text-white shadow-sm";
        } else {
          btn.className = "time-filter-btn flex-1 py-1.5 rounded-xl transition-all text-center text-slate-600 hover:text-blue-900";
        }
      });
      AppState.tg?.HapticFeedback?.impactOccurred('light');
      await fetchDashboardMetrics({ resetTransactions: true });
    }

    async function triggerRefresh() {
      if (AppState.isRefreshing) return;
      AppState.isRefreshing = true;
      const btn = document.getElementById('refreshBtn');
      btn.classList.add('animate-spin');
      AppState.tg?.HapticFeedback?.notificationOccurred('success');

      await fetchDashboardMetrics({ resetTransactions: true });

      setTimeout(() => {
        btn.classList.remove('animate-spin');
        AppState.isRefreshing = false;
      }, 500);
    }

    async function fetchDashboardMetrics({ resetTransactions = true, page = 1 } = {}) {
      const seq = ++AppState.dashboardRequestSeq;
      try {
        if (resetTransactions) {
          AppState.transactionPage = 1;
          AppState.transactionHasMore = false;
          AppState.transactionItems = [];
          AppState.transactionLoading = false;
          const list = document.getElementById('transactionList');
          if (list) list.innerHTML = '';
          document.getElementById('transactionEnd')?.classList.add('hidden');
          document.getElementById('transactionEmpty')?.classList.add('hidden');
        }

        const requestedPage = resetTransactions ? 1 : page;
        AppState.transactionLoading = !resetTransactions;
        document.getElementById('transactionLoader')?.classList.toggle('hidden', !AppState.transactionLoading);

        const response = await fetch('/api/dashboard-data', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            initData: AppState.initData,
            bot_username: AppState.selectedBot,
            time_filter: AppState.currentTimeFilter,
            page: requestedPage,
            limit: AppState.transactionLimit
          })
        });

        const res = await response.json();
        if (seq !== AppState.dashboardRequestSeq) return;
        if (!res.success) throw new Error(res.error || "Failed to load dashboard data");

        AppState.lastDashboardData = res;
        if (resetTransactions) {
          AppState.transactionItems = Array.isArray(res.latest_transactions) ? res.latest_transactions : [];
        } else {
          const incoming = Array.isArray(res.latest_transactions) ? res.latest_transactions : [];
          AppState.transactionItems = [...AppState.transactionItems, ...incoming];
        }

        AppState.transactionPage = requestedPage;
        AppState.transactionHasMore = !!res.pagination?.has_more;
        renderTransactionList({ replace: resetTransactions });
        updateDashboardUI(res);
      } catch (err) {
        console.error("Dashboard fetch error:", err);
        if (resetTransactions) {
          document.getElementById('transactionEmpty')?.classList.remove('hidden');
        }
        showToast("Metrics sync error: " + err.message);
      } finally {
        AppState.transactionLoading = false;
        document.getElementById('transactionLoader')?.classList.add('hidden');
      }
    }

    async function loadMoreTransactions() {
      if (AppState.transactionLoading || !AppState.transactionHasMore) return;
      await fetchDashboardMetrics({ resetTransactions: false, page: AppState.transactionPage + 1 });
    }

    function renderTransactionList() {
      const list = document.getElementById('transactionList');
      const empty = document.getElementById('transactionEmpty');
      const end = document.getElementById('transactionEnd');
      const summary = document.getElementById('transactionSummary');
      if (!list) return;

      list.innerHTML = '';
      if (!AppState.transactionItems.length) {
        empty?.classList.remove('hidden');
        end?.classList.add('hidden');
        if (summary) summary.textContent = '0 loaded';
        return;
      }
      empty?.classList.add('hidden');
      const total = AppState.lastDashboardData?.pagination?.total_items;
      if (summary) summary.textContent = `${AppState.transactionItems.length.toLocaleString()} loaded${Number.isFinite(total) ? ` • ${Number(total).toLocaleString()} total` : ''}`;

      AppState.transactionItems.forEach((tx, index) => {
        const row = document.createElement('div');
        const isStars = String(tx.currency || '').toUpperCase() === 'XTR';
        const type = tx.type || (tx.target_payload ? 'Paid Message' : 'Premium Subscription');
        const status = tx.status || 'Paid';
        const amount = formatMoney(tx.amount, tx.currency);
        row.className = 'detail-card p-3';
        row.innerHTML = `
          <div class="flex items-start justify-between gap-3">
            <div class="min-w-0">
              <div class="flex items-center gap-2 flex-wrap">
                <span class="px-2 py-0.5 rounded-full text-[10px] font-bold ${type === 'Paid Message' ? 'bg-violet-100 text-violet-800' : 'bg-amber-100 text-amber-800'}">${escapeHtml(type)}</span>
                <span class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-100 text-emerald-800">${escapeHtml(status)}</span>
              </div>
              <p class="text-sm font-extrabold text-[#0B2545] mt-1.5">${escapeHtml(amount)}</p>
            </div>
            <span class="text-[10px] font-semibold text-slate-400 whitespace-nowrap">#${escapeHtml(String(tx.transaction_id ?? index + 1))}</span>
          </div>
          <div class="grid grid-cols-2 gap-2 mt-2.5 text-[10px]">
            <div class="metric-mini p-2">
              <p class="text-slate-400 font-semibold">User ID</p>
              <p class="text-slate-700 font-bold mt-0.5 break-all">${escapeHtml(String(tx.user_id ?? '—'))}</p>
            </div>
            <div class="metric-mini p-2">
              <p class="text-slate-400 font-semibold">Bot</p>
              <p class="text-slate-700 font-bold mt-0.5 truncate">@${escapeHtml(tx.bot || '—')}</p>
            </div>
          </div>
          <div class="mt-2 text-[10px] text-slate-500">
            <div class="flex items-center justify-between gap-2"><span>Product</span><span class="font-semibold text-right">${escapeHtml(tx.product_detail || 'Standard Plan')}</span></div>
            <div class="flex items-center justify-between gap-2 mt-1"><span>Completed</span><span class="font-semibold text-right">${escapeHtml(formatDateTime(tx.time))}</span></div>
          </div>
        `;
        list.appendChild(row);
      });
      end?.classList.toggle('hidden', AppState.transactionHasMore);
      lucide.createIcons();

      const scroller = document.getElementById('transactionScroller');
      if (scroller && AppState.transactionHasMore && !AppState.transactionLoading && scroller.scrollHeight <= scroller.clientHeight + 24) {
        setTimeout(() => loadMoreTransactions(), 0);
      }
    }

    function formatMoney(amount, currency) {
      const n = Number(amount || 0);
      const c = String(currency || 'INR').toUpperCase();
      if (c === 'XTR') return `⭐ ${n.toLocaleString('en-IN')} XTR`;
      if (c === 'USD') return `$${n.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
      if (c === 'EUR') return `€${n.toLocaleString('de-DE', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
      return `₹${n.toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
    }

    function formatDateTime(value) {
      if (!value) return '—';
      const d = new Date(value);
      if (Number.isNaN(d.getTime())) return String(value);
      return d.toLocaleString('en-IN', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
    }

    function escapeHtml(value) {
      return String(value ?? '').replace(/[&<>'\"]/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','\"':'&quot;'}[ch]));
    }

    function updateDashboardUI(data) {
      const stats = data.stats || {};
      const graphs = data.latency_graph || [];

      document.getElementById('metricLiveConcurrency').textContent = stats.server_busy_concurrency ?? stats.current_active_concurrency ?? 0;

      let avgLat = 0, p95Lat = 0, maxLat = 0;
      if (graphs.length > 0) {
        const avgValues = graphs.map(g => Number(g.avg_latency || 0)).filter(Number.isFinite);
        const p95Values = graphs.map(g => Number(g.p95_latency || 0)).filter(Number.isFinite);
        const maxValues = graphs.map(g => Number(g.max_latency || 0)).filter(Number.isFinite);
        avgLat = avgValues.length ? Math.round(avgValues.reduce((a,b) => a+b, 0) / avgValues.length) : 0;
        p95Lat = p95Values.length ? Math.round(p95Values[p95Values.length - 1]) : 0;
        maxLat = maxValues.length ? Math.round(Math.max(...maxValues)) : 0;
      }

      document.getElementById('metricAvgDelivery').textContent = avgLat;
      document.getElementById('metricP95Delivery').textContent = `P95: ${p95Lat}ms`;
      document.getElementById('serverStatusText').textContent = `Live • Avg ${avgLat}ms`;
      document.getElementById('latCardAvg').textContent = `${avgLat}ms`;
      document.getElementById('latCardP95').textContent = `${p95Lat}ms`;
      document.getElementById('latCardMax').textContent = `${maxLat}ms`;

      const tClicks = Number(stats.today_clicks || 0);
      const tViews = Number(stats.today_views || 0);
      document.getElementById('metricTodayClicks').textContent = tClicks.toLocaleString('en-IN');
      document.getElementById('metricTotalClicks').textContent = Number(stats.total_clicks || 0).toLocaleString('en-IN');
      document.getElementById('metricTodayViews').textContent = tViews.toLocaleString('en-IN');
      document.getElementById('metricTotalViews').textContent = Number(stats.total_views ?? 0).toLocaleString('en-IN');
      document.getElementById('metricActiveUsers').textContent = Number(stats.active_users_today ?? 0).toLocaleString('en-IN');
      document.getElementById('metricTotalUsers').textContent = Number(stats.total_users ?? 0).toLocaleString('en-IN');
      document.getElementById('metricTotalPremium').textContent = stats.total_premium == null ? '—' : Number(stats.total_premium).toLocaleString('en-IN');
      document.getElementById('metricTotalLinks').textContent = stats.total_links == null ? '—' : Number(stats.total_links).toLocaleString('en-IN');

      document.getElementById('convClicksVal').textContent = tClicks.toLocaleString('en-IN');
      document.getElementById('convViewsVal').textContent = tViews.toLocaleString('en-IN');
      const convRate = tClicks > 0 ? ((tViews / tClicks) * 100) : 0;
      document.getElementById('convRatePercent').textContent = `${convRate.toFixed(1)}%`;
      document.getElementById('convViewsBar').style.width = `${Math.min(100, convRate)}%`;

      const todayRev = Number(stats.today_revenue ?? 0);
      const totalRev = Number(stats.total_revenue ?? 0);
      const todayText = `₹${todayRev.toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
      const totalText = `₹${totalRev.toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
      document.getElementById('metricTodayRev').textContent = todayText;
      document.getElementById('metricTotalRev').textContent = totalText;
      document.getElementById('revHeroToday').textContent = todayText;
      document.getElementById('revHeroTotal').textContent = totalText;

      document.getElementById('liveTimestamp').textContent = new Date().toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});

      if (AppState.isSuperAdmin && data.bot_settings) {
        const discovered = Object.keys(data.bot_settings);
        AppState.userBots = Array.from(new Set([...AppState.userBots, ...discovered])).sort();
        renderBotDropdownOptions();
      }
      updateBillingUI(data.pending_bills);
      updateSettingsUI(data.bot_settings || {});
      updateGatewayUI(data.bot_settings || {});
      updateLeaderboards(data.leaderboard);
      renderCharts(graphs);
    }

    function updateBillingUI(bill) {
      const grid = document.getElementById('billingGrid');
      const badge = document.getElementById('billingLockBadge');
      const note = document.getElementById('billingNote');
      if (!grid) return;
      grid.innerHTML = '';
      note?.classList.add('hidden');
      if (!bill) {
        grid.innerHTML = `<div class="col-span-2 metric-mini p-3 text-xs text-slate-400">No billing data supplied by API.</div>`;
        badge.textContent = '—';
        return;
      }
      if (bill.note) {
        note.textContent = bill.note;
        note.classList.remove('hidden');
      }
      badge.textContent = bill.is_locked ? 'Locked' : (bill.is_locked === false ? 'Open' : '—');
      badge.className = `px-2 py-0.5 text-[10px] font-bold rounded-full ${bill.is_locked ? 'bg-rose-100 text-rose-700' : 'bg-emerald-100 text-emerald-700'}`;
      const items = [
        ['Total Sales', bill.total_sales],
        ['Commission Bill', bill.total_commission_bill],
        ['Total Paid', bill.total_paid],
        ['Pending Bill', bill.pending_bill]
      ];
      items.forEach(([label, value]) => {
        const el = document.createElement('div');
        el.className = 'metric-mini p-3';
        el.innerHTML = `<p class="text-[10px] font-semibold text-slate-400">${escapeHtml(label)}</p><p class="text-sm font-extrabold text-[#0B2545] mt-1">${typeof value === 'number' ? `₹${value.toLocaleString('en-IN',{minimumFractionDigits:2,maximumFractionDigits:2})}` : escapeHtml(value ?? '—')}</p>`;
        grid.appendChild(el);
      });
    }

    function updateSettingsUI(settingsByBot) {
      const panel = document.getElementById('settingsPanel');
      const label = document.getElementById('settingsBotLabel');
      if (!panel) return;
      panel.innerHTML = '';
      const names = Object.keys(settingsByBot || {});
      label.textContent = AppState.selectedBot === 'all' ? `${names.length} bots` : `@${AppState.selectedBot}`;

      if (!names.length) {
        panel.innerHTML = `<div class="text-xs text-slate-400">No settings were returned for this selection.</div>`;
        return;
      }
      const renderOne = (bot, cfg) => {
        const card = document.createElement('div');
        card.className = 'detail-card p-3';
        const bool = (v) => v ? '<span class="text-emerald-700 font-bold">ON</span>' : '<span class="text-slate-400 font-bold">OFF</span>';
        card.innerHTML = `
          <div class="flex items-center justify-between mb-2">
            <span class="text-xs font-extrabold text-[#0B2545]">@${escapeHtml(bot)}</span>
            ${AppState.isSuperAdmin ? `<button class="text-[10px] font-bold text-blue-700 hover:text-blue-900" data-open-bot="${escapeHtml(bot)}">View bot</button>` : ''}
          </div>
          <div class="grid grid-cols-2 gap-2 text-[10px]">
            <div class="metric-mini p-2"><p class="text-slate-400">Protection</p><p class="mt-0.5">${bool(cfg.protected_content)}</p></div>
            <div class="metric-mini p-2"><p class="text-slate-400">Auto Delete</p><p class="mt-0.5">${bool(cfg.file_deletion)}</p></div>
            <div class="metric-mini p-2"><p class="text-slate-400">Delete After</p><p class="font-bold text-slate-700 mt-0.5">${escapeHtml(formatDuration(cfg.deletion_time_seconds))}</p></div>
            <div class="metric-mini p-2"><p class="text-slate-400">FSUB Channels</p><p class="font-bold text-slate-700 mt-0.5">${Number(cfg.fsub_channels_count ?? 0)}</p></div>
            <div class="metric-mini p-2"><p class="text-slate-400">Admins</p><p class="font-bold text-slate-700 mt-0.5">${Number(cfg.admins_count ?? 0)}</p></div>
            <div class="metric-mini p-2"><p class="text-slate-400">Welcome Msg</p><p class="mt-0.5">${bool(cfg.welcome_message_set)}</p></div>
            <div class="metric-mini p-2 col-span-2"><p class="text-slate-400">UPI ID</p><p class="setting-value font-bold text-slate-700 mt-0.5">${escapeHtml(cfg.upi_id || 'Not Set')}</p></div>
            <div class="metric-mini p-2"><p class="text-slate-400">Cashfree</p><p class="mt-0.5">${bool(cfg.cashfree_enabled)}</p></div>
            <div class="metric-mini p-2"><p class="text-slate-400">Stars</p><p class="mt-0.5">${bool(cfg.stars_enabled)}</p></div>
          </div>`;
        const btn = card.querySelector('[data-open-bot]');
        if (btn) btn.onclick = () => selectBot(btn.dataset.openBot, `@${btn.dataset.openBot}`);
        panel.appendChild(card);
      };

      if (AppState.selectedBot !== 'all') {
        renderOne(AppState.selectedBot, settingsByBot[AppState.selectedBot] || {});
      } else {
        names.slice(0, 100).forEach(name => renderOne(name, settingsByBot[name] || {}));
      }
      lucide.createIcons();
    }

    function formatDuration(seconds) {
      const s = Number(seconds || 0);
      if (!s) return 'Disabled';
      if (s % 3600 === 0) return `${s / 3600}h`;
      if (s % 60 === 0) return `${s / 60}m`;
      return `${s}s`;
    }

    function updateGatewayUI(settingsByBot) {
      const cfg = settingsByBot?.[AppState.selectedBot];
      if (!cfg) {
        document.getElementById('gatewayUpiText').textContent = AppState.selectedBot === 'all' ? 'Select a bot for per-bot UPI' : 'Not set';
        document.getElementById('gatewayStarsText').textContent = AppState.selectedBot === 'all' ? 'Select a bot for per-bot Stars' : 'Not configured';
        document.getElementById('gatewayCashfreeBadge').textContent = '—';
        document.getElementById('gatewayUpiBadge').textContent = '—';
        document.getElementById('gatewayStarsBadge').textContent = '—';
        return;
      }
      document.getElementById('gatewayUpiText').textContent = cfg.upi_id && cfg.upi_id !== 'Not Set' ? cfg.upi_id : 'UPI ID not set';
      document.getElementById('gatewayStarsText').textContent = cfg.stars_enabled ? 'Enabled in bot settings' : 'Disabled in bot settings';
      document.getElementById('gatewayCashfreeBadge').textContent = cfg.cashfree_enabled ? 'Enabled' : 'Disabled';
      document.getElementById('gatewayUpiBadge').textContent = cfg.upi_id && cfg.upi_id !== 'Not Set' ? 'Configured' : 'Not Set';
      document.getElementById('gatewayStarsBadge').textContent = cfg.stars_enabled ? 'Enabled' : 'Disabled';
    }

    function updateLeaderboards(board) {
      const card = document.getElementById('superAdminLeaderboardCard');
      if (!card) return;
      if (!AppState.isSuperAdmin || !board) {
        card.classList.add('hidden');
        return;
      }
      card.classList.remove('hidden');
      renderLeaderboard('leaderboardClicks', board.top_clicks || [], 'count', value => Number(value || 0).toLocaleString('en-IN'));
      renderLeaderboard('leaderboardEarnings', board.top_earnings || [], 'amount', value => `₹${Number(value || 0).toLocaleString('en-IN',{minimumFractionDigits:2,maximumFractionDigits:2})}`);
      renderLeaderboard('leaderboardViews', board.top_views || [], 'count', value => Number(value || 0).toLocaleString('en-IN'));
    }

    function renderLeaderboard(id, rows, valueKey, formatValue) {
      const container = document.getElementById(id);
      if (!container) return;
      container.innerHTML = '';
      rows.slice(0,100).forEach((row, idx) => {
        const el = document.createElement('button');
        el.type = 'button';
        el.className = 'w-full flex items-center justify-between gap-2 p-2 rounded-xl bg-slate-50/80 border border-slate-100 hover:bg-blue-50/70 transition text-left';
        el.innerHTML = `<span class="flex items-center gap-2 min-w-0"><span class="w-5 text-[10px] font-extrabold text-slate-400">${idx+1}</span><span class="text-[11px] font-bold text-slate-700 truncate">@${escapeHtml(row.bot || '—')}</span></span><span class="text-[10px] font-extrabold text-[#133E87]">${escapeHtml(formatValue(row[valueKey]))}</span>`;
        el.onclick = () => selectBot(row.bot, `@${row.bot}`);
        container.appendChild(el);
      });
      if (!rows.length) container.innerHTML = `<div class="text-[10px] text-slate-400">No leaderboard data returned.</div>`;
    }

    function renderCharts(timeSeriesData) {
      const labels = timeSeriesData.map(d => {
        const dt = new Date(d.timestamp);
        return dt.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
      });

      const avgLatencies = timeSeriesData.map(d => d.avg_latency || 0);
      const p95Latencies = timeSeriesData.map(d => d.p95_latency || 0);
      const requestsData = timeSeriesData.map(d => d.requests || 0);
      const concurrencyData = timeSeriesData.map(d => d.concurrency || 0);

      // Chart Common Options
      const baseGridConfig = {
        color: 'rgba(230, 214, 198, 0.4)',
        drawBorder: false
      };

      // 1. Quick Traffic Chart (Overview Tab)
      initOrUpdateChart('quickTrafficChart', {
        type: 'line',
        data: {
          labels: labels,
          datasets: [{
            label: 'Requests',
            data: requestsData,
            borderColor: '#1D4ED8',
            backgroundColor: 'rgba(29, 78, 216, 0.08)',
            borderWidth: 2.5,
            tension: 0.35,
            fill: true,
            pointRadius: 0
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: {
            x: { grid: { display: false }, ticks: { maxTicksLimit: 6, font: { size: 10 } } },
            y: { grid: baseGridConfig, ticks: { maxTicksLimit: 4, font: { size: 10 } } }
          }
        }
      });

      // 2. Detailed Latency Chart (Latency Tab)
      initOrUpdateChart('detailedLatencyChart', {
        type: 'line',
        data: {
          labels: labels,
          datasets: [
            {
              label: 'Average Latency',
              data: avgLatencies,
              borderColor: '#133E87',
              backgroundColor: 'rgba(19, 62, 135, 0.08)',
              borderWidth: 2,
              tension: 0.3,
              pointRadius: 0
            },
            {
              label: 'P95 Latency',
              data: p95Latencies,
              borderColor: '#6366F1',
              borderWidth: 2,
              borderDash: [4, 4],
              tension: 0.3,
              pointRadius: 0
            }
          ]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: {
              position: 'top',
              labels: { boxWidth: 10, font: { size: 11, weight: 'bold' } }
            }
          },
          scales: {
            x: { grid: { display: false }, ticks: { maxTicksLimit: 6, font: { size: 10 } } },
            y: { grid: baseGridConfig, ticks: { maxTicksLimit: 5, font: { size: 10 } } }
          }
        }
      });

      // 3. Concurrency Load Chart
      initOrUpdateChart('concurrencyChart', {
        type: 'bar',
        data: {
          labels: labels,
          datasets: [{
            label: 'Concurrent Workers',
            data: concurrencyData,
            backgroundColor: 'rgba(245, 158, 11, 0.75)',
            borderRadius: 6
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: {
            x: { grid: { display: false }, ticks: { maxTicksLimit: 6, font: { size: 10 } } },
            y: { grid: baseGridConfig, ticks: { maxTicksLimit: 4, font: { size: 10 }, stepSize: 1 } }
          }
        }
      });

      // 4. Audience Requests Chart (Activity Tab)
      initOrUpdateChart('audienceRequestsChart', {
        type: 'bar',
        data: {
          labels: labels,
          datasets: [{
            label: 'Activity Batches',
            data: requestsData,
            backgroundColor: 'rgba(29, 78, 216, 0.7)',
            borderRadius: 6
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: {
            x: { grid: { display: false }, ticks: { maxTicksLimit: 6, font: { size: 10 } } },
            y: { grid: baseGridConfig, ticks: { maxTicksLimit: 5, font: { size: 10 } } }
          }
        }
      });
    }

    function initOrUpdateChart(canvasId, config) {
      const ctx = document.getElementById(canvasId)?.getContext('2d');
      if (!ctx) return;

      if (AppState.charts[canvasId]) {
        AppState.charts[canvasId].destroy();
      }

      AppState.charts[canvasId] = new Chart(ctx, config);
    }

    function switchTab(tabId) {
      if (AppState.currentTab === tabId) return;

      AppState.tg?.HapticFeedback?.impactOccurred('light');

      // Update Tab History Stack for BackButton
      if (AppState.tabHistory[AppState.tabHistory.length - 1] !== tabId) {
        AppState.tabHistory.push(tabId);
      }

      applyTabSwitch(tabId, true);
    }

    function applyTabSwitch(tabId, updateBackBtn = true) {
      AppState.currentTab = tabId;

      // Hide all contents
      document.querySelectorAll('.tab-content').forEach(el => el.classList.add('hidden'));

      // Show selected
      const activeContent = document.getElementById(`tab${capitalize(tabId)}`);
      if (activeContent) {
        activeContent.classList.remove('hidden');
      }

      // Update Navigation styling
      document.querySelectorAll('.nav-item').forEach(btn => {
        if (btn.getAttribute('data-tab') === tabId) {
          btn.className = "nav-item flex-1 py-2 rounded-2xl flex flex-col items-center justify-center text-xs font-bold transition-all text-[#133E87] bg-blue-50/90";
        } else {
          btn.className = "nav-item flex-1 py-2 rounded-2xl flex flex-col items-center justify-center text-xs font-bold transition-all text-slate-400 hover:text-[#133E87]";
        }
      });

      if (updateBackBtn) {
        updateBackButtonVisibility();
      }

      // Trigger charts resize after unhiding tab
      setTimeout(() => {
        Object.values(AppState.charts).forEach(c => c?.resize());
      }, 50);

      window.scrollTo({ top: 0, behavior: 'smooth' });
    }

    function showToast(message) {
      const toast = document.getElementById('toastNotification');
      document.getElementById('toastMessage').textContent = message;
      toast.classList.remove('opacity-0', 'pointer-events-none', 'translate-y-3');
      toast.classList.add('opacity-100', 'translate-y-0');

      setTimeout(() => {
        toast.classList.add('opacity-0', 'pointer-events-none', 'translate-y-3');
        toast.classList.remove('opacity-100', 'translate-y-0');
      }, 3500);
    }

    function capitalize(str) {
      return str.charAt(0).toUpperCase() + str.slice(1);
    }
  </script>
</body>
</html>
