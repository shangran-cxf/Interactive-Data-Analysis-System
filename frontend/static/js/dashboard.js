// ═══════════════ Chart Instances ═══════════════
let salesChart, brandPieChart, priceBarChart, priceDonutChart;
let allCharts = [];
let salesDataFull = [];
let showBar = true, showLine = true;
let pieRotateTimer = null;
let donutRotateTimer = null;
let pieIdx = 0, donutIdx = 0;
let pieDataLen = 0, donutDataLen = 0;
let donutRanges = [];
let vehicleFilter = []; // selected vehicle names (empty = show all)

// ═══════════════ Colors ═══════════════
const CC = {
    text: '#c8cdd4',
    textDim: '#5e6670',
    axis: 'rgba(180,200,210,0.15)',
    split: 'rgba(180,200,210,0.04)',
    white: '#e2e6ea',
    barTop: 'rgba(210,220,230,0.88)',
    barBot: 'rgba(140,160,180,0.45)',
    line: '#bcc8d2',
    // Subtle cyan/teal/blue pastel tones for pie
    pie: ['#b3dce8','#8ecddb','#a3d5e2','#c2e2ed','#7cc3d4','#aedae6','#94cfe0','#b9e0ea','#88c8d8','#a0d3e3','#bcdde7','#ccdce3']
};

const tooltipStyle = {
    backgroundColor: 'rgba(10,20,34,0.95)',
    borderColor: 'rgba(130,160,180,0.2)',
    textStyle: { color: '#c8cdd4', fontSize: 10 }
};

// ═══════════════ Init ═══════════════
document.addEventListener('DOMContentLoaded', () => {
    initClock();
    initUpload();
    initAllCharts();
    initVehicleFilter();
    refreshAllData();
    window.addEventListener('resize', () => allCharts.forEach(c => { try { c.resize(); } catch(e) {} }));
});

function initClock() {
    const el = document.getElementById('headerTime');
    const tick = () => {
        const d = new Date();
        el.textContent = d.toLocaleString('zh-CN', {
            year:'numeric', month:'2-digit', day:'2-digit',
            hour:'2-digit', minute:'2-digit', second:'2-digit', hour12:false
        });
    };
    tick(); setInterval(tick, 1000);
}

// ═══════════════ Upload ═══════════════
function initUpload() {
    const zone = document.getElementById('uploadZone');
    const input = document.getElementById('fileInput');
    zone.addEventListener('click', () => input.click());
    zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('dragover'); });
    zone.addEventListener('dragleave', () => zone.classList.remove('dragover'));
    zone.addEventListener('drop', e => {
        e.preventDefault(); zone.classList.remove('dragover');
        if (e.dataTransfer.files[0]) {
            const dt = new DataTransfer(); dt.items.add(e.dataTransfer.files[0]);
            input.files = dt.files; handleFile(e.dataTransfer.files[0]);
        }
    });
    input.addEventListener('change', e => { if (e.target.files[0]) handleFile(e.target.files[0]); });
}

async function handleFile(file) {
    const ext = file.name.split('.').pop().toLowerCase();
    if (!['csv','json'].includes(ext)) { showStatus('仅支持 CSV 和 JSON 格式', 'error'); return; }
    showStatus('正在上传并处理...', 'info');
    const fd = new FormData(); fd.append('file', file);
    try {
        const r = await fetch('/api/data/upload', { method:'POST', body:fd });
        const d = await r.json();
        if (d.success) {
            showStatus(d.message, 'success');
            if (d.report) showReport(d.report, d.download_url);
            refreshAllData();
        } else showStatus(d.message, 'error');
    } catch(e) { showStatus('上传失败: ' + e.message, 'error'); }
}

function showStatus(msg, type) {
    const el = document.getElementById('uploadStatus');
    el.textContent = msg; el.className = 'upload-status show ' + type;
    if (type === 'success') setTimeout(() => el.classList.remove('show'), 5000);
}

