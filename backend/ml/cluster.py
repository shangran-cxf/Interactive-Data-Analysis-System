import numpy as np
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from collections import Counter


class MarketSegmenter:
    """基于价格-销量的 K-Means 市场细分器。"""

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

    # ── 聚类入口 ──────────────────────────────────────────────

    def segment(self, k=3):
        if len(self._filtered) < k:
            return {
                'success': False,
                'error': f'有效数据不足（需 ≥{k} 条，当前 {len(self._filtered)} 条）',
                'dataPoints': len(self._filtered),
            }

        prices = np.array([float(v.get('sales_price'))  for v in self.vehicles])
        sales  = np.array([float(v.get('sales_volume')) for v in self.vehicles])

        X = np.column_stack([prices, sales])
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)

        model = KMeans(n_clusters=k, random_state=42, n_init='auto')
        labels = model.fit_predict(X_scaled)

        centroids_scaled = model.cluster_centers_
        centroids = scaler.inverse_transform(centroids_scaled)

        # 按销量均值排序簇（高销量簇在前）
        cluster_order = sorted(range(k), key=lambda i: sales[labels == i].mean(), reverse=True)

        clusters = []
        for rank, i in enumerate(cluster_order):
            mask = labels == i
            cluster_vehicles = [self.vehicles[j] for j in range(len(self.vehicles)) if mask[j]]
            cluster_prices = prices[mask]
            cluster_sales  = sales[mask]

            # 收集品牌名
            brand_set = []
            for v in cluster_vehicles:
                b = str(v.get('brand', '')).strip()
                if b and b not in brand_set:
                    brand_set.append(b)

            clusters.append({
                'id': i,
                'rank': rank + 1,
                'label': self._label_cluster(rank, cluster_prices, cluster_sales),
                'count': int(mask.sum()),
                'avgPrice': round(float(cluster_prices.mean()), 1),
                'avgSales': round(float(cluster_sales.mean()), 1),
                'priceRange': [round(float(cluster_prices.min()), 1),
                               round(float(cluster_prices.max()), 1)],
                'salesRange': [round(float(cluster_sales.min())),
                               round(float(cluster_sales.max()))],
                'centroid': {'price': round(float(centroids[i][0]), 1),
                             'sales': round(float(centroids[i][1]), 1)},
                'brands': brand_set,
                'vehicles': [{'model': f"{v.get('brand','')} {v.get('model','')}".strip(),
                               'price': float(v.get('sales_price')),
                               'sales': float(v.get('sales_volume')),
                               'cluster': i}
                             for v in cluster_vehicles],
            })

        # 散点图数据（前端用）
        scatter_data = [
            {'x': float(prices[i]), 'y': float(sales[i]),
             'cluster': int(labels[i]),
             'name': f"{self.vehicles[i].get('brand', '')} {self.vehicles[i].get('model', '')}".strip()}
            for i in range(len(self.vehicles))
        ]

        # 各簇能源分布
        energy_by_cluster = {}
        for cl in clusters:
            ci = cl['id']
            mask = labels == ci
            energies = [str(self.vehicles[j].get('energy_type', '未知'))
                        for j in range(len(self.vehicles)) if mask[j]]
            energy_by_cluster[f'cluster_{ci}'] = dict(Counter(energies))

        return {
            'success': True,
            'dataPoints': len(self.vehicles),
            'k': k,
            'inertia': round(float(model.inertia_), 1),
            'clusters': clusters,
            'scatter': scatter_data,
            'counterExamples': self._find_counters(labels, k, prices, sales),
            'energyDistribution': energy_by_cluster,
            'summary': {
                'totalVehicles': len(self.vehicles),
                'validVehicles': len(self._filtered),
                'priceRange': [round(float(prices.min()), 1), round(float(prices.max()), 1)],
                'salesRange': [round(float(sales.min())), round(float(sales.max()))],
            },
        }

    # ── 反例查找 ──────────────────────────────────────────────

    def _find_counters(self, labels, k, prices, sales):
        """找出每个簇中离质心最远的点。"""
        counters = []
        for i in range(k):
            mask = labels == i
            if mask.sum() == 0:
                continue
            idx = np.where(mask)[0]
            cluster_center = np.array([prices[mask].mean(), sales[mask].mean()])
            distances = [np.linalg.norm(np.array([prices[j], sales[j]]) - cluster_center)
                         for j in idx]
            farthest_idx = idx[np.argmax(distances)]
            v = self.vehicles[farthest_idx]
            name = f"{v.get('brand', '')} {v.get('model', '')}".strip() or '未知车型'
            counters.append({
                'name': name,
                'price': float(prices[farthest_idx]),
                'sales': float(sales[farthest_idx]),
                'cluster': i,
                'reason': f'距簇{i}质心最远，可能属于其他细分市场',
            })
        return counters

    # ── 标签 ──────────────────────────────────────────────────

    @staticmethod
    def _label_cluster(rank, prices, sales):
        avg_p = prices.mean()
        avg_s = sales.mean()
        if rank == 0:
            tag = '高销量主力'
        elif avg_p > 25:
            tag = '高端车型'
        elif avg_p < 12:
            tag = '经济车型'
        else:
            tag = '中端均衡'
        return f'簇{rank+1}·{tag}'
