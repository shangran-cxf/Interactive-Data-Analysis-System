import os
import numpy as np
import joblib
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import cross_val_score
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score

MODELS_DIR = os.path.join(os.path.dirname(__file__), '../../ml_models')

SEASONAL_FACTORS = {
    1: 0.95, 2: 0.55, 3: 1.05, 4: 0.98,
    5: 1.02, 6: 1.08, 7: 0.92, 8: 0.96,
    9: 1.15, 10: 1.10, 11: 1.12, 12: 1.18
}

class SalesPredictor:
    def __init__(self, user_id):
        self.user_id = user_id
        self.model = None
        self.scaler = None
        self.metrics = {}
        self.model_path = os.path.join(MODELS_DIR, f'user_{user_id}_predictor.joblib')
        os.makedirs(MODELS_DIR, exist_ok=True)
        self._try_load()

    def _try_load(self):
        if os.path.exists(self.model_path):
            saved = joblib.load(self.model_path)
            self.model = saved['model']
            self.scaler = saved['scaler']
            self.metrics = saved['metrics']

    def _build_features(self, vehicles):
        """构建特征矩阵：价格 + 能源类型 One-Hot"""
        X, y = [], []
        for v in vehicles:
            try:
                price  = float(v.get('sales_price') or 0)
                sales  = float(v.get('sales_volume') or 0)
                energy = str(v.get('energy_type') or '油车')
                if price <= 0 or sales <= 0:
                    continue
                is_electric = 1 if '电' in energy else 0
                is_hybrid   = 1 if '混' in energy or 'DM' in energy or 'PHEV' in energy else 0
                X.append([price, is_electric, is_hybrid])
                y.append(sales)
            except (ValueError, TypeError):
                continue
        return np.array(X), np.array(y)

    def train(self, vehicles):
        X, y = self._build_features(vehicles)
        if len(X) < 5:
            return {'success': False, 'error': '有效数据不足 5 条，无法训练'}

        self.scaler = StandardScaler()
        X_scaled = self.scaler.fit_transform(X)

        self.model = LinearRegression()
        self.model.fit(X_scaled, y)

        y_pred = self.model.predict(X_scaled)
        r2   = r2_score(y, y_pred)
        rmse = float(np.sqrt(mean_squared_error(y, y_pred)))
        mae  = float(mean_absolute_error(y, y_pred))

        cv_scores = cross_val_score(self.model, X_scaled, y,
                                    cv=min(5, len(X)), scoring='r2')

        self.metrics = {
            'r2': round(r2, 4),
            'rmse': round(rmse, 1),
            'mae': round(mae, 1),
            'cv_r2_mean': round(float(cv_scores.mean()), 4),
            'data_points': len(X),
            'mode': 'predictive' if r2 >= 0 else 'exploratory',
            'coefficients': {
                'intercept': round(float(self.model.intercept_), 2),
                'price':      round(float(self.model.coef_[0]), 2),
                'is_electric':round(float(self.model.coef_[1]), 2),
                'is_hybrid':  round(float(self.model.coef_[2]), 2),
            }
        }

        joblib.dump({'model': self.model, 'scaler': self.scaler,
                     'metrics': self.metrics}, self.model_path)
        return {'success': True, **self.metrics}

    def predict(self, price, energy_type, month=None):
        if not self.model:
            return {'success': False, 'error': '模型未就绪，请先上传数据'}

        is_electric = 1 if '电' in energy_type else 0
        is_hybrid   = 1 if '混' in energy_type or 'DM' in energy_type else 0
        X = self.scaler.transform([[price, is_electric, is_hybrid]])

        monthly = max(0, float(self.model.predict(X)[0]))
        std_err  = self.metrics.get('rmse', monthly * 0.3)
        ci_low   = max(0, monthly - 1.96 * std_err)
        ci_high  = monthly + 1.96 * std_err

        annual_data = self.monthly_to_annual(monthly, month)

        return {
            'success': True,
            'prediction': {
                'monthlySales':       round(monthly),
                'annualSales':        annual_data['annualSales'],
                'annualMethod':       annual_data['method'],
                'confidenceInterval': [round(ci_low), round(ci_high)],
            },
            'modelMetrics': self.metrics,
            'equation': (f"月销量 = {self.metrics['coefficients']['intercept']} "
                         f"+ {self.metrics['coefficients']['price']}×价格 + 能源效应"),
            'coefficients': self.metrics.get('coefficients', {})
        }

    def predict_all(self, vehicles):
        """
        对全部车辆进行预测，返回实际销量 vs 预测销量对比数据（供前端 ECharts 使用）。

        返回:
            {
                'success': bool,
                'vehicles': [str],       # 车型名称列表
                'actual': [int],         # 实际销量
                'predicted': [int],      # 预测销量
                'r2': float,             # R² 拟合度
                'mae': float,            # 平均绝对误差
                'rmse': float,           # 均方根误差
                'data_points': int,      # 有效数据点数
            }
        """
        # 确保模型已训练
        if not self.model:
            train_result = self.train(vehicles)
            if not train_result.get('success'):
                return {'success': False,
                        'error': train_result.get('error', '模型训练失败'),
                        'vehicles': [], 'actual': [], 'predicted': [],
                        'r2': 0, 'mae': 0, 'rmse': 0, 'data_points': 0}

        vehicle_names = []
        actual_sales = []
        predicted_sales = []

        for v in vehicles:
            try:
                price = float(v.get('sales_price') or 0)
                energy = str(v.get('energy_type') or '油车')
                actual = float(v.get('sales_volume') or 0)
                name = f"{v.get('brand', '')} {v.get('model', '')}".strip()

                if price <= 0 or actual <= 0:
                    continue

                result = self.predict(price, energy)
                if result.get('success'):
                    predicted = result['prediction']['monthlySales']
                else:
                    predicted = 0

                vehicle_names.append(name)
                actual_sales.append(int(actual))
                predicted_sales.append(int(predicted))
            except (ValueError, TypeError):
                continue

        if not vehicle_names:
            return {'success': False,
                    'error': '无有效数据可预测',
                    'vehicles': [], 'actual': [], 'predicted': [],
                    'r2': 0, 'mae': 0, 'rmse': 0, 'data_points': 0}

        return {
            'success': True,
            'vehicles': vehicle_names,
            'actual': actual_sales,
            'predicted': predicted_sales,
            'r2': self.metrics.get('r2', 0),
            'mae': self.metrics.get('mae', 0),
            'rmse': self.metrics.get('rmse', 0),
            'data_points': len(vehicle_names),
        }

    def predict_trend(self, vehicles, price_range=None):
        """
        生成价格区间内不同能源类型的预测趋势数据（供前端 ECharts 折线图使用）。

        参数:
            vehicles: 车辆数据（用于训练模型）
            price_range: 价格点列表，默认 5~50 万每隔 5 万

        返回:
            {
                'success': bool,
                'prices': [5, 10, 15, ...],          # 价格点
                'series': {
                    '油车': [3200, 2800, ...],       # 每个价格点的预测销量
                    '电车': [4100, 3900, ...],
                    '混动': [3600, 3400, ...],
                },
                'r2': float,
                'data_points': int,
                'conclusions': [str, ...],           # 自动分析结论
            }
        """
        if price_range is None:
            price_range = list(range(5, 55, 5))  # 5, 10, 15, ..., 50

        # 确保模型已训练
        if not self.model:
            train_result = self.train(vehicles)
            if not train_result.get('success'):
                return {'success': False,
                        'error': train_result.get('error', '模型训练失败'),
                        'prices': [], 'series': {}, 'r2': 0, 'data_points': 0,
                        'conclusions': []}

        energy_types = ['油车', '电车', '混动']
        series = {et: [] for et in energy_types}

        for price in price_range:
            for et in energy_types:
                result = self.predict(price, et)
                if result.get('success'):
                    series[et].append(result['prediction']['monthlySales'])
                else:
                    series[et].append(0)

        # ── 自动生成分析结论 ──
        conclusions = []
        coeff = self.metrics.get('coefficients', {})

        # 结论1: 价格弹性
        price_coef = coeff.get('price', 0)
        if price_coef < 0:
            conclusions.append(f'价格上涨 1 万元，预测销量下降约 {abs(int(price_coef))} 辆 —— 符合价格弹性规律')
        else:
            conclusions.append('当前数据未呈现明显价格-销量负相关，建议扩充样本')
        # 结论2: 能源类型效应
        elec_coef = coeff.get('is_electric', 0)
        hyb_coef = coeff.get('is_hybrid', 0)
        if elec_coef > hyb_coef and elec_coef > 0:
            conclusions.append(f'电车品类溢价效应显著（系数 {elec_coef}），同等价位下电动车预测销量高于混动和燃油车')
        elif hyb_coef > elec_coef and hyb_coef > 0:
            conclusions.append(f'混动车型市场接受度最高（系数 {hyb_coef}），兼顾续航与政策优势')
        else:
            conclusions.append('不同能源类型的销量差异由品牌、定位等因素共同决定')
        # 结论3: 交叉验证
        cv_r2 = self.metrics.get('cv_r2_mean', 0)
        if cv_r2 > 0.5:
            conclusions.append(f'交叉验证 R²={cv_r2:.2f}，模型泛化能力良好，可用于辅助定价决策')
        elif cv_r2 > 0:
            conclusions.append(f'交叉验证 R²={cv_r2:.2f}，模型具有一定参考价值，建议增加样本量提升稳定性')
        else:
            conclusions.append('模型处于探索模式，当前预测仅供参考趋势方向')

        return {
            'success': True,
            'prices': price_range,
            'series': series,
            'r2': self.metrics.get('r2', 0),
            'mae': self.metrics.get('mae', 0),
            'rmse': self.metrics.get('rmse', 0),
            'data_points': self.metrics.get('data_points', 0),
            'mode': self.metrics.get('mode', 'exploratory'),
            'conclusions': conclusions,
            'coefficients': coeff,
        }

    def monthly_to_annual(self, monthly, month=None):
        factor = SEASONAL_FACTORS.get(month, 1.005)
        method = 'seasonal' if month else 'naive'
        return {
            'annualSales': round(monthly * 12 * factor),
            'method': method,
            'factor': factor
        }

    def get_model_info(self):
        if not self.model:
            return {'ready': False, 'r2': None, 'dataPoints': 0,
                    'mode': 'no_data', 'warning': '请先上传数据'}
        warning = None
        if self.metrics.get('r2', 0) < 0:
            warning = '当前数据量较小，R²为负，处于探索性分析模式'
        return {
            'ready': True,
            'r2':         self.metrics.get('r2'),
            'rmse':       self.metrics.get('rmse'),
            'mae':        self.metrics.get('mae'),
            'dataPoints': self.metrics.get('data_points', 0),
            'mode':       self.metrics.get('mode', 'exploratory'),
            'warning':    warning,
            'coefficients': self.metrics.get('coefficients', {})
        }