function showReport(r, downloadUrl) {
    document.getElementById('cleaningReport').classList.add('show');
    const rows = [
        ['原始行数', r.original_rows], ['缺失填充', r.missing_filled],
        ['异常处理', r.outliers_detected], ['移除无效行', r.rows_removed],
        ['最终行数', r.final_rows]
    ];
    let html = rows.map(([k,v]) => `<div class="report-row"><span>${k}</span><span>${v}</span></div>`).join('');
    if (downloadUrl) {
        html += `<div style="margin-top:6px;text-align:center">
            <a href="${downloadUrl}" download style="display:inline-block;padding:4px 12px;border:1px solid rgba(140,184,154,0.25);border-radius:3px;color:#8cb89a;font-size:9px;text-decoration:none;letter-spacing:1px;transition:all 0.25s"
               onmouseover="this.style.background='rgba(140,184,154,0.06)'" onmouseout="this.style.background='transparent'">
                下载清洗后数据 (Excel)
            </a></div>`;
    }
    document.getElementById('reportContent').innerHTML = html;
}

function toggleCleaning() {
    const el = document.getElementById('cleaningReport');
    const t = document.getElementById('eyeToggle');
    if (el.classList.contains('show')) { el.classList.remove('show'); t.innerHTML = '<span>&#9678;</span> 显示'; }
    else { el.classList.add('show'); t.innerHTML = '<span>&#9673;</span> 隐藏'; }
}

// ═══════════════ Init Charts ═══════════════
function initAllCharts() {
    allCharts = [];
    salesChart = echarts.init(document.getElementById('salesChart')); allCharts.push(salesChart);
    brandPieChart = echarts.init(document.getElementById('brandPieChart')); allCharts.push(brandPieChart);
    priceBarChart = echarts.init(document.getElementById('priceBarChart')); allCharts.push(priceBarChart);
    priceDonutChart = echarts.init(document.getElementById('priceDonutChart')); allCharts.push(priceDonutChart);
}

function showEmpty(chart) {
    chart.setOption({
        title: { text: '暂无数据', left:'center', top:'center', textStyle:{ color:'#3a4048', fontSize:12, fontWeight:300 } }
    }, true);
}

// ═══════════════ Vehicle Filter ═══════════════
function initVehicleFilter() {
    const panel = document.getElementById('filterPanel');
    if (!panel) return;
    // Click outside to close
    document.addEventListener('click', e => {
        if (!e.target.closest('#filterPanel') && !e.target.closest('#filterBtn')) {
            panel.style.display = 'none';
        }
    });
}

function toggleFilterPanel() {
    const panel = document.getElementById('filterPanel');
    if (!panel) return;
    if (panel.style.display === 'block') { panel.style.display = 'none'; return; }
    // Build checkboxes
    const list = document.getElementById('filterList');
    list.innerHTML = salesDataFull.map((d, i) => `
        <label class="filter-item">
            <input type="checkbox" value="${i}" ${vehicleFilter.length===0||vehicleFilter.includes(i)?'checked':''}
                   onchange="onFilterChange()">
            <span>${d.name}</span>
        </label>
    `).join('');
    panel.style.display = 'block';
}

function onFilterChange() {
    const checks = document.querySelectorAll('#filterList input[type=checkbox]');
    vehicleFilter = [];
    checks.forEach(cb => { if (cb.checked) vehicleFilter.push(parseInt(cb.value)); });
    renderSalesChart();
}

// ═══════════════ Sales Chart — no animation, dataZoom slider ═══════════════
function updateSalesChart(data) {
    salesDataFull = data || [];
    vehicleFilter = []; // reset filter
    if (!salesDataFull.length) { showEmpty(salesChart); return; }
    renderSalesChart();
}

