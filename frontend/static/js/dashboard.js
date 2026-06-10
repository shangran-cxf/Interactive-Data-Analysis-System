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

            // ── 新增：触发 ML 重训练 ──
            corrLoaded = false;
            clusterLoaded = false;
            clusterChartInstance = null;
            fetch('/api/ml/retrain', { method: 'POST' })
                .then(() => {
                    mlInit();
                    showStatus('模型已更新', 'success');
                })
                .catch(() => {}); // 静默失败，不影响主流程
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

// ════════════════════════════════════════
//  ML 智能分析模块
// ════════════════════════════════════════

// Tab 切换
document.querySelectorAll('.ml-tab').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.ml-tab').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.ml-tab-content').forEach(c => c.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById('tab-' + btn.dataset.tab).classList.add('active');
    // 懒加载
    if (btn.dataset.tab === 'correlation') loadCorrelation();
    if (btn.dataset.tab === 'cluster')     loadCluster();
  });
});

// 初始化：加载模型状态
async function mlInit() {
  try {
    const res = await fetch('/api/ml/model-info');
    const data = await res.json();
    const badge = document.getElementById('mlModelBadge');
    if (!data.ready) {
      badge.textContent = '待训练';
      badge.className = 'ml-model-badge warn';
    } else if (data.mode === 'exploratory') {
      badge.textContent = `探索模式 · ${data.dataPoints}条`;
      badge.className = 'ml-model-badge warn';
    } else {
      badge.textContent = `R²=${data.r2} · ${data.dataPoints}条`;
      badge.className = 'ml-model-badge';
    }
  } catch(e) {
    document.getElementById('mlModelBadge').textContent = '离线';
    document.getElementById('mlModelBadge').className = 'ml-model-badge err';
  }
}

// 销量预测
async function mlPredict() {
  const price = parseFloat(document.getElementById('mlPrice').value);
  const energy = document.getElementById('mlEnergy').value;
  if (!price || price <= 0) {
    alert('请输入有效价格');
    return;
  }
  const btn = document.getElementById('mlPredictBtn');
  btn.textContent = '预测中...';
  btn.disabled = true;

  try {
    const res  = await fetch('/api/ml/predict', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ price, energyType: energy })
    });
    const data = await res.json();

    if (!data.success) {
      // 模型未训练时自动触发训练
      if (data.error && data.error.includes('未就绪')) {
        btn.textContent = '训练中...';
        await fetch('/api/ml/retrain', { method: 'POST' });
        btn.textContent = '预测';
        btn.disabled = false;
        mlPredict();
        return;
      }
      alert(data.error);
      return;
    }

    const pred = data.prediction;
    document.getElementById('resMonthly').textContent =
      pred.monthlySales.toLocaleString() + ' 辆';
    document.getElementById('resAnnual').textContent =
      pred.annualSales.toLocaleString() + ' 辆';
    document.getElementById('resCI').textContent =
      `[${pred.confidenceInterval[0].toLocaleString()}, ${pred.confidenceInterval[1].toLocaleString()}]`;
    document.getElementById('resEquation').textContent = data.equation || '';

    const warn = document.getElementById('resWarning');
    if (data.modelMetrics && data.modelMetrics.mode === 'exploratory') {
      warn.textContent = '⚠ 数据量较小，当前为趋势参考，非精确预测';
      warn.style.display = 'block';
    } else {
      warn.style.display = 'none';
    }

    document.getElementById('mlPredictResult').style.display = 'flex';
    document.getElementById('mlPredictEmpty').style.display = 'none';
    mlInit(); // 刷新 badge
  } catch(e) {
    alert('请求失败：' + e.message);
  } finally {
    btn.textContent = '预测';
    btn.disabled = false;
  }
}

// 关系分析
let corrLoaded = false;
async function loadCorrelation(stratify) {
  if (corrLoaded && !stratify) return;
  document.getElementById('corrLoading').style.display = 'block';
  document.getElementById('corrContent').style.display = 'none';

  try {
    const url = '/api/ml/correlation' + (stratify ? `?stratify=${stratify}` : '');
    const res  = await fetch(url);
    const data = await res.json();
    if (!data.success) return;

    // 更新按钮状态
    document.querySelectorAll('.ml-stratify-btns .ml-btn-sm').forEach((b, i) => {
      b.classList.toggle('active', (i === 0 && !stratify) || (i === 1 && !!stratify));
    });

    const ov = data.overall;
    document.getElementById('corrPearson').textContent =
      (ov.pearsonR >= 0 ? '+' : '') + ov.pearsonR;
    document.getElementById('corrInterpret').textContent = ov.interpretation;

    // 分层
    const stratifyDiv = document.getElementById('corrStratify');
    if (data.byEnergyType) {
      const html = Object.entries(data.byEnergyType).map(([k, v]) =>
        `<div class="ml-stratify-row">
           <span>${k}（n=${v.n}）</span>
           <span>${v.r !== undefined ? (v.r >= 0 ? '+' : '') + v.r : v.note}
             ${v.significant ? ' ★' : ''}</span>
         </div>`
      ).join('');
      document.getElementById('corrStratifyContent').innerHTML = html;
      stratifyDiv.style.display = 'block';
    } else {
      stratifyDiv.style.display = 'none';
    }

    // 反例
    const countersHtml = (data.counterExamples || []).map(c =>
      `<div class="ml-counter-row">
         <span>${c.model}（${c.price}万）</span>
         <span>${c.reason}</span>
       </div>`
    ).join('') || '<div class="ml-empty">暂无典型反例</div>';
    document.getElementById('corrCounters').innerHTML = countersHtml;

    // 价格区间
    const maxSales = Math.max(...(data.priceSegments || []).map(s => s.avgSales));
    const segHtml = (data.priceSegments || []).map(s => {
      const pct = maxSales > 0 ? Math.round(s.avgSales / maxSales * 100) : 0;
      return `<div class="ml-segment-row">
        <span style="width:60px;color:rgba(255,255,255,0.6)">${s.range}</span>
        <div class="ml-segment-bar-wrap">
          <div class="ml-segment-bar" style="width:${pct}%"></div>
        </div>
        <span style="color:#00ffb4;font-size:11px;width:70px;text-align:right">
          ${s.avgSales > 0 ? s.avgSales.toLocaleString() + '辆' : '—'}
        </span>
      </div>`;
    }).join('');
    document.getElementById('corrSegments').innerHTML = segHtml;

    document.getElementById('corrLoading').style.display = 'none';
    document.getElementById('corrContent').style.display = 'block';
    corrLoaded = true;
  } catch(e) {
    document.getElementById('corrLoading').textContent = '加载失败';
  }
}

