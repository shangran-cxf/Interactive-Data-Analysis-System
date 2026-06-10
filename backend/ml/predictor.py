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