function renderSalesChart() {
    let filtered = vehicleFilter.length > 0
        ? vehicleFilter.map(i => salesDataFull[i]).filter(Boolean)
        : salesDataFull;
    if (!filtered.length) filtered = salesDataFull;

    const names = filtered.map(d => d.name.length > 10 ? d.name.slice(0,9)+'...' : d.name);
    const vols = filtered.map(d => d.volume);
    const prices = filtered.map(d => d.price);

    const dataZoom = filtered.length > 18 ? [{
        type: 'slider', bottom: 2, height: 14,
        borderColor: 'rgba(130,160,180,0.1)',
        backgroundColor: 'rgba(20,30,50,0.5)',
        fillerColor: 'rgba(100,140,170,0.15)',
        handleStyle: { color: '#7aa8c0', borderColor: '#7aa8c0' },
        textStyle: { color: '#5e6670', fontSize: 9 },
        start: 0, end: Math.min(18 / filtered.length * 100, 100)
    }] : [];

    const series = [];
    if (showBar) series.push({
        name: '销售辆数', type: 'bar', data: vols, yAxisIndex: 0, barWidth: '50%',
        itemStyle: {
            borderRadius: [2,2,0,0],
            color: new echarts.graphic.LinearGradient(0,0,0,1,[
                {offset:0, color: CC.barTop}, {offset:1, color: CC.barBot}
            ])
        }
    });
    if (showLine) series.push({
        name: '价格(万元)', type: 'line', data: prices, yAxisIndex: 1,
        smooth: true, symbol: 'circle', symbolSize: 4,
        lineStyle: { color: CC.line, width: 1.5 },
        itemStyle: { color: CC.white, borderWidth: 0 },
    });

    salesChart.setOption({
        tooltip: { trigger:'axis', ...tooltipStyle },
        legend: { bottom: dataZoom.length?18:0, textStyle:{ color:CC.textDim, fontSize:9 }, data:['销售辆数','价格(万元)'] },
        grid: { left:'3%', right:'4%', top:'12%', bottom: dataZoom.length?'10%':'5%', containLabel:true },
        dataZoom,
        xAxis: {
            type:'category', data:names,
            axisLine:{ lineStyle:{ color:CC.axis } },
            axisLabel:{ color:CC.textDim, fontSize: filtered.length>20?7:8, rotate: filtered.length>12?28:0 },
            axisTick:{ show:false }
        },
        yAxis: [
            {
                type:'value', name:'辆',
                nameTextStyle:{ color:CC.textDim, fontSize:8 },
                axisLabel:{ color:CC.textDim, fontSize:8 },
                splitLine:{ lineStyle:{ color:CC.split } }
            },
            {
                type:'value', name:'万元',
                nameTextStyle:{ color:CC.textDim, fontSize:8 },
                axisLabel:{ color:CC.textDim, fontSize:8 },
                splitLine:{ show:false }
            }
        ],
        series,
        animationDuration: 400
    }, true);
}

function toggleSeries(t) {
    if (t==='bar') { showBar=!showBar; document.getElementById('btnBar').classList.toggle('on',showBar); }
    else { showLine=!showLine; document.getElementById('btnLine').classList.toggle('on',showLine); }
    if (salesDataFull.length) renderSalesChart();
}

// ═══════════════ Brand Pie — roseType + auto rotate ═══════════════
function updateBrandPie(data) {
    if (!data || !data.length) { showEmpty(brandPieChart); stopPieRotate(); return; }
    pieDataLen = data.length;

    brandPieChart.setOption({
        tooltip: { trigger:'item', ...tooltipStyle, formatter:'{b}: {c} 辆 ({d}%)' },
        series: [{
            type: 'pie',
            radius: ['42%', '78%'],
            center: ['50%', '48%'],
            roseType: 'area',
            itemStyle: { borderColor:'#0c1c32', borderWidth:1.5, borderRadius:3 },
            label: { color:CC.textDim, fontSize:9, formatter:'{b}\n{d}%' },
            labelLine: { lineStyle:{ color:'rgba(180,200,210,0.18)' } },
            emphasis: {
                scaleSize: 10,
                label: { fontSize:13, color:CC.white },
                itemStyle: { shadowBlur:12, shadowColor:'rgba(160,200,220,0.25)' }
            },
            data: data.map((d, i) => ({
                value: d.sales, name: d.brand,
                itemStyle: { color: CC.pie[i % CC.pie.length] }
            })),
            animationType: 'scale',
            animationEasing: 'elasticOut'
        }]
    }, true);

    startPieRotate();
}

