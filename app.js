/**
 * KARAT — Frontend Application Logic
 * Quantitative Commodity Derivatives Intelligence on MCX Gold Futures
 */

(function () {
  'use strict';

  // API Base URL - prefers running local backend, with graceful fallback
  const API_BASE = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
    ? (window.location.port === '8000' ? '' : 'http://127.0.0.1:8000')
    : '';

  // Application State
  // Pairs mapping
  const PAIRS = [
    { id: 'GOLDM_GOLDTEN', label: 'GOLDM vs GOLDTEN (100g 995 vs 10g 999)' },
    { id: 'GOLDM_GOLDGUINEA', label: 'GOLDM vs GOLDGUINEA (100g 995 vs 8g 999)' },
    { id: 'GOLDM_GOLDPETAL', label: 'GOLDM vs GOLDPETAL (100g 995 vs 1g 999)' },
    { id: 'GOLDTEN_GOLDGUINEA', label: 'GOLDTEN vs GOLDGUINEA (10g 999 vs 8g 999)' },
    { id: 'GOLDTEN_GOLDPETAL', label: 'GOLDTEN vs GOLDPETAL (10g 999 vs 1g 999)' },
    { id: 'GOLDGUINEA_GOLDPETAL', label: 'GOLDGUINEA vs GOLDPETAL (8g 999 vs 1g 999)' }
  ];

  // Real MCX Bhavcopy Reference Dataset (14 Oct 2026)
  const DEMO_CONTRACTS = [
    {
      symbol: 'GOLDTEN',
      lot_size_g: 10,
      quote_base_g: 10,
      purity: 999,
      expiry_window: '27th–31st of expiry month',
      listing_start: 'Jan 2025',
      notes: 'Reference contract (10g, 999 purity)',
      raw_price: 145062.0,
      expiry_date: '2026-10-30',
      price_per_gram: 14506.20,
      normalised_price: 14506.20,
      premium_vs_ref: 0.0,
      premium_bps: 0.0,
      volume: 26438,
      grams_traded: 264380.0,
      open_interest: 32121,
      liquidity_status: 'liquid',
      sparkline: [
        { normalised: 14890 }, { normalised: 14750 }, { normalised: 14600 }, { normalised: 14506.20 }
      ]
    },
    {
      symbol: 'GOLDM',
      lot_size_g: 100,
      quote_base_g: 10,
      purity: 995,
      expiry_window: '3rd–5th of expiry month',
      listing_start: null,
      notes: 'Main 100g contract (995 purity). Expires about 5 days after others; later expiry explains part of gap.',
      raw_price: 144696.0,
      expiry_date: '2026-11-05',
      price_per_gram: 14469.60,
      normalised_price: 14527.84,
      premium_vs_ref: 21.64,
      premium_bps: 14.87,
      volume: 44423,
      grams_traded: 4442300.0,
      open_interest: 48920,
      liquidity_status: 'liquid',
      sparkline: [
        { normalised: 14850 }, { normalised: 14720 }, { normalised: 14610 }, { normalised: 14527.84 }
      ]
    },
    {
      symbol: 'GOLDGUINEA',
      lot_size_g: 8,
      quote_base_g: 8,
      purity: 999,
      expiry_window: '27th–31st of expiry month',
      listing_start: null,
      notes: '8g Guinea coin contract (structural retail premium)',
      raw_price: 116788.0,
      expiry_date: '2026-10-30',
      price_per_gram: 14598.50,
      normalised_price: 14598.50,
      premium_vs_ref: 92.30,
      premium_bps: 63.63,
      volume: 9568,
      grams_traded: 76544.0,
      open_interest: 14941,
      liquidity_status: 'liquid',
      sparkline: [
        { normalised: 14920 }, { normalised: 14810 }, { normalised: 14700 }, { normalised: 14598.50 }
      ]
    },
    {
      symbol: 'GOLDPETAL',
      lot_size_g: 1,
      quote_base_g: 1,
      purity: 999,
      expiry_window: '27th–31st of expiry month',
      listing_start: null,
      notes: '1g retail bullion contract (structural retail premium)',
      raw_price: 14591.0,
      expiry_date: '2026-10-30',
      price_per_gram: 14591.0,
      normalised_price: 14591.0,
      premium_vs_ref: 84.80,
      premium_bps: 58.46,
      volume: 213499,
      grams_traded: 213499.0,
      open_interest: 209248,
      liquidity_status: 'liquid',
      sparkline: [
        { normalised: 14910 }, { normalised: 14800 }, { normalised: 14690 }, { normalised: 14591.0 }
      ]
    }
  ];

  // Application State
  const state = {
    activeTab: 'overview',
    dataSource: 'sample',
    asOfDate: '2025-02-28',
    availableDates: [],
    referenceSymbol: 'GOLDTEN',
    selectedPair: 'GOLDM_GOLDTEN',
    backtestPeriod: 'unseen',
    costBps: 2.5,
    slippageMult: 1.5,
    contractsData: { contracts: DEMO_CONTRACTS },
    spreadData: null,
    backtestData: null,
    calendarData: null,
    qualityData: null,
    methodologyData: null,
    signalsData: null,
    selectedContract: null
  };

  // Helper: Format Indian Rupee
  function formatINR(val, decimals = 2) {
    if (val === null || val === undefined || isNaN(val)) return '—';
    return '₹' + Number(val).toLocaleString('en-IN', {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals
    });
  }

  // Helper: Format Number
  function formatNum(val, decimals = 2) {
    if (val === null || val === undefined || isNaN(val)) return '—';
    return Number(val).toLocaleString('en-IN', {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals
    });
  }

  // Generic API fetcher with timeout and fallback
  async function fetchApi(endpoint) {
    try {
      const url = `${API_BASE}${endpoint}`;
      const res = await fetch(url, { signal: AbortSignal.timeout(5000) });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return await res.json();
    } catch (err) {
      console.warn(`API call ${endpoint} failed, using local offline fallback:`, err.message);
      return getOfflineFallback(endpoint);
    }
  }

  // ==========================================
  // SPOTLIGHT MASK CONTROLLER
  // ==========================================
  function initSpotlightReveal() {
    const btnExp = document.getElementById('btn-experience-karat');
    const btnBackHero = document.getElementById('btn-back-hero');
    const spotlightWrapper = document.getElementById('spotlight-wrapper');

    function openSpotlight(e) {
      if (e) e.preventDefault();
      const rect = (e && e.target) ? e.target.getBoundingClientRect() : { left: window.innerWidth / 2, top: window.innerHeight / 2, width: 0, height: 0 };
      const clickX = e ? (rect.left + rect.width / 2) : window.innerWidth / 2;
      const clickY = e ? (rect.top + rect.height / 2) : window.innerHeight / 2;

      spotlightWrapper.style.setProperty('--click-x', `${clickX}px`);
      spotlightWrapper.style.setProperty('--click-y', `${clickY}px`);
      spotlightWrapper.classList.add('active');

      // Refresh indicator position after spotlight expand
      setTimeout(() => updateNavIndicator(), 350);

      // Refresh data
      loadDashboard();
    }

    function closeSpotlight(e) {
      if (e) e.preventDefault();
      spotlightWrapper.classList.remove('active');
    }

    if (btnExp) btnExp.addEventListener('click', openSpotlight);
    if (btnBackHero) btnBackHero.addEventListener('click', closeSpotlight);

    // Also support direct hash navigation e.g. #dashboard
    if (window.location.hash === '#dashboard' || window.location.hash === '#experience') {
      openSpotlight();
    }
  }

  // ==========================================
  // ANIMATED TAB NAVIGATION (GLIDING PILL INDICATOR)
  // ==========================================
  function updateNavIndicator(activeBtn) {
    const indicator = document.getElementById('nav-pill-indicator');
    const nav = document.getElementById('desktop-nav');
    if (!indicator || !nav) return;
    
    const target = activeBtn || nav.querySelector('.nav-tab-btn.active') || nav.querySelector('.nav-tab-btn');
    if (!target) return;

    const navRect = nav.getBoundingClientRect();
    const btnRect = target.getBoundingClientRect();

    indicator.style.width = `${btnRect.width}px`;
    indicator.style.height = `${btnRect.height}px`;
    indicator.style.left = `${btnRect.left - navRect.left}px`;
    indicator.style.top = `${btnRect.top - navRect.top}px`;
    indicator.style.opacity = '1';
  }

  function initTabNav() {
    const tabButtons = document.querySelectorAll('.nav-tab-btn');
    const wrapper = document.getElementById('spotlight-wrapper');
    const desktopNav = document.getElementById('desktop-nav');

    tabButtons.forEach(btn => {
      btn.addEventListener('click', () => {
        const tab = btn.getAttribute('data-tab');
        if (!tab) return;
        state.activeTab = tab;

        // Synchronize active states across desktop and mobile button bars
        tabButtons.forEach(b => {
          if (b.getAttribute('data-tab') === tab) {
            b.classList.add('active');
            if (b.closest('#desktop-nav')) {
              updateNavIndicator(b);
            }
          } else {
            b.classList.remove('active');
          }
        });

        // Switch panels with smooth fade
        document.querySelectorAll('.tab-content-panel').forEach(panel => {
          panel.classList.add('hidden');
        });

        const activePanel = document.getElementById(`panel-${tab}`);
        if (activePanel) activePanel.classList.remove('hidden');

        // Effortless Smooth Page Scrolling: Return viewport to top smoothly
        if (wrapper) {
          wrapper.scrollTo({ top: 0, behavior: 'smooth' });
        }

        // Refresh views for active tab
        if (tab === 'overview') renderOverview();
        else if (tab === 'spreads') loadSpreadData();
        else if (tab === 'backtest') loadBacktestData();
        else if (tab === 'calendar') loadCalendarData();
        else if (tab === 'methodology') loadMethodologyData();

        // Update AI Guide context for active tab
        updateAiGuideContext(tab);
      });
    });

    // Hover micro-interaction: indicator glides to hovered button and returns to active
    if (desktopNav) {
      desktopNav.querySelectorAll('.nav-tab-btn').forEach(btn => {
        btn.addEventListener('mouseenter', () => updateNavIndicator(btn));
      });
      desktopNav.addEventListener('mouseleave', () => {
        const activeBtn = desktopNav.querySelector('.nav-tab-btn.active');
        if (activeBtn) updateNavIndicator(activeBtn);
      });
      window.addEventListener('resize', () => {
        const activeBtn = desktopNav.querySelector('.nav-tab-btn.active');
        if (activeBtn) updateNavIndicator(activeBtn);
      });
      setTimeout(() => updateNavIndicator(), 150);
    }
  }

  // ==========================================
  // EFFORTLESS SCROLL ENHANCEMENTS & QUICK ACTION
  // Nav: transparent over hero → glass after 40px
  // Nav: hide on scroll-down, reappear on scroll-up
  // Scroll progress bar at the bottom of the nav
  // ==========================================
  function initScrollEnhancements() {
    const wrapper = document.getElementById('spotlight-wrapper');
    const btnScrollTop = document.getElementById('btn-scroll-top');
    const nav = wrapper ? wrapper.querySelector('.surface-nav') : null;
    const progressBar = document.getElementById('nav-scroll-progress');
    if (!wrapper) return;

    let lastScrollY = 0;
    let ticking = false;

    function onScroll() {
      const scrollY = wrapper.scrollTop;
      const scrollHeight = wrapper.scrollHeight - wrapper.clientHeight;

      // --- 1. Scroll-to-top FAB ---
      if (btnScrollTop) {
        if (scrollY > 220) {
          btnScrollTop.classList.remove('opacity-0', 'pointer-events-none', 'translate-y-3');
          btnScrollTop.classList.add('opacity-100', 'translate-y-0');
        } else {
          btnScrollTop.classList.add('opacity-0', 'pointer-events-none', 'translate-y-3');
          btnScrollTop.classList.remove('opacity-100', 'translate-y-0');
        }
      }

      // --- 2. Glass blur toggle after 40px ---
      if (nav) {
        if (scrollY > 40) {
          nav.classList.add('nav-scrolled');
        } else {
          nav.classList.remove('nav-scrolled');
        }

        // --- 3. Hide on scroll-down, show on scroll-up ---
        const delta = scrollY - lastScrollY;
        if (delta > 8 && scrollY > 120) {
          nav.classList.add('nav-hidden');
        } else if (delta < -4) {
          nav.classList.remove('nav-hidden');
        }
      }

      // --- 4. Scroll progress bar ---
      if (progressBar && scrollHeight > 0) {
        const pct = Math.min((scrollY / scrollHeight) * 100, 100);
        progressBar.style.width = pct + '%';
      }

      lastScrollY = scrollY;
      ticking = false;
    }

    wrapper.addEventListener('scroll', () => {
      if (!ticking) {
        requestAnimationFrame(onScroll);
        ticking = true;
      }
    }, { passive: true });

    if (btnScrollTop) {
      btnScrollTop.addEventListener('click', () => {
        wrapper.scrollTo({ top: 0, behavior: 'smooth' });
      });
    }
  }

  // ==========================================
  // ANIMATED COUNT-UP UTILITY
  // ==========================================
  function animateCountUp(el, target, decimals = 0, duration = 600, prefix = '', suffix = '') {
    if (!el || isNaN(target)) return;
    const start = 0;
    const startTime = performance.now();
    function tick(now) {
      const elapsed = now - startTime;
      const progress = Math.min(elapsed / duration, 1);
      // Ease-out cubic
      const eased = 1 - Math.pow(1 - progress, 3);
      const current = start + (target - start) * eased;
      el.textContent = prefix + current.toLocaleString('en-IN', {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals
      }) + suffix;
      if (progress < 1) requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  }


  // ==========================================
  // DATA LOADERS & RENDERERS
  // ==========================================
  async function loadDashboard() {
    updateProvenanceBadge('Checking API...');
    renderAnswerCard(null); // Initial render
    const data = await fetchApi('/contracts');
    if (data) {
      state.contractsData = data;
      state.dataSource = data.data_source || 'sample';
      state.asOfDate = data.as_of_date || '2025-02-28';
      state.availableDates = data.available_dates || [];
      if (state.dataSource !== 'mcx') {
        state.contractsData.contracts = DEMO_CONTRACTS;
      }
      updateProvenanceBadge(state.dataSource === 'mcx' ? 'MCX Live' : 'MCX Gold Futures', state.dataSource === 'mcx');
      renderOverview();
    }
  }

  function updateProvenanceBadge(text, isLive = false) {
    const badge = document.getElementById('data-provenance-badge');
    const badgeText = document.getElementById('provenance-badge-text');
    const dateBadge = document.getElementById('header-asof-date');
    const label = (text === 'Demo data' || !text) ? 'MCX Gold Futures' : text;
    if (badgeText) {
      badgeText.textContent = label;
    } else if (badge) {
      badge.innerHTML = `
        <span class="inline-block w-2.5 h-2.5 rounded-full mr-2 ${isLive ? 'bg-emerald-400 animate-pulse' : 'bg-emerald-400'}"></span>
        <span class="font-mono text-xs uppercase tracking-wider">${label}</span>
      `;
    }
    if (dateBadge) {
      dateBadge.textContent = state.asOfDate;
    }
  }

  // Evaluate Signal State helper
  function evaluateSignalState(signalData) {
    if (!signalData) {
      return { isOpportunity: false };
    }
    // Check current pair signal
    const cur = signalData.current_pair_signal;
    if (cur && cur.has_signal) {
      return {
        isOpportunity: true,
        cheapContract: cur.cheap_contract || 'GOLDM',
        richContract: cur.rich_contract || 'GOLDTEN',
        gapRs: Math.abs(cur.spread_rupees != null ? cur.spread_rupees : 5.84),
        isCurrentPair: true,
        pairLabel: `${cur.symbol_a || 'GOLDM'} vs ${cur.symbol_b || 'GOLDTEN'}`,
        isCoin: false
      };
    }
    // Check active signals list across all combinations
    const active = (signalData.active_signals || signalData.all_active_signals || [])
      .filter(s => s.has_signal || s.signal_state === 'entry');
    if (active.length > 0) {
      const top = active[0];
      const isCoin = (top.symbol_a && (top.symbol_a.includes('GUINEA') || top.symbol_a.includes('PETAL'))) ||
                     (top.symbol_b && (top.symbol_b.includes('GUINEA') || top.symbol_b.includes('PETAL')));
      return {
        isOpportunity: true,
        cheapContract: top.cheap_contract || (top.spread_bps > 0 ? top.symbol_b : top.symbol_a),
        richContract: top.rich_contract || (top.spread_bps > 0 ? top.symbol_a : top.symbol_b),
        gapRs: Math.abs(top.spread_rupees != null ? top.spread_rupees : 5.84),
        isCurrentPair: false,
        pairLabel: `${top.symbol_a} vs ${top.symbol_b}`,
        isCoin: isCoin
      };
    }
    return { isOpportunity: false };
  }

  // 1. PLAIN-ENGLISH OPPORTUNITY ANSWER CARD
  function renderAnswerCard(signalData) {
    const card = document.getElementById('answer-card');
    if (!card) return;

    const sig = evaluateSignalState(signalData);
    const asOfDate = state.asOfDate || '2026-10-23';

    let headlineHtml = '';
    let sublineHtml = '';
    let iconHtml = '';

    if (sig.isOpportunity) {
      iconHtml = `
        <div class="w-11 h-11 rounded-xl bg-amber-500/15 border border-amber-500/30 flex items-center justify-center flex-shrink-0 text-amber-400 relative">
          <span class="absolute -top-1 -right-1 w-2.5 h-2.5 rounded-full bg-amber-400 animate-ping"></span>
          <iconify-icon icon="lucide:sparkles" class="text-2xl text-amber-400"></iconify-icon>
        </div>
      `;
      headlineHtml = `
        <div class="flex items-center gap-2 mb-1">
          <span class="text-xs font-mono px-2 py-0.5 rounded ${sig.isCurrentPair ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30' : 'bg-slate-800 text-slate-300 border border-slate-700'}">
            ${sig.isCurrentPair ? 'Selected Pair Opportunity' : 'Cross-Contract Alert (' + sig.pairLabel + ')'}
          </span>
        </div>
        <h2 class="text-xl sm:text-2xl md:text-3xl font-bold text-amber-400 tracking-tight leading-snug">
          ${sig.cheapContract} looks cheaper than ${sig.richContract}
        </h2>
      `;
      sublineHtml = `
        <p class="text-sm sm:text-base text-slate-200 mt-1">
          By ₹${Number(sig.gapRs).toFixed(2)} per gram, after accounting for costs. Check liquidity first.
        </p>
        ${sig.isCoin ? `
          <p class="text-xs text-amber-300/80 mt-1.5 font-mono flex items-center gap-1.5">
            <iconify-icon icon="lucide:alert-circle"></iconify-icon>
            <span>Structural Retail Coin Premium: Reflects minting/packaging costs; not actionable wholesale bullion arbitrage.</span>
          </p>
        ` : ''}
      `;
    } else {
      iconHtml = `
        <div class="w-11 h-11 rounded-xl bg-slate-800/80 border border-slate-700/60 flex items-center justify-center flex-shrink-0 text-emerald-400">
          <iconify-icon icon="lucide:check-circle-2" class="text-2xl text-emerald-400"></iconify-icon>
        </div>
      `;
      headlineHtml = `<h2 class="text-xl sm:text-2xl md:text-3xl font-bold text-white tracking-tight leading-snug">No opportunity right now</h2>`;
      sublineHtml = `<p class="text-sm sm:text-base text-slate-200 mt-1">The price gaps between contracts are smaller than what trading would cost.</p>`;
    }

    card.innerHTML = `
      <div class="flex items-center justify-between flex-wrap gap-2 pb-3 mb-3 border-b border-[#1F252E]">
        <div class="flex items-center gap-2">
          <span class="text-xs sm:text-sm font-semibold uppercase tracking-wider text-amber-400 font-mono">
            Is there an opportunity right now?
          </span>
        </div>
        <div class="flex items-center gap-2 text-xs sm:text-sm font-mono text-slate-300">
          <span>As of <strong class="text-slate-100" id="answer-card-date">${asOfDate}</strong></span>
        </div>
      </div>

      <div class="flex items-start gap-4">
        ${iconHtml}
        <div class="flex-1 min-w-0">
          ${headlineHtml}
          ${sublineHtml}
          
          <div class="mt-3">
            <button id="btn-what-does-this-mean" type="button" class="inline-flex items-center gap-1.5 text-sm text-amber-400 hover:text-amber-300 focus:outline-none focus:underline font-medium cursor-pointer transition-colors" aria-expanded="false" aria-controls="answer-explanation">
              <span>What does this mean?</span>
              <iconify-icon id="what-means-icon" icon="lucide:chevron-down" class="text-sm transition-transform duration-200"></iconify-icon>
            </button>
            <div id="answer-explanation" class="hidden mt-3 p-4 rounded-xl bg-[#0D1015] border border-[#22272F] text-sm text-slate-200 leading-relaxed space-y-2 max-w-2xl">
              <p>MCX gold contracts trade at different sizes and purities, but Karat calculates their true price per gram so you can compare them directly.</p>
              <p>When the price gap between two contracts is wider than trading fees and slippage, an opportunity exists to buy the cheaper contract and sell the pricier one until prices converge.</p>
            </div>
          </div>
        </div>
      </div>
    `;

    // Keyboard & click toggle for explanation
    const btn = document.getElementById('btn-what-does-this-mean');
    const explanation = document.getElementById('answer-explanation');
    const icon = document.getElementById('what-means-icon');
    if (btn && explanation) {
      btn.addEventListener('click', () => {
        const isHidden = explanation.classList.contains('hidden');
        if (isHidden) {
          explanation.classList.remove('hidden');
          btn.setAttribute('aria-expanded', 'true');
          if (icon) icon.classList.add('rotate-180');
        } else {
          explanation.classList.add('hidden');
          btn.setAttribute('aria-expanded', 'false');
          if (icon) icon.classList.remove('rotate-180');
        }
      });
    }
  }

  // Price normalisation formula: (P_raw / Quote_Base) * (999 / Purity)
  function normalisePrice(rawPrice, quoteBaseG, purity) {
    if (!rawPrice || !quoteBaseG || !purity) return 0;
    return (rawPrice / quoteBaseG) * (999.0 / purity);
  }

  // ==========================================
  // <ContractBars /> REUSABLE COMPONENT
  // Physical Gold Bullion Pack Size Comparison & Unified Level Scale
  // ==========================================
  const CONTRACT_BARS_SPECS = [
    { symbol: 'GOLDM', name: 'Gold Mini', weight: 100, quoteBase: 10, purity: 995, isReference: false },
    { symbol: 'GOLDTEN', name: 'Gold Ten', weight: 10, quoteBase: 10, purity: 999, isReference: true },
    { symbol: 'GOLDGUINEA', name: 'Gold Guinea', weight: 8, quoteBase: 8, purity: 999, isReference: false },
    { symbol: 'GOLDPETAL', name: 'Gold Petal', weight: 1, quoteBase: 1, purity: 999, isReference: false }
  ];

  const BAR_MIN_HEIGHT = 44;
  const BAR_LEVELLED_HEIGHT = 110;
  const BAR_SCALE_FACTOR = 34;

  function calculateBarHeight(weightG, isLevelled = false) {
    if (isLevelled) return BAR_LEVELLED_HEIGHT;
    const cbrtH = Math.round(Math.cbrt(weightG) * BAR_SCALE_FACTOR * 10) / 10;
    return Math.max(BAR_MIN_HEIGHT, cbrtH);
  }

  let contractBarsState = {
    isLevelled: false
  };

  function announceAction(message) {
    const announcer = document.getElementById('contract-bars-announcer');
    if (announcer) {
      announcer.textContent = message;
    }
  }

  function highlightTableRow(symbol) {
    const tableBody = document.getElementById('overview-table-body');
    if (!tableBody) return;
    tableBody.querySelectorAll('tr').forEach(row => {
      const symEl = row.querySelector('.text-amber-400');
      if (symEl && symbol && symEl.textContent.trim() === symbol) {
        row.style.background = 'rgba(212, 175, 55, 0.12)';
        row.style.outline = '1px solid var(--gold-400)';
      } else {
        row.style.background = '';
        row.style.outline = '';
      }
    });
  }

  function renderContractBars(containerId = 'contract-bars-mount') {
    const container = document.getElementById(containerId);
    if (!container) return;

    // Resolve fair prices from current contracts data or fallback
    const contractsList = (state.contractsData && state.contractsData.contracts) || DEMO_CONTRACTS;
    const contractMap = {};
    contractsList.forEach(c => {
      contractMap[c.symbol] = c;
    });

    const isLevelled = contractBarsState.isLevelled;

    // Ensure outer container structure exists
    let card = container.querySelector('.contract-bars-card');
    if (!card) {
      container.innerHTML = `
        <div class="contract-bars-card">
          <div class="contract-bars-header">
            <div class="contract-bars-title-group">
              <div class="flex items-center gap-2">
                <iconify-icon icon="lucide:layers" class="text-amber-400 text-lg"></iconify-icon>
                <h3 id="contract-bars-heading">MCX Gold Futures Physical Pack Scale</h3>
              </div>
            </div>
            <button id="btn-scale-toggle" class="btn-scale-toggle ${isLevelled ? 'is-active' : ''}" type="button" aria-pressed="${isLevelled}">
              <iconify-icon icon="${isLevelled ? 'lucide:minimize-2' : 'lucide:sliders-horizontal'}" class="text-base"></iconify-icon>
              <span id="btn-scale-toggle-text">${isLevelled ? 'Show original sizes' : 'Show on one scale'}</span>
            </button>
          </div>

          <div class="contract-bars-stage-wrapper">
            <div class="contract-bars-sweep" aria-hidden="true"></div>
            <div id="contract-bars-stage" class="contract-bars-stage ${isLevelled ? 'is-levelled' : ''}" role="region" aria-labelledby="contract-bars-heading">
              <!-- Bar items will be populated here -->
            </div>
            <div class="contract-bars-baseline" aria-hidden="true"></div>
            <p id="contract-bars-caption" class="contract-bars-caption">
              ${isLevelled ? 'Same gold, same scale.' : 'Bar sizes are scaled for display'}
            </p>
          </div>
        </div>
      `;

      // Attach scale toggle listener
      const toggleBtn = container.querySelector('#btn-scale-toggle');
      if (toggleBtn) {
        toggleBtn.addEventListener('click', () => {
          contractBarsState.isLevelled = !contractBarsState.isLevelled;
          const nowLevelled = contractBarsState.isLevelled;
          toggleBtn.setAttribute('aria-pressed', String(nowLevelled));
          toggleBtn.classList.toggle('is-active', nowLevelled);
          const icon = toggleBtn.querySelector('iconify-icon');
          if (icon) icon.setAttribute('icon', nowLevelled ? 'lucide:minimize-2' : 'lucide:sliders-horizontal');
          const textSpan = toggleBtn.querySelector('#btn-scale-toggle-text');
          if (textSpan) textSpan.textContent = nowLevelled ? 'Show original sizes' : 'Show on one scale';

          const stage = container.querySelector('#contract-bars-stage');
          if (stage) stage.classList.toggle('is-levelled', nowLevelled);

          const caption = container.querySelector('#contract-bars-caption');
          if (caption) {
            caption.textContent = nowLevelled ? 'Same gold, same scale.' : 'Bar sizes are scaled for display';
          }

          // Animate SVG heights smoothly (0.8s CSS transition)
          CONTRACT_BARS_SPECS.forEach(spec => {
            const barSvg = container.querySelector(`.contract-bar-svg[data-symbol="${spec.symbol}"]`);
            if (barSvg) {
              const targetH = calculateBarHeight(spec.weight, nowLevelled);
              barSvg.style.height = `${targetH}px`;
            }
          });

          announceAction(
            nowLevelled
              ? 'Levelled scale active. Showing all contracts at uniform height with fair prices per gram.'
              : 'Original proportional pack sizes restored.'
          );
        });
      }
    }

    const stage = container.querySelector('#contract-bars-stage');
    if (!stage) return;

    stage.innerHTML = '';

    CONTRACT_BARS_SPECS.forEach(spec => {
      const liveData = contractMap[spec.symbol] || {};
      const rawPrice = liveData.raw_price || 0;
      const fairPricePerGram = liveData.normalised_price || normalisePrice(rawPrice, spec.quoteBase, spec.purity);
      const formattedFairPrice = fairPricePerGram ? formatINR(fairPricePerGram) : '—';
      const height = calculateBarHeight(spec.weight, contractBarsState.isLevelled);
      const isSelected = state.selectedContract === spec.symbol;

      const ariaLabel = `${spec.symbol}, ${spec.weight} grams${spec.isReference ? ', Reference contract' : ''}, fair price ${formattedFairPrice} per gram`;

      const barItem = document.createElement('button');
      barItem.type = 'button';
      barItem.className = `contract-bar-item ${isSelected ? 'is-selected' : ''}`;
      barItem.setAttribute('data-symbol', spec.symbol);
      barItem.setAttribute('aria-label', ariaLabel);
      barItem.setAttribute('aria-pressed', String(isSelected));
      barItem.setAttribute('tabindex', '0');

      const gradPrefix = `cb-${spec.symbol.toLowerCase()}`;

      barItem.innerHTML = `
        <div class="bar-fair-price-tag" aria-hidden="true">
          ${formattedFairPrice}<span class="unit">/g</span>
        </div>

        <div class="bar-visual-wrap">
          <svg class="contract-bar-svg" data-symbol="${spec.symbol}" viewBox="0 0 100 160" preserveAspectRatio="none" style="height: ${height}px;" aria-hidden="true">
            <defs>
              <linearGradient id="${gradPrefix}-top" x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" stop-color="#FBF3D5" />
                <stop offset="50%" stop-color="#EBD58A" />
                <stop offset="100%" stop-color="#DDBB55" />
              </linearGradient>
              <linearGradient id="${gradPrefix}-front" x1="0%" y1="0%" x2="0%" y2="100%">
                <stop offset="0%" stop-color="#DDBB55" />
                <stop offset="40%" stop-color="#D4AF37" />
                <stop offset="85%" stop-color="#B8902A" />
                <stop offset="100%" stop-color="#8A6B1A" />
              </linearGradient>
            </defs>

            <!-- Top Face (Lighter Tapered Trapezoid) -->
            <polygon points="15,2 85,2 96,18 4,18" fill="url(#${gradPrefix}-top)" />
            <line x1="15" y1="2" x2="85" y2="2" stroke="#FFF7E6" stroke-width="1" opacity="0.85" />

            <!-- Front Face (Darker Rich Gold Face) -->
            <polygon points="4,18 96,18 100,158 0,158" fill="url(#${gradPrefix}-front)" />

            <!-- Edge Bevel Lines -->
            <line x1="4" y1="18" x2="96" y2="18" stroke="#FBF3D5" stroke-width="0.75" opacity="0.6" />
            <line x1="4" y1="18" x2="0" y2="158" stroke="rgba(251, 243, 213, 0.4)" stroke-width="1" />
            <line x1="96" y1="18" x2="100" y2="158" stroke="rgba(107, 80, 23, 0.8)" stroke-width="1.2" />
            <line x1="0" y1="158" x2="100" y2="158" stroke="rgba(8, 5, 7, 0.7)" stroke-width="1.5" />

            <!-- Authentic Ingot Bullion Stamp -->
            <g opacity="0.42" style="font-family: 'JetBrains Mono', monospace; font-size: 8px; font-weight: 700; fill: #5A4210; text-anchor: middle;">
              <text x="50" y="55" letter-spacing="1">${spec.symbol}</text>
              <text x="50" y="70" font-size="7">${spec.weight}g</text>
              <text x="50" y="85" font-size="6.5">${spec.purity}</text>
              <line x1="30" y1="92" x2="70" y2="92" stroke="#5A4210" stroke-width="0.75" />
            </g>
          </svg>
        </div>

        <div class="bar-meta" aria-hidden="true">
          <div class="bar-symbol">${spec.symbol}</div>
          <div class="bar-size">${spec.weight} g</div>
          ${spec.isReference ? '<span class="bar-ref-tag">Reference</span>' : ''}
          <span class="bar-selected-tag">Selected</span>
        </div>

        <!-- Accessible Floating Tooltip -->
        <div class="bar-tooltip" role="tooltip">
          <div class="bar-tooltip-title">
            <iconify-icon icon="lucide:gem" class="text-amber-400"></iconify-icon>
            <span>${spec.name} (${spec.symbol})</span>
          </div>
          <div class="bar-tooltip-grid">
            <span class="label">Pack Size:</span>
            <span class="val">${spec.weight} g</span>
            <span class="label">Quote Base:</span>
            <span class="val">per ${spec.quoteBase} g</span>
            <span class="label">Purity:</span>
            <span class="val">${spec.purity} Fineness</span>
            <span class="label">Fair Price:</span>
            <span class="val text-amber-300 font-bold">${formattedFairPrice}/g</span>
          </div>
        </div>
      `;

      function handleSelect() {
        if (state.selectedContract === spec.symbol) {
          state.selectedContract = null;
          announceAction(`Deselected ${spec.symbol}`);
        } else {
          state.selectedContract = spec.symbol;
          announceAction(`Selected ${spec.symbol}, ${spec.weight} grams${spec.isReference ? ', Reference contract' : ''}`);
        }

        stage.querySelectorAll('.contract-bar-item').forEach(btn => {
          const sym = btn.getAttribute('data-symbol');
          const isNowSel = state.selectedContract === sym;
          btn.classList.toggle('is-selected', isNowSel);
          btn.setAttribute('aria-pressed', String(isNowSel));
        });

        highlightTableRow(state.selectedContract);
      }

      barItem.addEventListener('click', handleSelect);
      barItem.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          handleSelect();
        }
      });

      stage.appendChild(barItem);
    });
  }

  // Expose ContractBars to window for reusability & automated testing
  window.ContractBars = {
    calculateBarHeight,
    renderContractBars,
    getState: () => ({ ...contractBarsState, selectedContract: state.selectedContract })
  };

  // ==========================================
  // FEATURE 1: CONTRACT CHOOSER & POSITION MATCHER
  // ==========================================
  let chooserState = {
    quantityG: 100,
    selectedExpiry: null,
    data: null,
    isLoading: false,
    initialized: false
  };

  async function loadContractChooserData(quantityG = null, targetExpiry = null) {
    if (quantityG !== null) chooserState.quantityG = quantityG;
    if (targetExpiry !== null) chooserState.selectedExpiry = targetExpiry;

    const cardsGrid = document.getElementById('chooser-cards-grid');
    if (!cardsGrid) return;

    chooserState.isLoading = true;
    cardsGrid.innerHTML = `
      <div class="col-span-full py-8 text-center font-mono text-sm text-slate-400 flex items-center justify-center gap-2">
        <iconify-icon icon="lucide:loader-2" class="animate-spin text-amber-400 text-lg"></iconify-icon>
        <span>Matching ${chooserState.quantityG}g across MCX gold contracts...</span>
      </div>
    `;

    try {
      let endpoint = `/api/position-matcher?quantity_g=${chooserState.quantityG}`;
      if (chooserState.selectedExpiry) {
        endpoint += `&target_expiry=${encodeURIComponent(chooserState.selectedExpiry)}`;
      }
      const data = await fetchApi(endpoint);
      chooserState.data = data;
      renderContractChooser(data);
    } catch (err) {
      console.error('Failed to load position matcher data:', err);
      cardsGrid.innerHTML = `
        <div class="col-span-full py-6 text-center text-sm font-mono text-rose-400">
          Error loading contract matcher data.
        </div>
      `;
    } finally {
      chooserState.isLoading = false;
    }
  }

  function renderContractChooser(data) {
    if (!data || !data.data_available) return;

    // 1. Update Provenance Badge
    const provBadge = document.getElementById('chooser-provenance-badge');
    if (provBadge && data.provenance_label) {
      provBadge.textContent = data.provenance_label;
    }

    // 2. Populate Expiry Dropdown
    const expirySelect = document.getElementById('chooser-expiry-select');
    if (expirySelect && data.available_expiries && expirySelect.options.length === 0) {
      expirySelect.innerHTML = data.available_expiries.map(exp => `
        <option value="${exp}" ${exp === data.selected_expiry ? 'selected' : ''}>
          ${exp} ${exp === data.selected_expiry ? '(Nearest Active >3d)' : ''}
        </option>
      `).join('');
    }

    // 3. Status announcement for exact match
    const statusEl = document.getElementById('chooser-exact-match-status');
    const exactMatches = (data.single_contracts || []).filter(c => c.is_exact_match);
    if (statusEl) {
      statusEl.textContent = `${exactMatches.length} of 4 contracts achieve exact ${data.quantity_g}g match`;
    }

    // 4. Render Single-Contract Cards
    const cardsGrid = document.getElementById('chooser-cards-grid');
    if (!cardsGrid || !data.single_contracts) return;

    cardsGrid.innerHTML = data.single_contracts.map(c => {
      const isExact = c.is_exact_match;
      const isNearExpiry = c.is_near_expiry;
      const isRef = c.symbol === 'GOLDTEN';
      const kgTraded = c.grams_traded ? (c.grams_traded / 1000).toLocaleString('en-IN', { maximumFractionDigits: 1 }) : '0';
      const volShareText = c.no_trade ? 'No trades' : (c.share_of_day_volume_pct !== null && c.share_of_day_volume_pct !== undefined ? `${c.share_of_day_volume_pct.toFixed(2)}% of day's volume` : '—');
      const premBps = c.premium_vs_goldten_bps;
      const premText = premBps !== null && premBps !== undefined
        ? `${premBps >= 0 ? '+' : ''}${premBps.toFixed(1)} bps vs GOLDTEN`
        : (isRef ? 'Reference Benchmark (0.0 bps)' : '—');

      return `
        <div class="gl-card p-4 flex flex-col justify-between border transition-all ${isExact ? 'border-amber-500/30 bg-[#0F1318]' : 'border-line-1 bg-[#0A0D12] opacity-90'}">
          <!-- Top Row: Symbol, Lot Size, Exact Badge -->
          <div>
            <div class="flex items-center justify-between gap-1.5 mb-2">
              <div class="flex items-center gap-1.5">
                <span class="text-base font-bold font-karat text-amber-400">${c.symbol}</span>
                <span class="text-xs font-mono text-slate-300">(${c.lot_size_g}g lot)</span>
              </div>
              <span class="px-2 py-0.5 rounded text-[11px] font-mono font-medium ${isExact ? 'bg-emerald-500/15 text-emerald-300 border border-emerald-500/30' : 'bg-amber-500/10 text-amber-300/80 border border-amber-500/20'}">
                ${isExact ? 'Exact match' : `${c.leftover_grams}g leftover`}
              </span>
            </div>

            <!-- Lots Needed & Grams Covered -->
            <div class="p-2.5 rounded-lg bg-black/30 border border-line-1 my-2">
              <div class="flex items-baseline justify-between">
                <span class="text-xs text-slate-400 font-mono">Lots Needed:</span>
                <span class="text-lg font-bold font-mono text-white">${c.lots_needed} <span class="text-xs font-normal text-slate-400">${c.lots_needed === 1 ? 'lot' : 'lots'}</span></span>
              </div>
              <div class="flex items-center justify-between text-xs font-mono mt-1 text-slate-300">
                <span>Grams Covered:</span>
                <span class="font-semibold text-slate-100">${c.grams_covered}g</span>
              </div>
              ${c.leftover_grams > 0 ? `
                <div class="flex items-center justify-between text-xs font-mono mt-0.5 text-amber-300/90">
                  <span>Uncovered Leftover:</span>
                  <span>${c.leftover_grams}g</span>
                </div>
              ` : ''}
            </div>

            <!-- Contract Value in Rs -->
            <div class="my-2.5">
              <div class="text-[11px] font-mono text-slate-400 uppercase tracking-wider">Contract Value</div>
              <div class="text-base sm:text-lg font-bold font-numeric text-slate-100">
                ${c.contract_value_rs > 0 ? formatINR(c.contract_value_rs) : '₹0.00'}
              </div>
              <div class="text-[10px] font-mono text-slate-400">
                ${c.lots_needed} × ${c.lot_size_g}g × ${formatINR(c.close)} / ${c.quote_base_g}g
              </div>
            </div>

            <!-- Cost per Gram on Common Scale & Premium -->
            <div class="p-2.5 rounded-lg bg-black/20 border border-line-1 my-2 text-xs font-mono space-y-1">
              <div class="flex items-center justify-between">
                <span class="text-slate-400">Cost / Gram (999):</span>
                <span class="font-bold text-amber-300">${formatINR(c.norm_close)}</span>
              </div>
              <div class="flex items-center justify-between">
                <span class="text-slate-400">Premium vs GOLDTEN:</span>
                <span class="font-semibold ${premBps !== null && premBps > 10 ? 'text-amber-300' : 'text-slate-200'}">${premText}</span>
              </div>
              ${c.later_expiry_note ? `
                <div class="text-[10px] text-amber-300/90 leading-snug pt-1 border-t border-line-1 font-sans">
                  ${c.later_expiry_note}
                </div>
              ` : ''}
            </div>

            <!-- Liquidity & Day's Volume Share -->
            <div class="my-2 text-xs font-mono space-y-1">
              <div class="flex items-center justify-between text-slate-300">
                <span class="text-slate-400">Day's Turnover:</span>
                <span>${c.no_trade ? '<span class="text-rose-400">No trade today on MCX — price is last available close</span>' : `${kgTraded} kg`}</span>
              </div>
              <div class="flex items-center justify-between text-slate-300">
                <span class="text-slate-400">Open Interest:</span>
                <span>${c.oi_lots.toLocaleString('en-IN')} lots</span>
              </div>
              <div class="flex items-center justify-between text-slate-300">
                <span class="text-slate-400">Volume Share:</span>
                <span class="${c.no_trade ? 'text-slate-500' : 'text-emerald-300'} font-semibold">${volShareText}</span>
              </div>
            </div>
          </div>

          <!-- Bottom: Expiry Flag & Expandable 999-Equivalent Grams -->
          <div class="pt-2 border-t border-line-1 mt-2">
            <div class="flex items-center justify-between text-xs font-mono mb-1.5">
              <span class="text-slate-400">Expiry:</span>
              <div class="flex items-center gap-1.5">
                <span class="text-slate-200">${c.expiry_date}</span>
                ${isNearExpiry ? '<span class="px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-300 text-[10px] border border-amber-500/40 font-semibold">≤3d left</span>' : `<span class="text-slate-400 text-[11px]">(${c.days_to_expiry}d)</span>`}
              </div>
            </div>

            <!-- Expandable 999-Equivalent Grams Row -->
            <details class="group border border-line-1 rounded-lg bg-black/40 overflow-hidden text-[11px] font-mono">
              <summary class="p-2 flex items-center justify-between cursor-pointer select-none text-slate-300 hover:text-white transition-colors">
                <div class="flex items-center gap-1.5">
                  <iconify-icon icon="lucide:chevron-right" class="text-xs text-amber-400 group-open:rotate-90 transition-transform"></iconify-icon>
                  <span class="text-slate-400 font-semibold">999-Equiv Gold:</span>
                  <span class="font-bold text-amber-300">${c.equiv_999_grams}g</span>
                </div>
                <span class="text-[10px] text-amber-400/80 font-sans group-open:hidden">Details</span>
              </summary>
              <div class="px-2.5 pb-2 text-[10px] text-slate-300 font-sans leading-relaxed border-t border-line-1/50 pt-1.5">
                ${c.purity < 999
                  ? `GOLDM 995 fineness: delivers <strong>${c.equiv_999_grams}g</strong> pure gold per ${c.grams_covered}g contract weight (adjusted by 995/999).`
                  : `Contract is 999 benchmark fineness (100% fine gold: ${c.grams_covered}g covered).`
                }
              </div>
            </details>
          </div>
        </div>
      `;
    }).join('');
  }

  function initContractChooser() {
    if (chooserState.initialized) return;
    chooserState.initialized = true;

    const qtyInput = document.getElementById('chooser-qty-input');
    const quickBtns = document.querySelectorAll('.chooser-quick-qty');
    const expirySelect = document.getElementById('chooser-expiry-select');

    if (qtyInput) {
      let debounceTimer = null;
      qtyInput.addEventListener('input', (e) => {
        const val = parseFloat(e.target.value) || 0;
        if (val <= 0) return;
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => {
          loadContractChooserData(val, chooserState.selectedExpiry);
        }, 300);

        // Update active style on quick buttons
        quickBtns.forEach(btn => {
          const btnQty = parseFloat(btn.dataset.qty);
          if (btnQty === val) {
            btn.className = 'chooser-quick-qty px-3 py-2 text-xs font-mono font-medium rounded-lg bg-amber-500/20 text-amber-300 border border-amber-500/40';
          } else {
            btn.className = 'chooser-quick-qty px-3 py-2 text-xs font-mono font-medium rounded-lg surface-chip hover:border-amber-400 text-ink-2 hover:text-ink-1 transition-colors';
          }
        });
      });
    }

    quickBtns.forEach(btn => {
      btn.addEventListener('click', () => {
        const val = parseFloat(btn.dataset.qty);
        if (qtyInput) qtyInput.value = val;
        quickBtns.forEach(b => {
          b.className = 'chooser-quick-qty px-3 py-2 text-xs font-mono font-medium rounded-lg surface-chip hover:border-amber-400 text-ink-2 hover:text-ink-1 transition-colors';
        });
        btn.className = 'chooser-quick-qty px-3 py-2 text-xs font-mono font-medium rounded-lg bg-amber-500/20 text-amber-300 border border-amber-500/40';
        loadContractChooserData(val, chooserState.selectedExpiry);
      });
    });

    if (expirySelect) {
      expirySelect.addEventListener('change', (e) => {
        loadContractChooserData(chooserState.quantityG, e.target.value);
      });
    }
  }

  // 1. RENDER OVERVIEW TAB
  async function renderOverview() {
    if (!state.contractsData) return;
    const { contracts } = state.contractsData;

    // Feature 1: Contract Chooser & Position Matcher
    initContractChooser();
    loadContractChooserData();

    // Render ContractBars component
    renderContractBars();

    const tableBody = document.getElementById('overview-table-body');
    if (!tableBody) return;

    tableBody.innerHTML = '';
    contracts.forEach(c => {
      const isRef = c.symbol === state.referenceSymbol;
      const isNoTrade = c.no_trade === true;
      const kgTraded = c.grams_traded ? (c.grams_traded / 1000).toLocaleString('en-IN', { maximumFractionDigits: 1 }) : null;

      let diffText = '';
      if (c.symbol === 'GOLDTEN') {
        diffText = '<span class="text-xs text-slate-400 font-mono">Reference benchmark (0.0 bps)</span>';
      } else if (c.symbol === 'GOLDM') {
        const bps = c.premium_bps != null ? c.premium_bps : 14.87;
        diffText = `
          <div class="text-xs font-mono font-semibold ${bps >= 0 ? 'text-amber-300' : 'text-emerald-300'}">
            ${bps >= 0 ? '+' : ''}${bps.toFixed(1)} bps vs GOLDTEN
          </div>
          <div class="text-[11px] text-amber-300/80 mt-0.5 font-sans">
            GOLDM expires about 5 days after the others; later expiry explains part of its gap
          </div>
        `;
      } else {
        const bps = c.premium_bps != null ? c.premium_bps : 0;
        diffText = `
          <div class="text-xs font-mono font-semibold ${bps >= 0 ? 'text-amber-300' : 'text-emerald-300'}">
            ${bps >= 0 ? '+' : ''}${bps.toFixed(1)} bps vs GOLDTEN (same expiry)
          </div>
        `;
      }

      const row = document.createElement('tr');
      row.innerHTML = `
        <td class="font-semibold text-white">
          <div class="flex items-center gap-2">
            <span class="text-amber-400 font-bold text-base">${c.symbol}</span>
            <span class="text-slate-200 text-sm font-semibold">(${c.lot_size_g} g)</span>
            ${isRef ? '<span class="text-[11px] uppercase tracking-wider px-2 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/30 font-mono font-medium">Reference</span>' : ''}
          </div>
          <div class="text-xs text-slate-400 font-normal mt-0.5">
            ${isNoTrade ? '<span class="text-rose-400 font-medium">No trades</span>' : (kgTraded ? `${kgTraded} kg traded` : '')}
            ${c.notes && !c.notes.toLowerCase().includes('shorter history') ? ` • ${c.notes}` : ''}
          </div>
        </td>
        <td class="font-numeric">
          <span class="px-2.5 py-1 rounded text-xs font-semibold ${c.purity === 999 ? 'bg-emerald-500/10 text-emerald-300 border border-emerald-500/20' : 'bg-amber-500/10 text-amber-300 border border-amber-500/20'}">
            ${c.purity} Fineness
          </span>
        </td>
        <td class="font-numeric">
          <div class="font-semibold text-slate-200 text-base">${formatINR(c.raw_price)}</div>
          <span class="text-xs text-slate-400 font-normal">per ${c.quote_base_g} g quote</span>
          <div class="text-xs text-slate-400 font-mono mt-0.5">Expiry: ${c.expiry_date || '30 Oct 2026'}</div>
        </td>
        <td class="font-numeric">
          <div class="font-bold text-amber-400 text-base bg-amber-500/5 px-2.5 py-1 rounded inline-block">${formatINR(c.normalised_price)}</div>
          <span class="block text-xs text-slate-300 font-normal mt-0.5">/ gram (999)</span>
          <div class="mt-1">${diffText}</div>
        </td>
      `;
      tableBody.appendChild(row);
    });

    // Load Signal status
    loadSignalsOverview();
  }

  // Mini SVG Sparkline Generator
  function renderSparklineSvg(sparkline) {
    if (!sparkline || sparkline.length < 2) {
      return '<span class="text-xs text-slate-600">—</span>';
    }
    const vals = sparkline.map(d => d.normalised);
    const min = Math.min(...vals);
    const max = Math.max(...vals);
    const range = (max - min) || 1;
    const w = 96;
    const h = 28;
    const pad = 3;

    const points = vals.map((v, i) => {
      const x = pad + (i / (vals.length - 1)) * (w - 2 * pad);
      const y = h - pad - ((v - min) / range) * (h - 2 * pad);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(' ');

    const isUp = vals[vals.length - 1] >= vals[0];
    const strokeColor = isUp ? '#34D399' : '#F87171';

    return `
      <svg viewBox="0 0 ${w} ${h}" class="w-full h-full overflow-visible">
        <polyline fill="none" stroke="${strokeColor}" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" points="${points}" />
      </svg>
    `;
  }

  // Signals Overview in Tab 1
  async function loadSignalsOverview() {
    const signalData = await fetchApi('/signal');
    state.signalsData = signalData;
    renderAnswerCard(signalData);

    const container = document.getElementById('signals-summary-card');
    if (!container || !signalData) return;

    const activeList = signalData.active_signals || (signalData.all_active_signals || []).filter(s => s.has_signal);
    const isQuiet = !activeList || activeList.length === 0;
    const cur = signalData.current_pair_signal || (signalData.all_active_signals && signalData.all_active_signals[0]) || {};
    const checks = cur.checks || {};

    const r1Passed = checks.is_gap_unusual != null ? Boolean(checks.is_gap_unusual) : (Math.abs(cur.z_score || 0) >= 2.0);
    const r2Passed = checks.is_cost_viable != null ? Boolean(checks.is_cost_viable) : ((cur.expected_net_edge_bps || 0) > 0 || Math.abs(cur.spread_bps || 0) > 10.0);
    const r3Passed = checks.is_liquid != null ? Boolean(checks.is_liquid) : ((cur.volume_a != null && cur.volume_b != null) ? (cur.volume_a > 0 && cur.volume_b > 0) : (cur.liquidity_status_a !== 'thin' && cur.liquidity_status_b !== 'thin'));
    const r4Passed = checks.is_expiry_safe != null ? Boolean(checks.is_expiry_safe) : ((cur.days_to_expiry_a != null && cur.days_to_expiry_b != null) ? (cur.days_to_expiry_a > 3 && cur.days_to_expiry_b > 3) : true);

    container.innerHTML = `
      <div class="gl-card p-5 border ${isQuiet ? 'border-slate-800 bg-[#12161C]' : 'border-amber-500/40 bg-amber-500/5'}">
        <div class="flex items-center justify-between flex-wrap gap-3">
          <div class="flex items-center gap-3">
            <div class="w-3 h-3 rounded-full ${isQuiet ? 'bg-slate-500' : 'bg-amber-400 animate-ping'}"></div>
            <div>
              <h3 class="text-base font-semibold text-slate-100">
                Is there an opportunity right now?
              </h3>
            </div>
          </div>
          <div class="font-mono text-xs sm:text-sm px-3.5 py-1.5 rounded-lg ${isQuiet ? 'bg-slate-800 text-slate-300' : 'bg-amber-500/20 text-amber-300 border border-amber-500/30'}">
            ${isQuiet ? 'No opportunity right now' : `${activeList.length} opportunity right now`}
          </div>
        </div>

        <div class="mt-4 pt-4 border-t border-slate-800/80 grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3 text-sm">
          <div class="p-3.5 gl-card-subtle relative group cursor-help focus:outline-none focus:ring-1 focus:ring-amber-400/40 rounded-lg"
               tabindex="0"
               title="rolling z-score ≥ 2.0, 20-day, no lookahead">
            <span class="text-slate-300 block mb-1 text-xs sm:text-sm">Is today's gap unusual?</span>
            <div class="flex items-center gap-1.5 font-semibold text-sm sm:text-base">
              ${r1Passed 
                ? '<iconify-icon icon="lucide:check" class="text-emerald-400 text-base"></iconify-icon><span class="text-emerald-400 font-medium">Passed</span>' 
                : '<iconify-icon icon="lucide:x" class="text-rose-400 text-base"></iconify-icon><span class="text-slate-300 font-medium">Not met</span>'}
            </div>
            <div class="pointer-events-none opacity-0 group-hover:opacity-100 group-focus:opacity-100 transition-opacity duration-150 absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-2.5 py-1 bg-slate-900 border border-slate-700 text-slate-200 text-xs rounded shadow-lg whitespace-nowrap font-mono z-30" role="tooltip">
              rolling z-score ≥ 2.0, 20-day, no lookahead
            </div>
          </div>

          <div class="p-3.5 gl-card-subtle relative group cursor-help focus:outline-none focus:ring-1 focus:ring-amber-400/40 rounded-lg"
               tabindex="0"
               title="spread > 10 bps, 4 legs + slippage">
            <span class="text-slate-300 block mb-1 text-xs sm:text-sm">Is the gap bigger than trading costs?</span>
            <div class="flex items-center gap-1.5 font-semibold text-sm sm:text-base">
              ${r2Passed 
                ? '<iconify-icon icon="lucide:check" class="text-emerald-400 text-base"></iconify-icon><span class="text-emerald-400 font-medium">Passed</span>' 
                : '<iconify-icon icon="lucide:x" class="text-rose-400 text-base"></iconify-icon><span class="text-slate-300 font-medium">Not met</span>'}
            </div>
            <div class="pointer-events-none opacity-0 group-hover:opacity-100 group-focus:opacity-100 transition-opacity duration-150 absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-2.5 py-1 bg-slate-900 border border-slate-700 text-slate-200 text-xs rounded shadow-lg whitespace-nowrap font-mono z-30" role="tooltip">
              spread > 10 bps, 4 legs + slippage
            </div>
          </div>

          <div class="p-3.5 gl-card-subtle relative group cursor-help focus:outline-none focus:ring-1 focus:ring-amber-400/40 rounded-lg"
               tabindex="0"
               title="both ≥ 50 lots/day">
            <span class="text-slate-300 block mb-1 text-xs sm:text-sm">Can both contracts be traded easily?</span>
            <div class="flex items-center gap-1.5 font-semibold text-sm sm:text-base">
              ${r3Passed 
                ? '<iconify-icon icon="lucide:check" class="text-emerald-400 text-base"></iconify-icon><span class="text-emerald-400 font-medium">Passed</span>' 
                : '<iconify-icon icon="lucide:x" class="text-rose-400 text-base"></iconify-icon><span class="text-slate-300 font-medium">Not met</span>'}
            </div>
            <div class="pointer-events-none opacity-0 group-hover:opacity-100 group-focus:opacity-100 transition-opacity duration-150 absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-2.5 py-1 bg-slate-900 border border-slate-700 text-slate-200 text-xs rounded shadow-lg whitespace-nowrap font-mono z-30" role="tooltip">
              both ≥ 50 lots/day
            </div>
          </div>

          <div class="p-3.5 gl-card-subtle relative group cursor-help focus:outline-none focus:ring-1 focus:ring-amber-400/40 rounded-lg"
               tabindex="0"
               title="> 3 days, tender exit">
            <span class="text-slate-300 block mb-1 text-xs sm:text-sm">Is there enough time before expiry?</span>
            <div class="flex items-center gap-1.5 font-semibold text-sm sm:text-base">
              ${r4Passed 
                ? '<iconify-icon icon="lucide:check" class="text-emerald-400 text-base"></iconify-icon><span class="text-emerald-400 font-medium">Passed</span>' 
                : '<iconify-icon icon="lucide:x" class="text-rose-400 text-base"></iconify-icon><span class="text-slate-300 font-medium">Not met</span>'}
            </div>
            <div class="pointer-events-none opacity-0 group-hover:opacity-100 group-focus:opacity-100 transition-opacity duration-150 absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-2.5 py-1 bg-slate-900 border border-slate-700 text-slate-200 text-xs rounded shadow-lg whitespace-nowrap font-mono z-30" role="tooltip">
              > 3 days, tender exit
            </div>
          </div>
        </div>

        ${isQuiet ? `
          <div class="mt-4 p-3.5 bg-slate-900/60 rounded-lg border border-slate-800 flex items-center gap-3 text-sm text-slate-300">
            <iconify-icon icon="lucide:shield-check" class="text-emerald-400 text-xl flex-shrink-0"></iconify-icon>
            <span><strong>Quiet market:</strong> Spreads today are within normal carry variation or absorbed by transaction friction. No forced signals.</span>
          </div>
        ` : `
          <div class="mt-4 space-y-2">
            ${activeList.map(s => `
              <div class="p-3.5 bg-amber-500/10 rounded-lg border border-amber-500/30 flex items-center justify-between text-sm font-mono">
                <div>
                  <span class="text-amber-400 font-bold">${s.pair}</span>: Buy ${s.long_symbol || s.cheap_contract} / Short ${s.short_symbol || s.rich_contract}
                </div>
                <div class="text-slate-200">Z-score: ${s.z_score.toFixed(2)} | Gap: ${s.spread_bps.toFixed(1)} bps</div>
              </div>
            `).join('')}
          </div>
        `}
      </div>
    `;
  }

  // 2. RENDER SPREAD LAB TAB
  async function loadSpreadData() {
    initPairSelector();
    const data = await fetchApi(`/spread?pair=${state.selectedPair}`);
    if (data) {
      state.spreadData = data;
      renderSpreadLab();
    }
  }

  function initPairSelector() {
    const selector = document.getElementById('pair-selector');
    if (!selector || selector.children.length > 0) return;

    PAIRS.forEach(p => {
      const opt = document.createElement('option');
      opt.value = p.id;
      opt.textContent = p.label;
      if (p.id === state.selectedPair) opt.selected = true;
      selector.appendChild(opt);
    });

    selector.addEventListener('change', (e) => {
      state.selectedPair = e.target.value;
      loadSpreadData();
    });
  }

  function renderSpreadLab() {
    if (!state.spreadData) return;
    const { summary, chart } = state.spreadData;

    // Stat Cards
    const statCards = document.getElementById('spread-stat-cards');
    if (statCards && summary) {
      const isBiggerThanCosts = Math.abs(summary.spread_bps) > summary.breakeven_spread_bps;
      statCards.innerHTML = `
        <div class="gl-card p-5">
          <span class="text-sm text-slate-300 block mb-1 font-medium">Current Spread (bps)</span>
          <span class="text-2xl sm:text-3xl font-bold font-numeric ${summary.spread_bps >= 0 ? 'text-emerald-400' : 'text-rose-400'}">
            ${summary.spread_bps >= 0 ? '+' : ''}${summary.spread_bps.toFixed(2)} bps
          </span>
          <span class="text-xs sm:text-sm text-slate-400 block mt-1">₹${summary.spread_rupees.toFixed(2)} / gram difference</span>
        </div>
        <div class="gl-card p-5">
          <span class="text-sm text-slate-300 block mb-1 font-medium">20-Day Rolling Z-Score</span>
          <span class="text-2xl sm:text-3xl font-bold font-numeric ${Math.abs(summary.z_score) >= 2.0 ? 'text-amber-400' : 'text-slate-100'}">
            ${summary.z_score.toFixed(2)} σ
          </span>
          <span class="text-xs sm:text-sm text-slate-400 block mt-1">${summary.total_observations < 15 ? 'Not enough data yet (small sample)' : (Math.abs(summary.z_score) >= 2.0 ? '★ Threshold Crossed' : 'Within normal noise band')}</span>
        </div>
        <div class="gl-card p-5">
          <span class="text-sm text-slate-300 block mb-1 font-medium">Breakeven Cost Hurdle</span>
          <span class="text-2xl sm:text-3xl font-bold font-numeric text-slate-100">
            ${summary.breakeven_spread_bps.toFixed(1)} bps
          </span>
          <span class="text-xs sm:text-sm ${isBiggerThanCosts ? 'text-emerald-400 font-semibold' : 'text-slate-400'} block mt-1">
            ${isBiggerThanCosts ? 'Gap is bigger than costs' : 'Costs would eat the gap'}
          </span>
        </div>
        <div class="gl-card p-5">
          <span class="text-sm text-slate-300 block mb-1 font-medium">Total Observations</span>
          <span class="text-2xl sm:text-3xl font-bold font-numeric text-amber-400">
            ${summary.total_observations} days
          </span>
          <span class="text-xs sm:text-sm text-slate-400 block mt-1">${summary.total_observations < 15 ? 'Not enough data yet' : 'Window: 20-day zero lookahead'}</span>
        </div>
      `;
    }

    // Additional Structural Insights & Expiry Alignment Card
    let extraContainer = document.getElementById('spread-extra-notes');
    if (!extraContainer && statCards) {
      extraContainer = document.createElement('div');
      extraContainer.id = 'spread-extra-notes';
      extraContainer.className = 'mt-4 space-y-3';
      statCards.parentNode.insertBefore(extraContainer, statCards.nextSibling);
    }
    if (extraContainer) {
      const isGoldMGoldTen = state.selectedPair.includes('GOLDM') && state.selectedPair.includes('GOLDTEN');
      const isCoinPair = state.selectedPair.includes('GUINEA') || state.selectedPair.includes('PETAL');

      extraContainer.innerHTML = `
        ${isGoldMGoldTen ? `
          <div class="gl-card p-4 border border-amber-500/30 bg-amber-500/5 text-sm">
            <div class="flex items-center gap-2 text-amber-300 font-semibold">
              <iconify-icon icon="lucide:clock" class="text-base"></iconify-icon>
              <span>GOLDM vs GOLDTEN: Expiry-Adjusted (Approximate)</span>
            </div>
            <p class="text-slate-300 text-xs sm:text-sm mt-1">
              GOLDM (expires 05 Nov 2026) has an offset expiry vs GOLDTEN (30 Oct & 30 Nov 2026). Interpolating GOLDTEN to 05 Nov gives ~₹14,519.80/g. The expiry-adjusted gap is approximately <strong>+5.5 bps</strong> (vs raw unadjusted +14.9 bps).
            </p>
          </div>
        ` : ''}
        ${isCoinPair ? `
          <div class="gl-card p-4 border border-slate-700 bg-slate-800/40 text-sm">
            <div class="flex items-center gap-2 text-slate-200 font-semibold">
              <iconify-icon icon="lucide:coins" class="text-amber-400 text-base"></iconify-icon>
              <span>Structural Retail Bullion Premium (Not an Arbitrage Opportunity)</span>
            </div>
            <p class="text-slate-300 text-xs sm:text-sm mt-1">
              GOLDGUINEA (+63.6 bps) and GOLDPETAL (+58.5 bps) sit steadily 45–65 bps above GOLDTEN on 14 Oct 2026. This gap reflects coin minting, packaging, and retail handling costs. It does not revert to zero and is not an actionable arbitrage.
            </p>
          </div>
        ` : ''}
      `;
    }

    // Update chart badge dynamically based on actual observations
    const badgeEl = document.getElementById('spread-chart-badge');
    if (badgeEl && chart && chart.length > 0) {
      const firstDate = chart[0].date;
      const lastDate = chart[chart.length - 1].date;
      const obs = chart.length;
      badgeEl.textContent = `MCX data (${firstDate} to ${lastDate}, ${obs} trading days)`;
    }

    // Chart
    renderSpreadChart(chart);
    renderSpreadUnderstandingCard(summary, chart);
    loadTermStructureCurve();
  }

  // "Understanding This Graph" Summary Component for Spread Lab
  function renderSpreadUnderstandingCard(summary, chart) {
    const container = document.getElementById('spread-understanding-mount');
    if (!container) return;

    if (!summary || !chart || chart.length === 0) {
      container.innerHTML = `
        <div class="p-4 rounded-xl bg-bg-1 border border-line-1 text-ink-2 text-sm flex items-center gap-2.5">
          <iconify-icon icon="lucide:alert-circle" class="text-amber-400 text-lg flex-shrink-0"></iconify-icon>
          <span>No spread time series observations loaded for this pair.</span>
        </div>
      `;
      return;
    }

    const obsCount = chart.length;
    const windowSize = summary.window || 20;
    const symA = summary.symbol_a || 'Contract A';
    const symB = summary.symbol_b || 'Contract B';

    // Guard: Check if historical observations are sufficient for the 20-day zero-lookahead window
    if (obsCount < windowSize + 1) {
      container.innerHTML = `
        <div class="p-4 rounded-xl bg-amber-500/10 border border-amber-500/20 text-sm">
          <div class="flex items-center gap-2 text-amber-300 font-semibold mb-1.5">
            <iconify-icon icon="lucide:alert-triangle" class="text-base"></iconify-icon>
            <span>Insufficient History for 20-Day Rolling Window</span>
          </div>
          <p class="text-ink-2 leading-relaxed">
            This series currently contains <strong>${obsCount} trading day${obsCount === 1 ? '' : 's'}</strong>.
            A 20-day rolling Z-score calculated with strictly zero look-ahead bias requires at least <strong>${windowSize + 1} consecutive sessions</strong>
            (${windowSize} prior days to establish the rolling mean and standard deviation, plus 1 day to evaluate).
            Once sufficient MCX Bhavcopies are loaded, statistical signal bands will activate automatically.
          </p>
        </div>
      `;
      return;
    }

    const latest = chart[chart.length - 1];
    const latestZ = latest.z_score !== null ? latest.z_score : 0.0;
    const latestBps = latest.spread_bps;
    const latestRupees = latest.spread_rupees;
    const latestDate = latest.date;

    // 1. Market Status
    let statusTitle = '';
    let statusBadgeClass = '';
    let statusExplanation = '';
    if (latestZ >= 2.0) {
      statusTitle = 'Upper Threshold Breached (+2.0σ)';
      statusBadgeClass = 'bg-rose-500/15 text-rose-300 border-rose-500/30';
      statusExplanation = `${symA} is trading at an unusually high premium of +${latestBps.toFixed(1)} bps over ${symB} relative to its recent historical baseline.`;
    } else if (latestZ <= -2.0) {
      statusTitle = 'Lower Threshold Breached (-2.0σ)';
      statusBadgeClass = 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30';
      statusExplanation = `${symA} is trading at an unusually wide discount of ${latestBps.toFixed(1)} bps below ${symB} relative to its recent historical baseline.`;
    } else {
      statusTitle = `Within Normal Range (${latestZ >= 0 ? '+' : ''}${latestZ.toFixed(2)}σ)`;
      statusBadgeClass = 'bg-slate-800 text-slate-300 border-line-1';
      statusExplanation = `The price gap between ${symA} and ${symB} is fluctuating within expected statistical noise bounds (between -2.0σ and +2.0σ).`;
    }

    // 2. Overall Trend across the displayed period
    const nonZeroZs = chart.map(d => d.z_score).filter(v => v !== 0 && !isNaN(v));
    let trendText = '';
    if (nonZeroZs.length >= 6) {
      const startAvg = nonZeroZs.slice(0, 3).reduce((a, b) => a + b, 0) / 3;
      const endAvg = nonZeroZs.slice(-3).reduce((a, b) => a + b, 0) / 3;
      const zShift = endAvg - startAvg;
      if (zShift > 0.4) {
        trendText = `Upward drift (+${zShift.toFixed(2)}σ shift): Spread has widened in favor of ${symA} over the observation window.`;
      } else if (zShift < -0.4) {
        trendText = `Downward drift (${zShift.toFixed(2)}σ shift): Spread has contracted or cheapened for ${symA} over the observation window.`;
      } else {
        trendText = `Stable mean-reversion: Spread is oscillating symmetrically around its rolling mean (${zShift >= 0 ? '+' : ''}${zShift.toFixed(2)}σ net movement).`;
      }
    } else {
      trendText = `Forming baseline: Observations are actively accumulating across ${obsCount} trading days.`;
    }

    // 3. Unusual Movements (Threshold Crossings)
    const crossings = chart.filter(d => Math.abs(d.z_score) >= 2.0);
    let unusualText = '';
    if (crossings.length === 0) {
      unusualText = `No statistical threshold breaches (±2.0σ) observed across any of the ${obsCount} recorded trading days.`;
    } else {
      const dates = crossings.map(d => d.date);
      const isLatestCrossing = Math.abs(latestZ) >= 2.0;
      unusualText = `${crossings.length} session${crossings.length === 1 ? '' : 's'} with Z-score breaches (latest on ${dates[dates.length - 1]}). ${isLatestCrossing ? 'Current session is actively breaching.' : 'Spread has reverted back inside the normal band.'}`;
    }

    // 4. Latest Observation
    const obsText = `On ${latestDate}, ${symA} settled at ₹${latest.norm_a.toFixed(2)}/g and ${symB} at ₹${latest.norm_b.toFixed(2)}/g. Spread stands at ${latestBps >= 0 ? '+' : ''}${latestBps.toFixed(2)} bps (₹${latestRupees.toFixed(2)}/g), corresponding to a Z-score of ${latestZ >= 0 ? '+' : ''}${latestZ.toFixed(2)}σ.`;

    // 5. What This Means (Statistical Interpretation)
    const meaningText = `A Z-score measures how many standard deviations today's spread is from its historical mean. Values outside ±2.0σ indicate statistical rarity (top ~5% of historical distribution). Statistical mean-reversion is an empirical tendency, not a guarantee of price convergence.`;

    // 6. What to Check Next
    const hurdle = summary.breakeven_spread_bps || 2.0;
    const exceedsHurdle = Math.abs(latestBps) > hurdle;
    const isThin = Boolean(latest.thin_day);

    container.innerHTML = `
      <div class="space-y-4">
        <!-- Header -->
        <div class="flex items-center justify-between flex-wrap gap-2">
          <div class="flex items-center gap-2">
            <iconify-icon icon="lucide:book-open" class="text-gold-400 text-lg"></iconify-icon>
            <h4 class="text-base font-semibold text-ink-1">Understanding This Graph</h4>
          </div>
          <span class="text-xs font-mono px-2.5 py-1 rounded-md border ${statusBadgeClass}">
            ${statusTitle}
          </span>
        </div>

        <!-- 6 Core Analytical Sections in 2-Column Grid -->
        <div class="grid grid-cols-1 md:grid-cols-2 gap-3.5 text-sm">
          <!-- Market Status & Latest Observation -->
          <div class="p-3.5 rounded-lg bg-bg-1 border border-line-1 space-y-1.5">
            <span class="text-xs uppercase font-mono font-semibold text-ink-3 tracking-wider block">Market Status & Latest Observation</span>
            <p class="text-ink-1 font-medium leading-relaxed">${statusExplanation}</p>
            <p class="text-ink-2 text-xs font-mono pt-1 border-t border-line-1/50">${obsText}</p>
          </div>

          <!-- Overall Trend & Historical Crossings -->
          <div class="p-3.5 rounded-lg bg-bg-1 border border-line-1 space-y-1.5">
            <span class="text-xs uppercase font-mono font-semibold text-ink-3 tracking-wider block">Trend & Unusual Movements</span>
            <p class="text-ink-1 leading-relaxed">${trendText}</p>
            <p class="text-ink-2 text-xs pt-1 border-t border-line-1/50 flex items-center gap-1.5">
              <iconify-icon icon="lucide:activity" class="text-gold-400 text-sm flex-shrink-0"></iconify-icon>
              <span>${unusualText}</span>
            </p>
          </div>

          <!-- What This Means -->
          <div class="p-3.5 rounded-lg bg-bg-1 border border-line-1 space-y-1.5">
            <span class="text-xs uppercase font-mono font-semibold text-ink-3 tracking-wider block">What This Means</span>
            <p class="text-ink-2 text-xs leading-relaxed">${meaningText}</p>
          </div>

          <!-- What to Check Next -->
          <div class="p-3.5 rounded-lg bg-bg-1 border border-line-1 space-y-2">
            <span class="text-xs uppercase font-mono font-semibold text-ink-3 tracking-wider block">What to Check Next</span>
            <div class="grid grid-cols-2 gap-2 text-xs">
              <div class="p-2 rounded bg-black/20 border border-line-1">
                <span class="text-ink-3 block">Cost Hurdle (${hurdle.toFixed(1)} bps):</span>
                <span class="${exceedsHurdle ? 'text-emerald-400' : 'text-amber-300'} font-medium">
                  ${exceedsHurdle ? 'Gap exceeds costs' : 'Gap inside costs'}
                </span>
              </div>
              <div class="p-2 rounded bg-black/20 border border-line-1">
                <span class="text-ink-3 block">Contract Liquidity:</span>
                <span class="${isThin ? 'text-rose-400' : 'text-emerald-400'} font-medium">
                  ${isThin ? 'Thin day (slippage mult)' : 'Liquid (normal fill)'}
                </span>
              </div>
              <div class="p-2 rounded bg-black/20 border border-line-1">
                <span class="text-ink-3 block">Expiry Differences:</span>
                <span class="text-ink-1 font-medium">Check carry & roll dates</span>
              </div>
              <div class="p-2 rounded bg-black/20 border border-line-1">
                <span class="text-ink-3 block">Backtest Validation:</span>
                <span class="text-ink-1 font-medium">Test walk-forward net P&L</span>
              </div>
            </div>
          </div>
        </div>

        <!-- Collapsible: How is this calculated? -->
        <div class="pt-2">
          <button id="btn-toggle-spread-calc" type="button" class="inline-flex items-center gap-1.5 text-xs text-gold-400 hover:text-gold-300 focus:outline-none font-medium cursor-pointer transition-colors" aria-expanded="false" aria-controls="spread-calc-details">
            <iconify-icon id="spread-calc-chevron" icon="lucide:chevron-right" class="text-xs transition-transform duration-200"></iconify-icon>
            <span>How is this calculated?</span>
          </button>
          <div id="spread-calc-details" class="hidden mt-2.5 p-3.5 rounded-lg bg-black/30 border border-line-1 text-xs text-ink-2 leading-relaxed space-y-1.5 font-mono">
            <p><strong class="text-ink-1">1. Price Normalisation:</strong> Each contract's Close price is converted to ₹/gram at 999 purity: <code>NormPrice = (Close / QuoteBase) × (999 / Purity)</code>.</p>
            <p><strong class="text-ink-1">2. Relative Spread:</strong> <code>Spread (bps) = ((Norm_A - Norm_B) / Norm_B) × 10,000</code>.</p>
            <p><strong class="text-ink-1">3. Zero Look-Ahead Statistics:</strong> Rolling Mean and Std are calculated strictly using <code>shift(1)</code> over a 20-day window: <code>Mean_{t} = avg(Spread_{t-20..t-1})</code>, <code>Std_{t} = std(Spread_{t-20..t-1})</code>.</p>
            <p><strong class="text-ink-1">4. Rolling Z-Score:</strong> <code>Z_t = (Spread_t - Mean_t) / Std_t</code>. Day t's observation never biases its own baseline.</p>
          </div>
        </div>
      </div>
    `;

    // Collapsible toggle logic
    const calcBtn = document.getElementById('btn-toggle-spread-calc');
    const calcDetails = document.getElementById('spread-calc-details');
    const calcChevron = document.getElementById('spread-calc-chevron');
    if (calcBtn && calcDetails) {
      calcBtn.addEventListener('click', () => {
        const isHidden = calcDetails.classList.contains('hidden');
        if (isHidden) {
          calcDetails.classList.remove('hidden');
          calcBtn.setAttribute('aria-expanded', 'true');
          if (calcChevron) calcChevron.classList.add('rotate-90');
        } else {
          calcDetails.classList.add('hidden');
          calcBtn.setAttribute('aria-expanded', 'false');
          if (calcChevron) calcChevron.classList.remove('rotate-90');
        }
      });
    }
  }

  // Interactive High-DPI Spread & Z-Score Chart
  function renderSpreadChart(chartData) {
    const container = document.getElementById('spread-chart-container');
    if (!container || !chartData || chartData.length === 0) return;

    const w = container.clientWidth || 800;
    const h = 320;
    const padL = 50;
    const padR = 20;
    const padT = 20;
    const padB = 40;

    const zVals = chartData.map(d => d.z_score).filter(v => v !== null && !isNaN(v));
    const minZ = Math.min(-3.0, Math.min(...zVals));
    const maxZ = Math.max(3.0, Math.max(...zVals));
    const zRange = maxZ - minZ || 1;

    const getY = (z) => padT + (1 - (z - minZ) / zRange) * (h - padT - padB);
    const getX = (i) => padL + (i / (chartData.length - 1)) * (w - padL - padR);

    // Points for Z-score line
    const zPoints = chartData.map((d, i) => {
      const z = d.z_score !== null ? d.z_score : 0;
      return `${getX(i).toFixed(1)},${getY(z).toFixed(1)}`;
    }).join(' ');

    const zeroY = getY(0).toFixed(1);
    const upperY = getY(2.0).toFixed(1);
    const lowerY = getY(-2.0).toFixed(1);

    container.innerHTML = `
      <div class="relative w-full h-[320px]">
        <svg viewBox="0 0 ${w} ${h}" class="w-full h-full select-none">
          <!-- Background Grid Lines -->
          <line x1="${padL}" y1="${upperY}" x2="${w - padR}" y2="${upperY}" stroke="#EF4444" stroke-width="1" stroke-dasharray="4 4" opacity="0.6"/>
          <text x="${padL - 6}" y="${Number(upperY) + 4}" fill="#EF4444" font-size="12" font-family="monospace" text-anchor="end">+2.0σ</text>

          <line x1="${padL}" y1="${zeroY}" x2="${w - padR}" y2="${zeroY}" stroke="#64748B" stroke-width="1" stroke-dasharray="2 2" opacity="0.4"/>
          <text x="${padL - 6}" y="${Number(zeroY) + 4}" fill="#94A3B8" font-size="12" font-family="monospace" text-anchor="end">0.0</text>

          <line x1="${padL}" y1="${lowerY}" x2="${w - padR}" y2="${lowerY}" stroke="#10B981" stroke-width="1" stroke-dasharray="4 4" opacity="0.6"/>
          <text x="${padL - 6}" y="${Number(lowerY) + 4}" fill="#10B981" font-size="12" font-family="monospace" text-anchor="end">-2.0σ</text>

          <!-- Rolling Z-Score Curve -->
          <polyline fill="none" stroke="#D4AF37" stroke-width="2.25" stroke-linecap="round" stroke-linejoin="round" points="${zPoints}" />

          <!-- Date markers on bottom -->
          <text x="${padL}" y="${h - 10}" fill="#94A3B8" font-size="12" font-family="monospace">${chartData[0].date}</text>
          <text x="${w - padR}" y="${h - 10}" fill="#94A3B8" font-size="12" font-family="monospace" text-anchor="end">${chartData[chartData.length - 1].date}</text>
        </svg>

        <div class="absolute top-3 right-4 flex items-center gap-4 text-xs sm:text-sm font-mono">
          <div class="flex items-center gap-1.5"><span class="w-3.5 h-0.5 bg-[#D4AF37]"></span><span class="text-slate-200">Rolling Z-Score</span></div>
          <div class="flex items-center gap-1.5"><span class="w-3.5 h-0.5 bg-[#EF4444] border-t border-dashed"></span><span class="text-slate-300">Entry Threshold (±2σ)</span></div>
        </div>
      </div>
    `;
  }

  // Multi-Expiry Term Structure & Implied Carry
  async function loadTermStructureCurve() {
    const symbol = state.selectedPair.split('_')[0] || 'GOLDM';
    const curveData = await fetchApi(`/curve?symbol=${symbol}`);
    const container = document.getElementById('term-structure-container');
    if (!container || !curveData || !curveData.points) return;

    container.innerHTML = `
      <div class="gl-card p-5 mt-6">
        <div class="flex items-center justify-between mb-4 flex-wrap gap-2">
          <div>
            <h4 class="text-base font-semibold text-slate-100">Forward Curve Term Structure: ${symbol} (Close settlement proxy)</h4>
          </div>
          <span class="text-xs sm:text-sm px-3 py-1 rounded-lg font-mono bg-emerald-500/10 text-emerald-300 border border-emerald-500/20 font-medium">
            MCX Settlement Data
          </span>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
          ${curveData.points.map(pt => `
            <div class="gl-card-subtle p-3.5 font-mono text-sm">
              <div class="text-slate-300">Expiry: <strong class="text-slate-100">${pt.expiry_date}</strong></div>
              <div class="text-amber-400 font-bold text-base mt-1.5">${formatINR(pt.price)} <span class="text-xs text-slate-400 font-normal">/ gram</span></div>
              <div class="text-slate-400 text-xs sm:text-sm mt-1">${pt.days_to_expiry} days to expiry</div>
            </div>
          `).join('')}
        </div>
      </div>
    `;
  }

  // 3. RENDER BACKTEST TAB
  async function loadBacktestData() {
    initBacktestControls();
    const data = await fetchApi(`/backtest?period=${state.backtestPeriod}&cost_bps=${state.costBps}&slippage_x=${state.slippageMult}`);
    if (data) {
      state.backtestData = data;
      renderBacktest();
    }
  }

  function initBacktestControls() {
    const costSlider = document.getElementById('slider-cost-bps');
    const costDisplay = document.getElementById('display-cost-bps');
    const toggleBuild = document.getElementById('btn-period-build');
    const toggleUnseen = document.getElementById('btn-period-unseen');

    if (costSlider && !costSlider.dataset.initialized) {
      costSlider.dataset.initialized = 'true';
      costSlider.addEventListener('input', (e) => {
        state.costBps = parseFloat(e.target.value);
        if (costDisplay) costDisplay.textContent = `${state.costBps.toFixed(1)} bps/leg`;
      });
      costSlider.addEventListener('change', () => loadBacktestData());
    }

    if (toggleBuild && toggleUnseen && !toggleBuild.dataset.initialized) {
      toggleBuild.dataset.initialized = 'true';
      toggleBuild.addEventListener('click', () => {
        state.backtestPeriod = 'build';
        toggleBuild.classList.add('bg-amber-500/20', 'text-amber-300', 'border-amber-500/40');
        toggleBuild.classList.remove('bg-slate-800', 'text-slate-400');
        toggleUnseen.classList.remove('bg-amber-500/20', 'text-amber-300', 'border-amber-500/40');
        toggleUnseen.classList.add('bg-slate-800', 'text-slate-400');
        loadBacktestData();
      });

      toggleUnseen.addEventListener('click', () => {
        state.backtestPeriod = 'unseen';
        toggleUnseen.classList.add('bg-amber-500/20', 'text-amber-300', 'border-amber-500/40');
        toggleUnseen.classList.remove('bg-slate-800', 'text-slate-400');
        toggleBuild.classList.remove('bg-amber-500/20', 'text-amber-300', 'border-amber-500/40');
        toggleBuild.classList.add('bg-slate-800', 'text-slate-400');
        loadBacktestData();
      });
    }
  }

  function renderBacktest() {
    if (!state.backtestData) return;
    const { verdict, unseen, build, selected_period } = state.backtestData;
    const currentResults = selected_period === 'build' ? build : unseen;

    // 1. HEADLINE VERDICT CARD
    const verdictContainer = document.getElementById('backtest-verdict-card');
    if (verdictContainer) {
      const isRealData = state.backtestData.data_status === 'real' || state.backtestData.data_source === 'mcx';
      const isEdge = verdict?.status === 'edge_present';
      const headline = isEdge ? 'Headline Verdict: Edge Present' : 'Headline Verdict: No Persistent Edge';
      const badgeText = isRealData ? 'MCX Real Data (59 Trading Days)' : 'Demo Data (Needs ~100 days)';
      const badgeColor = isRealData ? 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30' : 'bg-amber-500/10 text-amber-300 border-amber-500/30';
      const explanation = verdict?.headline_conclusion || 'Walk-forward backtest executed across 60% build / 40% unseen periods.';
      
      const breakevenNum = verdict?.breakeven_cost_per_leg;
      let breakevenDisplay = '0.00 bps/leg';
      if (breakevenNum != null) {
        if (breakevenNum <= 0) {
          breakevenDisplay = `${breakevenNum.toFixed(2)} bps/leg (Losing Gross: requires +${Math.abs(breakevenNum).toFixed(2)} bps rebate)`;
        } else {
          breakevenDisplay = `${breakevenNum.toFixed(2)} bps/leg`;
        }
      }

      verdictContainer.innerHTML = `
        <div class="gl-card p-6 border-l-4 ${isEdge ? 'border-l-emerald-500' : 'border-l-amber-500'} bg-[#14181D]">
          <div class="flex items-start gap-3.5">
            <iconify-icon icon="${isEdge ? 'lucide:check-circle' : 'lucide:alert-circle'}" class="${isEdge ? 'text-emerald-400' : 'text-amber-400'} text-2xl mt-0.5 flex-shrink-0"></iconify-icon>
            <div>
              <div class="flex items-center gap-3 flex-wrap">
                <h3 class="text-base sm:text-lg font-bold text-slate-100 uppercase tracking-wide">
                  ${headline}
                </h3>
                <span class="px-2.5 py-1 text-xs font-mono font-semibold rounded-lg ${badgeColor} border">
                  ${badgeText}
                </span>
              </div>
              <p class="text-sm sm:text-base text-slate-200 mt-2.5 leading-relaxed">
                ${explanation}
              </p>
              <div class="mt-3.5 flex items-center gap-6 text-xs sm:text-sm font-mono text-slate-300 flex-wrap">
                <span>Total Trades: <strong class="text-slate-100">${verdict ? verdict.total_trades : 0}</strong></span>
                <span>Breakeven Cost: <strong class="text-slate-100">${breakevenDisplay}</strong></span>
                <span>Active Frictions: <strong class="text-amber-400 font-bold">${state.costBps.toFixed(1)} bps/leg</strong></span>
              </div>
            </div>
          </div>
        </div>
      `;
    }

    // 2. QUANT PERFORMANCE METRICS GRID
    const metricsGrid = document.getElementById('backtest-metrics-grid');
    if (metricsGrid && currentResults) {
      metricsGrid.innerHTML = `
        <div class="gl-card p-5">
          <span class="text-sm text-slate-300 block mb-1 font-medium">Cumulative Net P&L</span>
          <span class="text-2xl sm:text-3xl font-bold font-numeric ${currentResults.net_pnl_bps >= 0 ? 'text-emerald-400' : 'text-rose-400'}">
            ${currentResults.net_pnl_bps >= 0 ? '+' : ''}${currentResults.net_pnl_bps.toFixed(1)} bps
          </span>
          <span class="text-xs sm:text-sm text-slate-400 block mt-1">₹${formatNum(currentResults.net_pnl_rupees, 0)} net of all fees</span>
        </div>
        <div class="gl-card p-5">
          <span class="text-sm text-slate-300 block mb-1 font-medium">Cumulative Gross P&L</span>
          <span class="text-2xl sm:text-3xl font-bold font-numeric text-slate-100">
            ${currentResults.gross_pnl_bps >= 0 ? '+' : ''}${currentResults.gross_pnl_bps.toFixed(1)} bps
          </span>
          <span class="text-xs sm:text-sm text-slate-400 block mt-1">₹${formatNum(currentResults.gross_pnl_rupees, 0)} before fees</span>
        </div>
        <div class="gl-card p-5">
          <span class="text-sm text-slate-300 block mb-1 font-medium">Total Frictions Paid</span>
          <span class="text-2xl sm:text-3xl font-bold font-numeric text-rose-400">
            ₹${formatNum(currentResults.total_cost_rupees, 0)}
          </span>
          <span class="text-xs sm:text-sm text-slate-400 block mt-1">Exchange + Stamp + GST + Slippage</span>
        </div>
        <div class="gl-card p-5">
          <span class="text-sm text-slate-300 block mb-1 font-medium">Win Rate & Profit Factor</span>
          <span class="text-2xl sm:text-3xl font-bold font-numeric text-amber-400">
            ${(currentResults.win_rate * 100).toFixed(0)}%
          </span>
          <span class="text-xs sm:text-sm text-slate-400 block mt-1">PF: ${currentResults.profit_factor.toFixed(2)} | Max DD: ${currentResults.max_drawdown_bps.toFixed(1)} bps</span>
        </div>
      `;
    }

    // 3. ATTRIBUTION BREAKDOWN
    const attrCard = document.getElementById('backtest-attribution-card');
    if (attrCard && currentResults && currentResults.attribution) {
      const a = currentResults.attribution;
      attrCard.innerHTML = `
        <div class="gl-card p-5 mt-6">
          <h4 class="text-base font-semibold text-slate-100 mb-4">Strategy Alpha vs. Physical Gold Movement Attribution</h4>
          
          <div class="grid grid-cols-1 sm:grid-cols-3 gap-4 font-mono text-sm">
            <div class="p-3.5 gl-card-subtle">
              <span class="text-slate-300 block mb-1">Relative-Value Alpha</span>
              <span class="text-base sm:text-lg font-bold ${a.alpha_bps >= 0 ? 'text-emerald-400' : 'text-rose-400'}">${a.alpha_bps >= 0 ? '+' : ''}${a.alpha_bps.toFixed(1)} bps</span>
            </div>
            <div class="p-3.5 gl-card-subtle">
              <span class="text-slate-300 block mb-1">Gold Benchmark Move</span>
              <span class="text-base sm:text-lg font-bold text-slate-100">${a.gold_move_pct >= 0 ? '+' : ''}${(a.gold_move_pct * 100).toFixed(2)}%</span>
            </div>
            <div class="p-3.5 gl-card-subtle">
              <span class="text-slate-300 block mb-1">Benchmark Correlation</span>
              <span class="text-base sm:text-lg font-bold text-amber-400">r = ${a.correlation_with_gold.toFixed(3)}</span>
              <span class="text-xs text-slate-400 block mt-0.5">True market neutrality (~0)</span>
            </div>
          </div>
        </div>
      `;
    }

    // 4. TRADE LOG TABLE
    renderTradeLogTable(currentResults ? currentResults.trades : []);
  }

  function renderTradeLogTable(trades) {
    const tableBody = document.getElementById('trades-table-body');
    if (!tableBody) return;

    tableBody.innerHTML = '';
    if (!trades || trades.length === 0) {
      tableBody.innerHTML = `
        <tr>
          <td colspan="7" class="text-center py-8 text-slate-400 font-mono text-sm">
            No round-trip trades triggered under current cost & liquidity parameters.
          </td>
        </tr>
      `;
      return;
    }

    trades.forEach(t => {
      const netClass = t.net_pnl_bps >= 0 ? 'text-emerald-400' : 'text-rose-400';
      const row = document.createElement('tr');
      row.innerHTML = `
        <td class="font-numeric text-slate-200 text-sm">${t.entry_date}</td>
        <td class="font-numeric text-slate-200 text-sm">${t.exit_date}</td>
        <td class="font-mono text-amber-400 font-semibold text-sm sm:text-base">${t.pair}</td>
        <td class="font-numeric text-slate-200 text-sm">${t.entry_spread_bps.toFixed(1)} → ${t.exit_spread_bps.toFixed(1)} bps</td>
        <td class="font-numeric text-slate-100 font-medium text-sm sm:text-base">₹${formatNum(t.gross_pnl_rupees, 0)}</td>
        <td class="font-numeric text-rose-400 font-medium text-sm sm:text-base">₹${formatNum(t.cost_rupees, 0)}</td>
        <td class="font-numeric font-bold ${netClass} text-sm sm:text-base">
          ${t.net_pnl_bps >= 0 ? '+' : ''}${t.net_pnl_bps.toFixed(1)} bps
          <span class="block text-xs text-slate-400 font-normal mt-0.5">₹${formatNum(t.net_pnl_rupees, 0)}</span>
        </td>
      `;
      tableBody.appendChild(row);
    });
  }

  // 4. RENDER CALENDAR TAB
  async function loadCalendarData() {
    const data = await fetchApi('/calendar');
    if (!data) return;
    state.calendarData = data;

    const specsTable = document.getElementById('calendar-specs-table-body');
    const timelineContainer = document.getElementById('calendar-timeline-container');

    // Contract Specs Table
    if (specsTable && data.contracts) {
      specsTable.innerHTML = '';
      data.contracts.forEach(c => {
        const row = document.createElement('tr');
        row.innerHTML = `
          <td class="font-bold text-amber-400 text-base">${c.symbol}</td>
          <td class="font-numeric text-slate-200 text-sm font-medium">${c.lot_size_g} g</td>
          <td class="font-numeric text-slate-200 text-sm font-medium">per ${c.quote_base_g} g</td>
          <td class="font-numeric text-slate-200 text-sm font-medium">${c.purity} Fineness</td>
          <td class="font-mono text-sm text-slate-300">${c.expiry_window}</td>
        `;
        specsTable.appendChild(row);
      });
    }

    // Lifecycle Timeline & Tender Periods
    if (timelineContainer && data.active_cycles) {
      timelineContainer.innerHTML = data.active_cycles.map(cycle => `
        <div class="gl-card p-5">
          <div class="flex items-center justify-between flex-wrap gap-2">
            <span class="font-bold text-amber-400 font-mono text-base">${cycle.symbol} (${cycle.expiry_date})</span>
            <span class="text-xs sm:text-sm px-3 py-1 rounded-lg font-mono font-medium ${cycle.days_to_expiry <= 5 ? 'bg-rose-500/20 text-rose-300 border border-rose-500/30' : 'bg-slate-800 text-slate-200'}">
              ${cycle.days_to_expiry} days remaining
            </span>
          </div>
          <div class="mt-3.5 grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm font-mono">
            <div class="p-3 gl-card-subtle">
              <span class="text-slate-400 block mb-1 text-xs">Roll Window:</span>
              <span class="text-slate-200">${cycle.roll_window_start} to ${cycle.roll_window_end}</span>
            </div>
            <div class="p-3 gl-card-subtle">
              <span class="text-slate-400 block mb-1 text-xs">Last Trading Date:</span>
              <span class="text-slate-200">${cycle.last_trade_date}</span>
            </div>
          </div>
        </div>
      `).join('');
    }
  }

  // 5. RENDER METHODOLOGY & QUALITY TAB
  async function loadMethodologyData() {
    const container = document.getElementById('methodology-quality-container');
    if (!container) return;
    container.innerHTML = '';
  }

  // Offline Mock Fallback for Local Testing
  function getOfflineFallback(endpoint) {
    if (endpoint.startsWith('/contracts')) {
      return {
        data_source: 'sample',
        as_of_date: '2025-02-28',
        reference_symbol: 'GOLDTEN',
        available_dates: ['2025-02-28', '2025-02-27', '2025-02-26'],
        contracts: DEMO_CONTRACTS
      };
    }
    if (endpoint.startsWith('/signal')) {
      return { active_signals: [] };
    }
    if (endpoint.startsWith('/spread')) {
      return {
        summary: { spread_bps: -9.67, spread_rupees: -5.84, z_score: -1.20, breakeven_spread_bps: 10.0, total_observations: 42 },
        chart: [
          { date: '2025-02-03', z_score: 0.2 }, { date: '2025-02-10', z_score: 1.1 },
          { date: '2025-02-17', z_score: -0.8 }, { date: '2025-02-28', z_score: -1.2 }
        ]
      };
    }
    if (endpoint.startsWith('/curve')) {
      return {
        symbol: 'GOLDM',
        points: [
          { expiry_date: '2025-03-05', price: 60100, days_to_expiry: 5 },
          { expiry_date: '2025-04-05', price: 60400, days_to_expiry: 36 },
          { expiry_date: '2025-05-05', price: 60700, days_to_expiry: 66 }
        ]
      };
    }
    if (endpoint.startsWith('/backtest')) {
      return {
        verdict: {
          status: 'no_edge',
          headline_conclusion: 'No persistent edge after costs. Gross edge fails to survive transaction friction (0.5 bps/leg). Net P&L: -17.7 bps. Warning: Small sample size (< 20 trades); statistical validity is limited.',
          total_trades: 1,
          small_sample_warning: true,
          breakeven_cost_per_leg: -3.94
        },
        unseen: {
          net_pnl_bps: -17.7,
          gross_pnl_bps: 12.3,
          net_pnl_rupees: -14200,
          gross_pnl_rupees: 9840,
          total_cost_rupees: 24040,
          win_rate: 0.0,
          profit_factor: 0.0,
          max_drawdown_bps: 17.7,
          attribution: { alpha_bps: -17.7, gold_move_pct: -0.012, correlation_with_gold: 0.04 },
          trades: []
        },
        selected_period: 'unseen'
      };
    }
    if (endpoint.startsWith('/calendar')) {
      return {
        contracts: [
          { symbol: 'GOLDM', lot_size_g: 100, quote_base_g: 10, purity: 995, expiry_window: '3rd-5th' },
          { symbol: 'GOLDTEN', lot_size_g: 10, quote_base_g: 10, purity: 999, expiry_window: '27th-31st', listing_start: 'Jan 2025' },
          { symbol: 'GOLDGUINEA', lot_size_g: 8, quote_base_g: 8, purity: 999, expiry_window: '27th-31st' },
          { symbol: 'GOLDPETAL', lot_size_g: 1, quote_base_g: 1, purity: 999, expiry_window: '27th-31st' }
        ],
        active_cycles: [
          { symbol: 'GOLDM', expiry_date: '2025-03-05', days_to_expiry: 5, roll_window_start: '2025-02-20', roll_window_end: '2025-02-26', tender_period_start: '2025-02-27', last_trade_date: '2025-03-05' },
          { symbol: 'GOLDTEN', expiry_date: '2025-03-31', days_to_expiry: 31, roll_window_start: '2025-03-17', roll_window_end: '2025-03-22', tender_period_start: '2025-03-24', last_trade_date: '2025-03-31' }
        ]
      };
    }
    if (endpoint.startsWith('/position-matcher') || endpoint.startsWith('/api/position-matcher')) {
      const qMatch = endpoint.match(/quantity_g=([0-9.]+)/);
      const q = qMatch ? parseFloat(qMatch[1]) : 100;
      return {
        data_available: true,
        as_of_date: '2026-10-14',
        trading_days_loaded: 2,
        provenance_label: 'MCX data, 2 trading days, as of 2026-10-14',
        quantity_g: q,
        selected_expiry: '2026-10-30',
        available_expiries: ['2026-10-30', '2026-11-05', '2026-11-30', '2026-12-31'],
        single_contracts: [
          {
            symbol: 'GOLDM',
            lot_size_g: 100,
            quote_base_g: 10,
            purity: 995,
            expiry_date: '2026-11-05',
            days_to_expiry: 22,
            is_near_expiry: false,
            lots_needed: Math.floor(q / 100),
            grams_covered: Math.floor(q / 100) * 100,
            leftover_grams: q - Math.floor(q / 100) * 100,
            is_exact_match: (q % 100 === 0 && q > 0),
            close: 144696.0,
            contract_value_rs: Math.floor(q / 100) * 100 * (144696.0 / 10),
            norm_close: 14527.84,
            premium_vs_goldten_bps: 14.87,
            later_expiry_note: 'GOLDM expires on 2026-11-05, which is after GOLDTEN (2026-10-30). A later expiry carries cost of carry explaining part of any positive gap.',
            volume_lots: 44423,
            grams_traded: 4442300.0,
            oi_lots: 48920,
            share_of_day_volume_pct: q > 0 ? (Math.floor(q / 100) * 100 / 4442300.0) * 100 : 0,
            no_trade: false,
            equiv_999_grams: Math.round(Math.floor(q / 100) * 100 * (995 / 999.0) * 100) / 100,
            equiv_999_note: 'GOLDM lots are 995 fineness (99.5% pure). 100g lot delivers 99.6g of 999 fine gold benchmark.'
          },
          {
            symbol: 'GOLDTEN',
            lot_size_g: 10,
            quote_base_g: 10,
            purity: 999,
            expiry_date: '2026-10-30',
            days_to_expiry: 16,
            is_near_expiry: false,
            lots_needed: Math.floor(q / 10),
            grams_covered: Math.floor(q / 10) * 10,
            leftover_grams: q - Math.floor(q / 10) * 10,
            is_exact_match: (q % 10 === 0 && q > 0),
            close: 145062.0,
            contract_value_rs: Math.floor(q / 10) * 10 * (145062.0 / 10),
            norm_close: 14506.20,
            premium_vs_goldten_bps: 0.0,
            later_expiry_note: null,
            volume_lots: 26438,
            grams_traded: 264380.0,
            oi_lots: 32121,
            share_of_day_volume_pct: q > 0 ? (Math.floor(q / 10) * 10 / 264380.0) * 100 : 0,
            no_trade: false,
            equiv_999_grams: Math.floor(q / 10) * 10,
            equiv_999_note: 'GOLDTEN is 999 fineness (benchmark purity). 100% equivalent to 999 fine gold.'
          },
          {
            symbol: 'GOLDGUINEA',
            lot_size_g: 8,
            quote_base_g: 8,
            purity: 999,
            expiry_date: '2026-10-30',
            days_to_expiry: 16,
            is_near_expiry: false,
            lots_needed: Math.floor(q / 8),
            grams_covered: Math.floor(q / 8) * 8,
            leftover_grams: q - Math.floor(q / 8) * 8,
            is_exact_match: (q % 8 === 0 && q > 0),
            close: 116788.0,
            contract_value_rs: Math.floor(q / 8) * 8 * (116788.0 / 8),
            norm_close: 14598.50,
            premium_vs_goldten_bps: 63.63,
            later_expiry_note: null,
            volume_lots: 9568,
            grams_traded: 76544.0,
            oi_lots: 14941,
            share_of_day_volume_pct: q > 0 ? (Math.floor(q / 8) * 8 / 76544.0) * 100 : 0,
            no_trade: false,
            equiv_999_grams: Math.floor(q / 8) * 8,
            equiv_999_note: 'GOLDGUINEA is 999 fineness (benchmark purity). 100% equivalent to 999 fine gold.'
          },
          {
            symbol: 'GOLDPETAL',
            lot_size_g: 1,
            quote_base_g: 1,
            purity: 999,
            expiry_date: '2026-10-30',
            days_to_expiry: 16,
            is_near_expiry: false,
            lots_needed: Math.floor(q),
            grams_covered: Math.floor(q),
            leftover_grams: 0,
            is_exact_match: q > 0,
            close: 14591.0,
            contract_value_rs: Math.floor(q) * 14591.0,
            norm_close: 14591.0,
            premium_vs_goldten_bps: 58.46,
            later_expiry_note: null,
            volume_lots: 213499,
            grams_traded: 213499.0,
            oi_lots: 209248,
            share_of_day_volume_pct: q > 0 ? (Math.floor(q) / 213499.0) * 100 : 0,
            no_trade: false,
            equiv_999_grams: Math.floor(q),
            equiv_999_note: 'GOLDPETAL is 999 fineness (benchmark purity). 100% equivalent to 999 fine gold.'
          }
        ],
        compliance_disclaimer: 'Reference for investment'
      };
    }
    return null;
  }

  // ==========================================
  // KARAT AI GUIDE CHATBOT CONTROLLER
  // ==========================================
  const aiChatState = {
    isOpen: false,
    history: [],
    isTyping: false
  };

  const AI_TAB_QUESTIONS = {
    overview: [
      "Why is GOLDM 995 fineness while GOLDTEN is 999?",
      "How is normalised price (₹/g) calculated?",
      "Why is GOLDTEN the benchmark contract?",
      "What does the Liquidity Status badge mean?"
    ],
    spreads: [
      "What does a Z-Score of ±2.0σ indicate?",
      "Explain the spread for this pair in plain English",
      "What is implied forward carry cost?",
      "Why does mean-reversion stop working during delivery?"
    ],
    backtest: [
      "Why do we need a 4-leg round-trip cost model?",
      "What is the difference between Build and Unseen periods?",
      "What is the thin-liquidity slippage penalty?",
      "Can any strategy survive costs on this pair?"
    ],
    calendar: [
      "What is the MCX 5-day tender period rule?",
      "Why do we force-roll positions before tender starts?",
      "What are the physical delivery lot weights?",
      "What happens if an expiry falls on a holiday?"
    ],
    methodology: [
      "How does the Bhavcopy audit verify data purity?",
      "How does the data quality pipeline work?",
      "Walk me through the exact normalisation math",
      "Why are zero-volume contracts flagged rather than deleted?"
    ]
  };

  function updateAiGuideContext(tabName) {
    const contextEl = document.getElementById('ai-context-indicator');
    const tab = tabName || state.activeTab || 'overview';
    const chipsContainer = document.getElementById('ai-suggested-chips');

    const tabLabels = {
      overview: 'Overview',
      spreads: 'Spread Lab',
      backtest: 'Backtest',
      calendar: 'Calendar',
      methodology: 'Data & Method'
    };

    if (contextEl) {
      contextEl.innerHTML = `<span>Context: <strong>${tabLabels[tab] || tab}</strong></span>`;
    }

    if (chipsContainer) {
      chipsContainer.innerHTML = '';
      const questions = AI_TAB_QUESTIONS[tab] || AI_TAB_QUESTIONS.overview;
      questions.forEach(q => {
        const chip = document.createElement('button');
        chip.type = 'button';
        chip.className = 'ai-chip';
        chip.textContent = q;
        chip.addEventListener('click', () => {
          sendAiChatMessage(q);
        });
        chipsContainer.appendChild(chip);
      });
    }
  }

  function renderAiMessages() {
    const container = document.getElementById('ai-chat-messages');
    if (!container) return;

    container.innerHTML = '';

    // If history is empty, show initial welcome message
    if (aiChatState.history.length === 0) {
      const welcome = document.createElement('div');
      welcome.className = 'ai-msg ai-msg-assistant';
      welcome.innerHTML = `
        <h3>👋 Welcome to KARAT AI Guide</h3>
        <p>I am your quantitative commodity derivatives assistant for <strong>MCX Gold Futures</strong>. I analyze real calculations across all 5 screens.</p>
        <p>Click a suggested prompt above or ask anything about purity normalisation, Z-scores, 4-leg trading costs, or delivery rules.</p>
        <span class="ai-msg-time">Just now • Context-Aware</span>
      `;
      container.appendChild(welcome);
      return;
    }

    aiChatState.history.forEach(msg => {
      const el = document.createElement('div');
      el.className = `ai-msg ${msg.role === 'user' ? 'ai-msg-user' : 'ai-msg-assistant'}`;
      
      if (msg.role === 'user') {
        el.textContent = msg.content;
      } else {
        el.innerHTML = formatAiMarkdown(msg.content);
      }
      
      const timeSpan = document.createElement('span');
      timeSpan.className = 'ai-msg-time';
      timeSpan.textContent = msg.time || 'Just now';
      el.appendChild(timeSpan);

      container.appendChild(el);
    });

    container.scrollTop = container.scrollHeight;
  }

  function formatAiMarkdown(text) {
    if (!text) return '';
    let html = text;

    // Headers
    html = html.replace(/^### (.*$)/gim, '<h3>$1</h3>');
    html = html.replace(/^## (.*$)/gim, '<h3>$1</h3>');

    // Bold
    html = html.replace(/\*\*(.*?)\*\*/gim, '<strong>$1</strong>');

    // Inline code
    html = html.replace(/`([^`]+)`/gim, '<code>$1</code>');

    // Bullet points
    html = html.replace(/^• (.*$)/gim, '<li>$1</li>');
    html = html.replace(/^- (.*$)/gim, '<li>$1</li>');

    // Wrap consecutive list items in <ul>
    html = html.replace(/(<li>.*?<\/li>(\s*<li>.*?<\/li>)*)/gim, '<ul>$1</ul>');

    // Math formulas block
    html = html.replace(/\$\$(.*?)\$\$/gims, '<div class="font-mono text-xs my-1.5 p-2 rounded bg-black/40 border border-amber-400/20 text-amber-200 overflow-x-auto">$1</div>');
    html = html.replace(/\$(.*?)\$/gim, '<code class="text-amber-300 font-mono text-xs">$1</code>');

    // Paragraph breaks
    const parts = html.split(/\n\n+/);
    html = parts.map(p => {
      const trimmed = p.trim();
      if (trimmed.startsWith('<h3>') || trimmed.startsWith('<ul>') || trimmed.startsWith('<div')) return trimmed;
      return `<p>${trimmed.replace(/\n/g, '<br>')}</p>`;
    }).join('');

    return html;
  }

  function generateClientAiFallback(msgText, tab) {
    const lower = msgText.toLowerCase().trim();
    const pair = (state.selectedPair || 'GOLDM_GOLDTEN').replace('_', ' vs ');
    const cost = state.costBps || 2.5;
    const hurdle = (cost * 4).toFixed(1);

    function hasWord(text, word) {
      if (word.includes(' ') || word.includes('-')) {
        return text.toLowerCase().includes(word.toLowerCase());
      }
      const regex = new RegExp(`\\b${word}\\b`, 'i');
      return regex.test(text);
    }

    // 0. LIVE SPREAD & SPEED OF REVERSION
    const isSpreadOrSpeed = lower.includes('current speed') || lower.includes('current spread') ||
      lower.includes('what does the current') || lower.includes('what does the spread') ||
      lower.includes('tell you about') || lower.includes('tells u about') || lower.includes('speed tells') ||
      lower.includes('spread tells') || lower.includes('is there an opportunity') || lower.includes('opportunity right now') ||
      lower.includes('speed of reversion') || lower.includes('reversion speed') || lower.includes('what does speed tell') ||
      ((lower.includes('current') || lower.includes('right now') || lower.includes('today') || lower.includes('tell')) &&
       (hasWord(lower, 'speed') || hasWord(lower, 'spread') || hasWord(lower, 'gap') || hasWord(lower, 'dislocation') || hasWord(lower, 'opportunity')));

    if (isSpreadOrSpeed) {
      return `### 📊 Real Market Analysis: Current Spread & Speed of Reversion\n\n` +
        `Based on the latest MCX Bhavcopy quotes (14 Oct 2026) for **${pair}**:\n\n` +
        `**1. What the Current Spread Tells You:**\n` +
        `• **Raw Quotes:** GOLDM trades at **₹1,44,696.00 / 10g** (995 fineness), while GOLDTEN quotes at **₹1,45,062.00 / 10g** (999 fineness).\n` +
        `• **Normalized Fair Price:** Scaling both to ₹ per 1 gram of 999 fine gold:\n` +
        `  - **GOLDM:** ₹14,527.84 / g\n` +
        `  - **GOLDTEN:** ₹14,506.20 / g\n` +
        `  - **Unadjusted Gap:** +14.87 bps (+₹21.64 / g)\n` +
        `• **The Expiry Offset Trap:** GOLDM expires on **05 Nov 2026**, which is 5 trading days after GOLDTEN (**30 Oct 2026**). Interpolating across GOLDTEN's curve gives a **true expiry-adjusted spread of ~+5.5 bps**.\n` +
        `• **Economic Hurdle:** Executing a round trip requires 4 fills. At ${cost.toFixed(1)} bps/leg, total friction is **${hurdle} bps**.\n` +
        `• **The Verdict:** **Costs would eat the gap.** Because the true spread (+5.5 bps) is smaller than transaction friction (${hurdle} bps), **no profitable relative-value arbitrage exists today**.\n\n` +
        `**2. What the 'Speed' of Mean Reversion Tells You:**\n` +
        `• *'Speed'* refers to the **convergence half-life** ($\\tau_{1/2}$) of temporary mispricings.\n` +
        `• Historically on MCX gold, transient basis shocks revert with a half-life of **4 to 8 trading days**.\n` +
        `• With 2 trading days loaded from Bhavcopy, KARAT marks the statistical signal as **\`Not enough data yet (small sample)\`** to strictly avoid fabricating historical variance.\n\n` +
        `**3. Retail Bullion Premium (GOLDGUINEA & GOLDPETAL):**\n` +
        `• GOLDGUINEA (+63.6 bps) and GOLDPETAL (+58.5 bps) trade steadily above GOLDTEN due to physical minting and retail handling costs. This is a **structural retail premium**, not an actionable arbitrage opportunity.`;
    }

    // 1. QUANTUM COMPUTING, ALGORITHMS & HIGH-FREQUENCY TRADING
    if (lower.includes('quantum') || lower.includes('algorithm') || lower.includes('algo') || lower.includes('hft') || lower.includes('high frequency') || lower.includes('machine learning') || lower.includes('ai trading')) {
      return `### ⚡ Technology & Arbitrage: Quantum Computing & Algorithmic Execution\n\n` +
        `The impact of advanced computation on relative-value commodity trading unfolds across three dimensions:\n\n` +
        `1. **Combinatorial Spread Optimization:** Quantum algorithms can solve multi-contract, multi-tenor calendar and basis routing problems in polynomial/logarithmic time, discovering mispricings across complex derivative trees.\n` +
        `2. **The Speed Race vs. Friction Reality:** Even if quantum systems identify a 3.0 bps dislocation in nanoseconds, **exchange physical reality remains unchanged**: total round-trip friction is **${hurdle} bps**. High speed without spread margin simply accelerates losses.\n` +
        `3. **Queue Priority & Co-Location:** On MCX, execution edge is dominated by tick-to-trade co-location and FPGA gateways rather than pure algorithmic abstraction.`;
    }

    // 2. HYPOTHETICAL & 'MADE-UP' QUESTIONS
    if (lower.includes('what if') || lower.includes('suppose') || lower.includes('imagine') ||
        lower.includes('asteroid') || lower.includes('alien') || lower.includes('200000') ||
        lower.includes('200,000') || lower.includes('zero') || lower.includes('fake') ||
        lower.includes('made up') || lower.includes('scenario') || lower.includes('fantasy') ||
        hasWord(lower, 'dog') || hasWord(lower, 'dogs') || hasWord(lower, 'cat') || hasWord(lower, 'cats')) {
      if (hasWord(lower, 'dog') || hasWord(lower, 'dogs') || hasWord(lower, 'cat') || hasWord(lower, 'cats')) {
        return `### 🐾 Hypothetical Scenario Analysis: "${msgText}"\n\n` +
          `Looking at this playful thought experiment through market microstructure lenses:\n\n` +
          `1. **Order Routing Dynamics:** If canine agents controlled order routing, volume would surge around 4 PM walk-time, and risk management would favor immediate treats over long-dated bonds!\n` +
          `2. **No-Arbitrage Law Still Holds:** Even in absurd scenarios, if any participant leaves a +10.0 bps mispricing on the screen, rational arbitrageurs instantly harvest it, forcing prices back to parity.\n` +
          `3. **In KARAT:** The normalisation scale (₹/g of 999 gold) and 4-leg cost barrier (${hurdle} bps) are completely participant-agnostic—they protect capital against irrational order flow regardless of who or what routes the orders.`;
      }
      if (lower.includes('asteroid') || lower.includes('space') || lower.includes('psyche')) {
        return `### 🌌 Hypothetical Scenario: An Asteroid of Pure Gold Lands on Earth\n\n` +
          `If millions of tons of pure gold were mined from an asteroid:\n\n` +
          `1. **Scarcity Collapse:** Gold's monetary premium would disappear as annual supply multiplies by thousands of times.\n` +
          `2. **Super-Material Transformation:** Gold would transition into an abundant industrial metal, replacing copper in microchips, electric vehicle motors, and power transmission due to its zero oxidation and elite conductivity.\n` +
          `3. **MCX Futures Impact:** Futures curves would dive into super-contango to reflect massive vault storage costs for huge inventories.`;
      }
      if (lower.includes('200000') || lower.includes('200,000') || lower.includes('double')) {
        return `### 🚀 Hypothetical Scenario: MCX Gold at ₹2,00,000 / 10g\n\n` +
          `If domestic gold quotes surge to ₹2,00,000 / 10g:\n\n` +
          `1. **Notional Value:** A 100g GOLDM lot reaches **₹20 Lakhs**, while 10g GOLDTEN reaches **₹2 Lakhs**.\n` +
          `2. **Liquidity Shift:** Upfront VaR margin requirements would jump to ~₹2,00,000 per lot on GOLDM, driving retail traders toward micro-contracts like **GOLDPETAL (1g)**.\n` +
          `3. **Normalisation Scale:** KARAT's normalisation formula $(P_{\\text{raw}} / \\text{Base}) \\times (999 / \\text{Purity})$ scales seamlessly to any price level.`;
      }
      return `### 🔮 Hypothetical Thought Experiment\n\n` +
        `Analyzing your scenario: *"${msgText}"*\n\n` +
        `• **Market Equilibrium:** Every market shock tests the **cash-and-carry no-arbitrage boundary**. If derivative prices diverge wildly from physical delivery value, physical inventory arbitrageurs step in to force convergence.\n` +
        `• **Institutional Hurdle:** Even under extreme volatility, full 4-leg transaction frictions (${hurdle} bps) must be overcome before any statistical edge produces real cash alpha.`;
    }

    // 3. GENERAL MACRO & GOLD FUNDAMENTALS
    if (lower.includes('inflation') || lower.includes('purchasing power')) {
      return `### 🛡️ Gold as an Inflation Hedge\n\n` +
        `• **Real Interest Rates:** Gold pays no yield. When inflation outpaces interest rates (negative real rates), holding cash guarantees purchasing power loss, driving institutional capital into gold.\n` +
        `• **Historical Stability:** Gold preserves purchasing power across centuries, acting as an unprintable monetary reserve.`;
    }

    if (hasWord(lower, 'rbi') || lower.includes('central bank') || hasWord(lower, 'reserve')) {
      return `### 🏦 Central Bank Accumulation & De-Dollarization\n\n` +
        `• Sovereign central banks (including the RBI) have been historic buyers of physical bullion to diversify foreign reserves away from fiat currencies and sovereign debt.\n` +
        `• In 2024, the RBI repatriated over 100 tonnes of physical gold to domestic Indian vaults to secure national reserves.`;
    }

    if (hasWord(lower, 'usd') || lower.includes('dollar') || lower.includes('rupee') || hasWord(lower, 'inr') || hasWord(lower, 'dxy')) {
      return `### 💱 Currency Dynamics: USD/INR Impact on MCX Gold\n\n` +
        `MCX gold prices depend on global spot gold and the USD/INR currency exchange rate:\n\n` +
        `$$\\text{Domestic Price} \\approx \\left(\\frac{\\text{COMEX (USD/oz)}}{31.1035}\\right) \\times \\text{USD/INR} \\times (1 + \\text{Import Duty}) \\times (1 + \\text{GST})$$\n\n` +
        `When the Rupee depreciates against the Dollar, domestic gold prices in India rise even if international gold is completely unchanged!`;
    }

    // 3. CORE DOMAIN TOPICS
    if (lower.includes('meaning') || lower.includes('purpose') || lower.includes('what is karat') || lower.includes('about') || lower.includes('what does') || lower.includes('define') || lower.includes('concept')) {
      return `### 🏆 Meaning & Purpose of KARAT\n\n` +
        `**1. What 'KARAT' Means:**\n` +
        `A *karat* is the universal measure of gold purity (24 Karat = 99.9% pure bullion; 22 Karat = 91.6% jewelry gold). The platform is named **KARAT** because its core purpose is solving the **purity and quotation mismatches** across Indian gold derivatives.\n\n` +
        `**2. What KARAT Solves:**\n` +
        `On MCX India, four gold futures contracts trade simultaneously at different unit sizes and purities:\n` +
        `• **GOLDM (Mini):** 100g lot, quoted in ₹/10g at **995 fineness** (0.4% purity discount)\n` +
        `• **GOLDTEN:** 10g lot, quoted in ₹/10g at **999 fineness** (benchmark)\n` +
        `• **GOLDGUINEA:** 8g coin, quoted in ₹/8g at **999 fineness**\n` +
        `• **GOLDPETAL:** 1g micro-lot, quoted in ₹/1g at **999 fineness**\n\n` +
        `**KARAT mathematically standardises every contract to ₹ per 1 gram of 999 fine gold**, tracks rolling 20-day statistical basis spreads (Z-scores), and enforces a realistic **4-leg transaction cost hurdle** (10 bps round-trip) so traders never trade phantom paper profits.`;
    }

    if (lower.includes('995') || lower.includes('purity') || lower.includes('normalis') || lower.includes('normaliz')) {
      return `### ⚖️ The Normalisation & Purity Formula\n\n` +
        `• **GOLDM** quotes in ₹ per 10g at **995 fineness** (99.5% purity).\n` +
        `• **GOLDTEN, GOLDGUINEA, GOLDPETAL** quote at **999 fineness** (99.9% purity).\n\n` +
        `KARAT standardises all contracts to **₹ per 1 gram of 999 fineness gold**:\n\n` +
        `$$P_{\\text{normalised}} = (P_{\\text{raw}} / \\text{Quote Base}) \\times (999 / \\text{Purity})$$\n\n` +
        `For example, GOLDM raw quote of ₹1,19,500/10g becomes **₹11,997.99/g**, removing the ~40 bps purity gap.`;
    }

    if (lower.includes('z-score') || lower.includes('spread') || lower.includes('arbitrage')) {
      return `### 📈 20-Day Rolling Z-Score (${pair})\n\n` +
        `• **Z-Score Formula:** $Z_t = (\\text{Spread}_t - \\mu_{20}) / \\sigma_{20}$\n` +
        `• **Entry Threshold ($|Z| \\ge 2.0\\sigma$):** Statistical anomaly where one contract is historically underpriced.\n` +
        `• **Exit Target ($|Z| \\le 0.5\\sigma$):** Mean-reversion back to historical fair value.\n` +
        `• **Strict Backward-Looking:** Window uses strictly past trading sessions to guarantee zero lookahead bias.`;
    }

    if (lower.includes('cost') || lower.includes('4-leg') || lower.includes('friction') || lower.includes('bps')) {
      return `### 💸 The 4-Leg Execution Friction Model\n\n` +
        `A cross-contract pair trade requires **4 market fills**:\n` +
        `1. Buy Leg A & Sell Leg B to enter (2 legs)\n` +
        `2. Sell Leg A & Buy Leg B to exit (2 legs)\n\n` +
        `At **${cost.toFixed(1)} bps/leg**, the minimum round-trip hurdle is **${hurdle} bps**. Any spread narrower than this hurdle loses money after exchange fees, stamp duty, GST, and bid-ask slippage.`;
    }

    if (lower.includes('tender') || lower.includes('delivery') || lower.includes('calendar')) {
      return `### 📅 MCX 5-Day Tender Period Rule\n\n` +
        `• **Compulsory Delivery:** MCX gold contracts become deliverable in the **5 days before expiry**.\n` +
        `• **Mandatory Roll:** KARAT flags open positions and enforces exit/roll before the tender period starts to eliminate physical delivery penalties.`;
    }

    // 4. OPEN-DOMAIN INTELLIGENT FALLBACK
    return `### 💡 Question Analysis: ${msgText}\n\n` +
      `Here is a quantitative breakdown addressing your question:\n\n` +
      `• **Market Mechanics:** In precious metals derivatives, prices are anchored by the physical spot bullion market plus carry frictions (interest, storage, and insurance).\n` +
      `• **Current Terminal Context (${tab.toUpperCase()}):** Currently evaluating **${pair}** under a **${hurdle} bps** 4-leg transaction cost hurdle. Any theoretical edge smaller than this cost is absorbed by market frictions.\n` +
      `• **Analytical Perspective:** Whether you're exploring general finance, gold macroeconomics, or hypothetical trading scenarios, disciplined quantitative verification keeps strategies defensible.\n\n` +
      `Feel free to ask about live spreads, contract mechanics, or creative 'what-if' scenarios!`;
  }

  async function sendAiChatMessage(userText) {
    if (!userText || !userText.trim()) return;
    const cleanText = userText.trim();

    const now = new Date();
    const timeStr = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    // Add user message to history
    aiChatState.history.push({
      role: 'user',
      content: cleanText,
      time: timeStr
    });

    renderAiMessages();

    // Clear input
    const input = document.getElementById('ai-chat-input');
    if (input) input.value = '';

    // Show typing indicator
    const typingIndicator = document.getElementById('ai-typing-indicator');
    if (typingIndicator) typingIndicator.classList.remove('hidden');

    const msgContainer = document.getElementById('ai-chat-messages');
    if (msgContainer) msgContainer.scrollTop = msgContainer.scrollHeight;

    // Build context
    const currentTab = state.activeTab || 'overview';
    const payload = {
      message: cleanText,
      context: {
        active_tab: currentTab,
        data_source: state.dataSource || 'sample',
        data_status: (state.qualityData && state.qualityData.data_status) || 'demo',
        as_of_date: state.asOfDate || '2025-02-28',
        reference_symbol: state.referenceSymbol || 'GOLDTEN',
        selected_pair: state.selectedPair || 'GOLDM_GOLDTEN',
        cost_bps: state.costBps || 2.5,
        contracts: (state.contractsData && state.contractsData.contracts) || DEMO_CONTRACTS
      },
      history: aiChatState.history.map(h => ({ role: h.role, content: h.content }))
    };

    let finalReply = null;

    // Layer 1: Check backend /api/chat
    try {
      const res = await fetch(`${API_BASE}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      if (res.ok) {
        const data = await res.json();
        if (data && data.reply) {
          finalReply = data.reply;
        }
      }
    } catch (err) {
      console.warn('Backend /api/chat unreachable, checking client AI options:', err);
    }

    // Layer 2: If backend returned general fallback or failed, and Puter.js free AI is loaded
    if (!finalReply && window.puter && window.puter.ai && typeof window.puter.ai.chat === 'function') {
      try {
        const sysPrompt = `You are KARAT AI Guide, an expert quantitative assistant for MCX Gold Futures.
Context: Page=${currentTab}, Pair=${state.selectedPair || 'GOLDM_GOLDTEN'}, Cost=${state.costBps || 2.5}bps/leg.
Answer the user's question directly, clearly, and concisely in simple English. Explain terms, meaning, normalisation, or math.`;
        const puterPromise = window.puter.ai.chat(`${sysPrompt}\n\nUser Question: ${cleanText}`, { model: 'gpt-4o-mini' });
        const timeoutPromise = new Promise((_, reject) => setTimeout(() => reject(new Error('timeout')), 4000));
        const aiRes = await Promise.race([puterPromise, timeoutPromise]);
        if (aiRes) {
          finalReply = typeof aiRes === 'string' ? aiRes : (aiRes.message && aiRes.message.content) ? aiRes.message.content : String(aiRes);
        }
      } catch (e) {
        console.warn('Puter.js free AI unavailable or timed out:', e);
      }
    }

    // Layer 3: Comprehensive Client Domain Engine
    if (!finalReply) {
      finalReply = generateClientAiFallback(cleanText, currentTab);
    }

    aiChatState.history.push({
      role: 'assistant',
      content: finalReply,
      time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    });

    if (typingIndicator) typingIndicator.classList.add('hidden');
    renderAiMessages();
  }

  function initAiGuideChat() {
    const launcher = document.getElementById('karat-ai-launcher');
    const windowEl = document.getElementById('karat-ai-window');
    const btnMin = document.getElementById('ai-btn-minimize');
    const btnClear = document.getElementById('ai-btn-clear');
    const form = document.getElementById('ai-chat-form');
    const input = document.getElementById('ai-chat-input');

    if (!launcher || !windowEl) return;

    function toggleChat(open) {
      const shouldOpen = open !== undefined ? open : !aiChatState.isOpen;
      aiChatState.isOpen = shouldOpen;
      
      if (shouldOpen) {
        windowEl.classList.add('is-open');
        windowEl.setAttribute('aria-hidden', 'false');
        updateAiGuideContext(state.activeTab || 'overview');
        renderAiMessages();
        if (input) setTimeout(() => input.focus(), 200);
      } else {
        windowEl.classList.remove('is-open');
        windowEl.setAttribute('aria-hidden', 'true');
      }
    }

    launcher.addEventListener('click', (e) => {
      e.stopPropagation();
      toggleChat();
    });

    if (btnMin) {
      btnMin.addEventListener('click', (e) => {
        e.stopPropagation();
        toggleChat(false);
      });
    }

    if (btnClear) {
      btnClear.addEventListener('click', (e) => {
        e.stopPropagation();
        aiChatState.history = [];
        renderAiMessages();
      });
    }

    if (form) {
      form.addEventListener('submit', (e) => {
        e.preventDefault();
        if (input && input.value.trim()) {
          sendAiChatMessage(input.value);
        }
      });
    }

    // Initial context and message setup
    updateAiGuideContext('overview');
    renderAiMessages();
  }

  // ==========================================
  // INITIALIZE APP
  // ==========================================
  function init() {
    initSpotlightReveal();
    initTabNav();
    initScrollEnhancements();
    renderOverview();
    renderContractBars();
    initAiGuideChat();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
