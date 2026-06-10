import numpy as np
from scipy import stats
from collections import defaultdict


class CorrelationAnalyzer:
    """价格-销量相关性分析器，支持按能源类型分层分析。"""

    def __init__(self, vehicles):
        self.vehicles = vehicles
        self._filtered = [v for v in vehicles if self._valid(v)]

    # ── 辅助方法 ──────────────────────────────────────────────

    def _valid(self, v):
        try:
            return (float(v.get('sales_price') or 0) > 0 and
                    float(v.get('sales_volume') or 0) > 0)
        except (ValueError, TypeError):
            return False

    def _get_price(self, v):
        return float(v.get('sales_price'))

    def _get_sales(self, v):
        return float(v.get('sales_volume'))

    def _get_energy(self, v):
        return str(v.get('energy_type') or '油车')

    # ── 入口 ──────────────────────────────────────────────────

    def analyze(self, stratify=None):
        if len(self._filtered) < 5:
            return {
                'success': False,
                'error': f'有效数据不足（需 ≥5 条，当前 {len(self._filtered)} 条）',
                'dataPoints': len(self._filtered),
            }

        prices = np.array([self._get_price(v) for v in self._filtered])
        sales  = np.array([self._get_sales(v) for v in self._filtered])

        result = self._global_analysis(prices, sales)

        if stratify in ('energy', 'energy_type'):
            result['byEnergyType'] = self._by_energy(prices, sales)
        else:
            result['byEnergyType'] = None

        result['counterExamples'] = self._find_counters(prices, sales)
        result['priceSegments']   = self._price_segments(prices, sales)

        return result

    # ── 全局分析 ──────────────────────────────────────────────

    def _global_analysis(self, prices, sales):
        r, p = stats.pearsonr(prices, sales)
        rho, p_s = stats.spearmanr(prices, sales)
        slope, intercept, r_value, p_value, std_err = stats.linregress(prices, sales)

        return {
            'success': True,
            'dataPoints': len(self._filtered),
            'overall': {
                'pearsonR': round(float(r), 4),
                'pearsonP': self._fmt_p(p),
                'spearmanRho': round(float(rho), 4),
                'spearmanP': self._fmt_p(p_s),
                'interpretation': self._interpret_r(r),
                'rSquared': round(float(r_value ** 2), 4),
                'equation': f'销量 ≈ {intercept:.0f} + {slope:.1f} × 价格',
            },
            'scatter': [
                {'price': round(float(pp), 1), 'sales': round(float(ss)),
                 'energy': self._get_energy(v)}
                for pp, ss, v in zip(prices, sales, self._filtered)
            ],
            'summary': {
                'avgPrice': round(float(prices.mean()), 1),
                'avgSales': round(float(sales.mean()), 1),
                'priceRange': [round(float(prices.min()), 1), round(float(prices.max()), 1)],
                'salesRange': [round(float(sales.min())), round(float(sales.max()))],
            },
        }

    # ── 按能源分层 ────────────────────────────────────────────

    def _by_energy(self, prices, sales):
        groups = defaultdict(list)
        for i, v in enumerate(self._filtered):
            groups[self._get_energy(v)].append(i)

        result = {}
        for energy, indices in groups.items():
            if len(indices) < 3:
                result[energy] = {'n': len(indices), 'r': None,
                                  'note': '样本不足', 'significant': False}
                continue
            gp = prices[indices]
            gs = sales[indices]
            r, p = stats.pearsonr(gp, gs)
            result[energy] = {
                'n': len(indices),
                'r': round(float(r), 4),
                'p': self._fmt_p(p),
                'significant': bool(p < 0.05),
                'avgPrice': round(float(gp.mean()), 1),
                'avgSales': round(float(gs.mean()), 1),
            }
        return result

    # ── 反例发现 ──────────────────────────────────────────────

    def _find_counters(self, prices, sales):
        """找到与整体趋势最不一致的车型。"""
        if len(prices) < 5:
            return []

        # 用回归残差最大的作为反例
        slope, intercept, r, p, std_err = stats.linregress(prices, sales)
        predicted = intercept + slope * prices
        residuals = np.abs(sales - predicted)
        top_idx = np.argsort(residuals)[-min(4, len(residuals)):][::-1]

        counters = []
        for idx in top_idx:
            v = self._filtered[idx]
            name = f"{v.get('brand', '')} {v.get('model', '')}".strip() or '未知车型'
            actual = sales[idx]
            expected = predicted[idx]
            direction = '高于' if actual > expected else '低于'
            counters.append({
                'model': name,
                'price': round(float(prices[idx]), 1),
                'actualSales': round(float(actual)),
                'expectedSales': round(float(expected)),
                'reason': f'实际销量{actual:.0f}，{direction}回归预测{expected:.0f}',
            })
        return counters

    # ── 价格区间分段 ──────────────────────────────────────────

    def _price_segments(self, prices, sales):
        """按价格区间统计平均销量。"""
        bins = [(0, 10), (10, 15), (15, 20), (20, 25), (25, 30), (30, 50), (50, 999)]
        segments = []
        for lo, hi in bins:
            mask = (prices >= lo) & (prices < hi)
            if mask.sum() == 0:
                continue
            label = f'{lo}-{hi}万' if hi < 999 else f'{lo}万以上'
            segments.append({
                'range': label,
                'count': int(mask.sum()),
                'avgSales': round(float(sales[mask].mean())),
                'avgPrice': round(float(prices[mask].mean()), 1),
            })
        return segments

    # ── 工具 ──────────────────────────────────────────────────

    @staticmethod
    def _interpret_r(r):
        abs_r = abs(r)
        if abs_r >= 0.8:
            return '强' + ('正相关' if r > 0 else '负相关')
        if abs_r >= 0.5:
            return '中等' + ('正相关' if r > 0 else '负相关')
        if abs_r >= 0.3:
            return '弱' + ('正相关' if r > 0 else '负相关')
        return '几乎无线性相关'

    @staticmethod
    def _fmt_p(p):
        if p < 0.001:
            return '<0.001'
        return str(round(p, 4))