function startPieRotate() {
    stopPieRotate();
    if (!pieDataLen) return;
    pieIdx = 0;
    brandPieChart.dispatchAction({ type: 'highlight', seriesIndex: 0, dataIndex: 0 });

    pieRotateTimer = setInterval(() => {
        brandPieChart.dispatchAction({ type: 'downplay', seriesIndex: 0 });
        pieIdx = (pieIdx + 1) % pieDataLen;
        brandPieChart.dispatchAction({ type: 'highlight', seriesIndex: 0, dataIndex: pieIdx });
    }, 2200);
}

function stopPieRotate() {
    if (pieRotateTimer) { clearInterval(pieRotateTimer); pieRotateTimer = null; }
}

// ═══════════════ Price Distribution ═══════════════
function updatePriceCharts(data) {
    if (!data || !data.length || data.every(d => d.count === 0)) {
        showEmpty(priceBarChart); showEmpty(priceDonutChart);
        stopDonutRotate(); return;
    }
    const sorted = [...data].sort((a,b) => b.count - a.count);
    const barClrs = ['#b0d0de','#9abfcf','#c0dae5','#8ab0c2','#a8c8d6'];
    const totalC = sorted.reduce((s,d) => s + d.count, 0);
    donutDataLen = sorted.length;
    donutRanges = sorted.map(d => ({ name: d.range, count: d.count, pct: totalC > 0 ? (d.count/totalC*100).toFixed(1) : 0, price: d.lo !== undefined ? `${d.lo}-${d.hi===999?'以上':d.hi}万` : d.range }));

    // Horizontal bar
    priceBarChart.setOption({
        tooltip: { trigger:'axis', ...tooltipStyle },
        grid: { left:'2%', right:'10%', top:'8%', bottom:'2%', containLabel:true },
        xAxis: { type:'value', axisLabel:{ color:CC.textDim, fontSize:8 }, splitLine:{ lineStyle:{ color:CC.split } } },
        yAxis: { type:'category', data:sorted.map(d=>d.range), inverse:true, axisLabel:{ color:CC.text, fontSize:9 }, axisLine:{ show:false }, axisTick:{ show:false } },
        series: [{
            type:'bar', barWidth:'50%',
            data: sorted.map((d,i) => ({ value:d.count, itemStyle:{ color:barClrs[i%5], borderRadius:[0,2,2,0] } })),
            label: { show:true, position:'right', color:CC.textDim, fontSize:8, formatter:'{c}' }
        }],
        animationDuration: 500
    }, true);

    updateDonutCenter(0);

    priceDonutChart.setOption({
        tooltip: { trigger:'item', ...tooltipStyle, formatter:'{b}: {c} 款 ({d}%)' },
        series: [{
            type:'pie', radius:['48%','76%'], center:['50%','50%'],
            itemStyle: { borderColor:'#0c1c32', borderWidth:1.5, borderRadius:2 },
            label: { show:false },
            emphasis: { scaleSize:7, label:{ show:true, fontSize:11, color:CC.white } },
            data: sorted.map((d,i) => ({ value:d.count, name:d.range, itemStyle:{ color:barClrs[i%5] } })),
            animationType:'scale', animationEasing:'elasticOut'
        }],
        graphic: [{
            id: 'donutCenter', type:'group', left:'center', top:'center',
            children: [
                { type:'text', id:'donutPct', style:{ text:'0%', textAlign:'center', fill:CC.white, fontSize:18, fontWeight:400 } },
                { type:'text', id:'donutPrice', top:22, style:{ text:'', textAlign:'center', fill:CC.textDim, fontSize:9 } }
            ]
        }]
    }, true);

    startDonutRotate();
}