// 聚类分析
let clusterLoaded = false;
let clusterChartInstance = null;

async function loadCluster() {
  if (clusterLoaded) return;
  document.getElementById('clusterLoading').style.display = 'block';
  document.getElementById('clusterContent').style.display = 'none';

  try {
    const res  = await fetch('/api/ml/cluster?k=3');
    const data = await res.json();
    if (!data.success) return;

    const colors = ['#ff6b6b', '#00d4ff', '#00ffb4'];
    const cardsHtml = data.clusters.map((c, i) =>
      `<div class="ml-cluster-card">
         <div class="ml-cluster-label">🏷 ${c.label}（${c.count}款）</div>
         <div class="ml-cluster-meta">
           均价 ${c.avgPrice}万 · 月均销量 ${c.avgSales.toLocaleString()}辆
         </div>
         <div class="ml-cluster-brands">${c.brands.join(' · ')}</div>
       </div>`
    ).join('');
    document.getElementById('clusterCards').innerHTML = cardsHtml;

    // 存散点图数据备用
    window._clusterScatterData = { data, colors };

    document.getElementById('clusterLoading').style.display = 'none';
    document.getElementById('clusterContent').style.display = 'block';
    clusterLoaded = true;
  } catch(e) {
    document.getElementById('clusterLoading').textContent = '加载失败';
  }
}

function toggleClusterChart() {
  const wrap = document.getElementById('clusterChartWrap');
  const btn  = document.getElementById('clusterChartBtn');
  const isHidden = wrap.style.display === 'none';
  wrap.style.display = isHidden ? 'block' : 'none';
  btn.textContent = isHidden ? '收起散点图' : '查看散点图';

  if (isHidden && window._clusterScatterData && !clusterChartInstance) {
    renderClusterChart(window._clusterScatterData);
  }
}

function renderClusterChart({ data, colors }) {
  // 复用项目已有的 echarts 全局变量
  const chart = echarts.init(document.getElementById('clusterChart'));
  clusterChartInstance = chart;

  const series = data.clusters.map((c, i) => ({
    name: c.label,
    type: 'scatter',
    data: c.vehicles.map(v => [v.price, v.sales, v.model]),
    itemStyle: { color: colors[i], opacity: 0.85 },
    symbolSize: 8,
  }));

  chart.setOption({
    backgroundColor: 'transparent',
    tooltip: {
      formatter: p => `${p.data[2]}<br/>价格: ${p.data[0]}万<br/>月销: ${p.data[1].toLocaleString()}辆`
    },
    legend: {
      data: data.clusters.map(c => c.label),
      textStyle: { color: 'rgba(255,255,255,0.5)', fontSize: 10 },
      bottom: 0
    },
    grid: { top: 10, left: 40, right: 10, bottom: 40 },
    xAxis: {
      name: '价格(万)', nameTextStyle: { color: 'rgba(255,255,255,0.3)', fontSize: 10 },
      axisLabel: { color: 'rgba(255,255,255,0.4)', fontSize: 10 },
      splitLine: { lineStyle: { color: 'rgba(255,255,255,0.05)' } }
    },
    yAxis: {
      name: '月销量', nameTextStyle: { color: 'rgba(255,255,255,0.3)', fontSize: 10 },
      axisLabel: { color: 'rgba(255,255,255,0.4)', fontSize: 10 },
      splitLine: { lineStyle: { color: 'rgba(255,255,255,0.05)' } }
    },
    series
  });

  window.addEventListener('resize', () => chart.resize());
}

// ── 数据上传后自动重训练 ──
// 找到你项目里上传成功后的回调，加上这行：
// await fetch('/api/ml/retrain', { method: 'POST' }); mlInit(); corrLoaded = false; clusterLoaded = false; clusterChartInstance = null;

// 页面加载时初始化
mlInit();

// ═══════════════ Logout ═══════════════
async function handleLogout() {
    stopPieRotate(); stopDonutRotate();
    await fetch('/api/auth/logout', { method:'POST' });
    window.location.href = '/login';
}