function updateDonutCenter(idx) {
    if (!donutRanges.length) return;
    const d = donutRanges[Math.min(idx, donutRanges.length - 1)];
    priceDonutChart.setOption({
        graphic: [{
            id: 'donutCenter', type:'group', left:'center', top:'center',
            children: [
                { type:'text', id:'donutPct', style:{ text:d.pct+'%', textAlign:'center', fill:CC.white, fontSize:18, fontWeight:400 } },
                { type:'text', id:'donutPrice', top:22, style:{ text:d.price||d.name, textAlign:'center', fill:CC.textDim, fontSize:9 } }
            ]
        }]
    });
}

function startDonutRotate() {
    stopDonutRotate();
    if (!donutDataLen) return;
    donutIdx = 0;
    priceDonutChart.dispatchAction({ type: 'highlight', seriesIndex: 0, dataIndex: 0 });

    donutRotateTimer = setInterval(() => {
        priceDonutChart.dispatchAction({ type: 'downplay', seriesIndex: 0 });
        donutIdx = (donutIdx + 1) % donutDataLen;
        priceDonutChart.dispatchAction({ type: 'highlight', seriesIndex: 0, dataIndex: donutIdx });
        updateDonutCenter(donutIdx);
    }, 2500);
}

function stopDonutRotate() {
    if (donutRotateTimer) { clearInterval(donutRotateTimer); donutRotateTimer = null; }
}

// ═══════════════ Stats ═══════════════
function updateStats(s) {
    const set = (id, v) => { document.getElementById(id).textContent = v; };
    set('statTotal', (s.totalVehicles||0).toLocaleString());
    set('statTopCar', s.topSalesCar||'-');
    set('statTopAmount', s.topSalesAmount||'-');
    set('statTopModel', s.topSalesModel||'-');
    set('statTopBrand', s.topBrandByModels||'-');
    set('statAvgPrice', s.avgPrice ? s.avgPrice+'万' : '-');
    set('energyOil', (s.oilRatio??0)+'%');
    set('energyElectric', (s.electricRatio??0)+'%');
    set('energyHybrid', (s.hybridRatio??0)+'%');
}

function updateBrandRanking(data) {
    const list = document.getElementById('brandRanking');
    if (!data || !data.length) {
        list.innerHTML = '<li style="justify-content:center;color:var(--text-dim)">暂无数据</li>';
        return;
    }
    list.innerHTML = data.slice(0,7).map((d,i) => `
        <li>
            <span class="rank-num">${i+1}</span>
            <span class="rank-name" title="${d.brand}">${d.brand}</span>
            <span class="rank-val">${d.sales.toLocaleString()}</span>
        </li>
    `).join('');
}

// ═══════════════ AI ═══════════════
async function requestAI() {
    const btn = document.getElementById('aiBtn');
    const ct = document.getElementById('aiContent');
    btn.disabled = true; btn.textContent = '分析中...';
    ct.innerHTML = '<div class="ai-loading"><div class="ai-spinner"></div><span>AI 正在分析数据</span></div>';
    try {
        const r = await fetch('/api/ai/evaluate', { method:'POST' });
        const d = await r.json();
        if (d.success) {
            let html = d.report
                .replace(/### (.*)/g, '<h3>$1</h3>')
                .replace(/## (.*)/g, '<h2>$1</h2>')
                .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
                .replace(/- (.*)/g, '<span style="display:block;padding-left:6px;margin:1px 0">- $1</span>')
                .replace(/\n/g, '<br>');
            if (d.source==='deepseek') html += '<div style="margin-top:8px;font-size:8px;color:#8cb89a;opacity:0.5;border-top:1px solid rgba(120,180,140,0.1);padding-top:6px">DeepSeek API 分析</div>';
            ct.innerHTML = html;
        } else {
            ct.innerHTML = `<div class="empty-state">${d.message}</div>`;
        }
    } catch(e) {
        ct.innerHTML = `<div class="empty-state">请求失败: ${e.message}</div>`;
    } finally {
        btn.disabled = false; btn.textContent = '生成报告';
    }
}

// ═══════════════ Data Refresh ═══════════════
async function refreshAllData() {
    stopPieRotate(); stopDonutRotate();
    try {
        const [sr, br, pr, er, cr] = await Promise.all([
            fetch('/api/data/stats'), fetch('/api/data/brand-sales'),
            fetch('/api/data/price-distribution'), fetch('/api/data/energy-ratio'),
            fetch('/api/data/sales-chart')
        ]);
        const stats = await sr.json();
        const brands = await br.json();
        const prices = await pr.json();
        const energy = await er.json();
        const chart = await cr.json();

        if (energy.oil !== undefined) {
            stats.oilRatio = energy.oil;
            stats.electricRatio = energy.electric;
            stats.hybridRatio = energy.hybrid;
        }
        updateStats(stats);
        updateBrandRanking(brands);
        updateSalesChart(chart);
        updateBrandPie(brands);
        updatePriceCharts(prices);
    } catch(e) {
        console.error('refresh error:', e);
    }
}

// ═══════════════ Logout ═══════════════
async function handleLogout() {
    stopPieRotate(); stopDonutRotate();
    await fetch('/api/auth/logout', { method: 'POST' });
    window.location.href = '/login';
}

// ═══════════════ Matplotlib 汽车销售统计图 (第二部分核心) ═══════════════
let chartMode = 'mpl';       // 当前模式: 'echarts' | 'mpl'
let chartConfig = null;       // 图表配置 (从后端获取)

// 初始化: 获取图表配置并填充下拉框
async function initChartConfig() {
    try {
        const resp = await fetch('/api/chart/config');
        chartConfig = await resp.json();
        if (!chartConfig) return;

        // 填充图表类型
        const typeSel = document.getElementById('paramChartType');
        if (typeSel) {
            typeSel.innerHTML = Object.entries(chartConfig.chart_types)
                .map(([k, v]) => `<option value="${k}">${v}</option>`).join('');
            typeSel.value = chartConfig.default_params.chart_type;
        }

        // 填充配色主题
        const themeSel = document.getElementById('paramTheme');
        if (themeSel) {
            themeSel.innerHTML = Object.entries(chartConfig.themes)
                .map(([k, v]) => `<option value="${k}">${v}</option>`).join('');
            themeSel.value = chartConfig.default_params.theme;
        }

        // 填充能源类型
        const energySel = document.getElementById('paramEnergy');
        if (energySel) {
            energySel.innerHTML = Object.entries(chartConfig.energy_filters)
                .map(([k, v]) => `<option value="${k}">${v}</option>`).join('');
            energySel.value = chartConfig.default_params.energy_filter;
        }

        // 填充排序字段
        const sortSel = document.getElementById('paramSortBy');
        if (sortSel) {
            sortSel.innerHTML = Object.entries(chartConfig.sort_fields)
                .map(([k, v]) => `<option value="${k}">${v}</option>`).join('');
            sortSel.value = chartConfig.default_params.sort_by;
        }

        // 其他默认参数
        const topNEl = document.getElementById('paramTopN');
        if (topNEl) topNEl.value = chartConfig.default_params.top_n;
        const titleEl = document.getElementById('paramTitle');
        if (titleEl) titleEl.value = chartConfig.default_params.title;
        const showValEl = document.getElementById('paramShowValue');
        if (showValEl) showValEl.checked = chartConfig.default_params.show_value;
        const gridEl = document.getElementById('paramGridOn');
        if (gridEl) gridEl.checked = chartConfig.default_params.grid_on;
    } catch (e) {
        console.error('加载图表配置失败:', e);
    }
}

// 切换图表模式 (ECharts / Matplotlib)
function switchChartMode(mode) {
    chartMode = mode;
    const btnEcharts = document.getElementById('btnModeEcharts');
    const btnMpl = document.getElementById('btnModeMpl');
    const btnParams = document.getElementById('btnParams');
    const salesChart = document.getElementById('salesChart');
    const mplImage = document.getElementById('mplChartImage');

    if (mode === 'mpl') {
        btnMpl.classList.add('on');
        btnEcharts.classList.remove('on');
        btnParams.style.display = 'inline-block';
        if (salesChart) salesChart.style.display = 'none';
        if (mplImage) mplImage.style.display = 'block';
        // 自动生成一次默认图表
        generateMplChart();
    } else {
        btnEcharts.classList.add('on');
        btnMpl.classList.remove('on');
        btnParams.style.display = 'none';
        const panel = document.getElementById('paramPanel');
        if (panel) panel.style.display = 'none';
        if (salesChart) salesChart.style.display = 'block';
        if (mplImage) mplImage.style.display = 'none';
        // 使用 ECharts 渲染
        refreshAllData();
    }
}

// 切换参数面板的显示/隐藏
function toggleParamPanel() {
    const panel = document.getElementById('paramPanel');
    if (!panel) return;
    panel.style.display = (panel.style.display === 'none' || panel.style.display === '') ? 'block' : 'none';
}

// 根据当前参数生成 Matplotlib 图表
async function generateMplChart() {
    const infoEl = document.getElementById('chartInfo');
    const mplImage = document.getElementById('mplChartImage');
    const btn = document.getElementById('btnGenerate');

    // 收集用户自定义参数
    const params = {
        chart_type: document.getElementById('paramChartType')?.value || 'bar',
        theme: document.getElementById('paramTheme')?.value || 'tech',
        top_n: parseInt(document.getElementById('paramTopN')?.value || '15'),
        sort_by: document.getElementById('paramSortBy')?.value || 'sales_volume',
        sort_order: document.getElementById('paramSortOrder')?.value || 'desc',
        title: document.getElementById('paramTitle')?.value || '汽车销售统计图',
        show_value: document.getElementById('paramShowValue')?.checked ?? true,
        grid_on: document.getElementById('paramGridOn')?.checked ?? true,
        energy_filter: document.getElementById('paramEnergy')?.value || 'all'
    };

    if (btn) { btn.disabled = true; btn.textContent = '生成中...'; }
    if (infoEl) infoEl.textContent = '正在生成图表...';

    try {
        const resp = await fetch('/api/chart/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(params)
        });
        const result = await resp.json();

        if (result.success && result.image_base64) {
            // 显示生成的 Matplotlib 图片
            if (mplImage) {
                mplImage.src = result.image_base64;
                mplImage.style.display = 'block';
                const echartsEl = document.getElementById('salesChart');
                if (echartsEl) echartsEl.style.display = 'none';
            }
            // 显示统计信息
            if (result.info && infoEl) {
                const info = result.info;
                infoEl.innerHTML = `✓ <b>${info.title}</b> | 类型: ${info.chart_type} | 主题: ${info.theme} | 数据: ${info.data_count}条 | 总销量: ${info.total_sales.toLocaleString()}辆 | 均价: ${info.avg_price}万元 | 字体: ${info.font_used}`;
            }
        } else {
            if (infoEl) infoEl.innerHTML = `<span style="color:#c07878">✗ ${result.message || '图表生成失败'}</span>`;
        }
    } catch (e) {
        if (infoEl) infoEl.innerHTML = `<span style="color:#c07878">✗ 请求失败: ${e.message}</span>`;
    } finally {
        if (btn) { btn.disabled = false; btn.innerHTML = '🎨 生成图表'; }
    }
}

// 在页面初始化完成后加载图表配置 (覆盖原 init 的 refresh)
document.addEventListener('DOMContentLoaded', () => {
    setTimeout(() => {
        initChartConfig();
        // 默认进入 Matplotlib 模式
        switchChartMode('mpl');
    }, 300);
});
