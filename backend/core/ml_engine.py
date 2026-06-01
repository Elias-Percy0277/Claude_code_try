"""
ML 引擎模块
针对 Adult Income 数据集的机器学习建模与评估
"""
import pandas as pd
import numpy as np
import logging
from typing import Dict, List, Any, Optional, Tuple
from collections import Counter

logger = logging.getLogger(__name__)

try:
    from sklearn.model_selection import train_test_split, StratifiedKFold, cross_val_score
    from sklearn.preprocessing import StandardScaler, OneHotEncoder, OrdinalEncoder
    from sklearn.linear_model import LogisticRegression
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.metrics import (
        accuracy_score, precision_score, recall_score, f1_score,
        confusion_matrix, classification_report, roc_auc_score,
        roc_curve, precision_recall_curve, average_precision_score
    )
    from sklearn.compose import ColumnTransformer
    from sklearn.pipeline import Pipeline
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False
    logger.warning("scikit-learn 未安装，ML 功能不可用")


class MLError(Exception):
    pass


# Adult 数据集的默认特征配置
ADULT_DROP_COLUMNS = ['fnlwgt', 'education']
ADULT_TARGET_COLUMN = 'col_14'
ADULT_TARGET_MAP = {'<=50K': 0, '<=50K.': 0, '>50K': 1, '>50K.': 1}

NUMERIC_FEATURES = ['age', 'education-num', 'capital-gain', 'capital-loss', 'hours-per-week']
CATEGORICAL_FEATURES = [
    'workclass', 'marital-status', 'occupation',
    'relationship', 'race', 'sex', 'native-country'
]

# 低频合并阈值
RARE_THRESHOLD = 50


def _detect_target_column(df: pd.DataFrame) -> Optional[str]:
    """自动检测目标列（包含 <=50K/>50K 值的列）"""
    for col in df.columns:
        unique_vals = df[col].dropna().astype(str).unique()
        if any(v in {'<=50K', '>50K', '<=50K.', '>50K.'} for v in unique_vals):
            return col
    return None


def _detect_feature_columns(df: pd.DataFrame, target_col: str) -> Tuple[List[str], List[str]]:
    """自动检测数值特征和分类特征列"""
    all_cols = [c for c in df.columns if c != target_col]
    drop_cols = [c for c in all_cols if c in ADULT_DROP_COLUMNS]
    keep_cols = [c for c in all_cols if c not in drop_cols]

    numeric_cols = []
    categorical_cols = []
    for col in keep_cols:
        if pd.api.types.is_numeric_dtype(df[col]):
            numeric_cols.append(col)
        else:
            categorical_cols.append(col)

    return numeric_cols, categorical_cols


def _merge_rare_categories(df: pd.DataFrame, col: str, threshold: int = RARE_THRESHOLD) -> pd.DataFrame:
    """合并低频类别为 'Other'"""
    counts = df[col].value_counts()
    rare = counts[counts < threshold].index.tolist()
    if rare:
        df[col] = df[col].replace(rare, 'Other')
    return df


class AdultMLEngine:
    """Adult Income 数据集的机器学习引擎"""

    def __init__(self):
        self.model = None
        self.model_name = None
        self.preprocessor = None
        self.feature_names = None
        self.target_col = None
        self.is_fitted = False
        self.X_test = None
        self.y_test = None
        self.y_pred = None
        self.y_proba = None
        self.training_stats = {}

    def prepare(
        self,
        df: pd.DataFrame,
        target_col: Optional[str] = None,
        test_size: float = 0.2,
        random_state: int = 42
    ) -> Dict[str, Any]:
        """
        数据准备：特征工程 + 数据分割

        Returns:
            包含训练/测试数据和统计信息的字典
        """
        if not HAS_SKLEARN:
            raise MLError("scikit-learn 未安装")

        # 检测目标列
        if target_col is None:
            target_col = _detect_target_column(df)
        if target_col is None:
            raise MLError("无法检测目标列（未找到包含 <=50K/>50K 的列）")

        self.target_col = target_col

        # 目标编码
        y = df[target_col].astype(str).str.strip().map(ADULT_TARGET_MAP)
        if y.isna().any():
            unmapped = df[target_col][y.isna()].unique()
            logger.warning(f"目标列存在未映射的值: {unmapped}")
            y = y.fillna(0)

        # 检测特征列
        numeric_cols, categorical_cols = _detect_feature_columns(df, target_col)

        # 准备特征数据
        df_features = df[[c for c in df.columns if c != target_col]].copy()

        # 移除无关列
        for col in ADULT_DROP_COLUMNS:
            if col in df_features.columns:
                df_features.drop(columns=[col], inplace=True)

        # 更新特征列列表（移除后）
        numeric_cols = [c for c in numeric_cols if c in df_features.columns]
        categorical_cols = [c for c in categorical_cols if c in df_features.columns]

        # 资本特征二值化
        for cap_col in ['capital-gain', 'capital-loss']:
            if cap_col in df_features.columns:
                df_features[f'has_{cap_col}'] = (df_features[cap_col] > 0).astype(int)
                if cap_col not in numeric_cols:
                    numeric_cols.append(f'has_{cap_col}')

        # 对偏态特征做 log(1+x) 变换
        for cap_col in ['capital-gain', 'capital-loss']:
            if cap_col in df_features.columns:
                df_features[cap_col] = np.log1p(df_features[cap_col].clip(lower=0))

        # 合并低频类别
        for col in categorical_cols:
            df_features = _merge_rare_categories(df_features, col)

        # 填充缺失值
        for col in numeric_cols:
            df_features[col] = df_features[col].fillna(df_features[col].median())
        for col in categorical_cols:
            df_features[col] = df_features[col].fillna('Missing')

        # 数据分割
        X_train, X_test, y_train, y_test = train_test_split(
            df_features, y, test_size=test_size,
            random_state=random_state, stratify=y
        )

        # 构建预处理器
        numeric_transformer = StandardScaler()
        categorical_transformer = OneHotEncoder(handle_unknown='ignore', sparse_output=False)

        self.preprocessor = ColumnTransformer(
            transformers=[
                ('num', numeric_transformer, numeric_cols),
                ('cat', categorical_transformer, categorical_cols)
            ]
        )

        # 获取特征名
        self.feature_names = numeric_cols + categorical_cols

        # 保存测试数据
        self.X_test = X_test
        self.y_test = y_test

        # 统计信息
        target_dist = y.value_counts().to_dict()
        total = len(y)
        self.training_stats = {
            "total_samples": total,
            "train_samples": len(X_train),
            "test_samples": len(X_test),
            "target_distribution": {str(k): int(v) for k, v in target_dist.items()},
            "target_ratio": f"{target_dist.get(1, 0) / total * 100:.1f}% >50K",
            "numeric_features": numeric_cols,
            "categorical_features": categorical_cols,
            "feature_count": len(numeric_cols) + len(categorical_cols),
        }

        logger.info(f"数据准备完成: {len(X_train)} 训练, {len(X_test)} 测试, 特征数: {len(numeric_cols) + len(categorical_cols)}")

        return {
            "X_train": X_train,
            "X_test": X_test,
            "y_train": y_train,
            "y_test": y_test,
            "stats": self.training_stats
        }

    def train(
        self,
        X_train: pd.DataFrame,
        y_train: pd.Series,
        model_type: str = "random_forest",
        **kwargs
    ) -> Dict[str, Any]:
        """
        训练模型

        Args:
            model_type: 'logistic_regression' 或 'random_forest'
        """
        if self.preprocessor is None:
            raise MLError("请先调用 prepare()")

        if model_type == "logistic_regression":
            classifier = LogisticRegression(
                max_iter=1000, solver='saga',
                class_weight='balanced', random_state=42,
                **kwargs
            )
            self.model_name = "逻辑回归"
        else:
            n_estimators = kwargs.pop('n_estimators', 200)
            classifier = RandomForestClassifier(
                n_estimators=n_estimators,
                class_weight='balanced',
                random_state=42,
                n_jobs=-1,
                **kwargs
            )
            self.model_name = "随机森林"

        self.model = Pipeline([
            ('preprocessor', self.preprocessor),
            ('classifier', classifier)
        ])

        self.model.fit(X_train, y_train)
        self.is_fitted = True

        # 预测测试集
        self.y_pred = self.model.predict(self.X_test)
        self.y_proba = self.model.predict_proba(self.X_test)[:, 1]

        logger.info(f"模型训练完成: {self.model_name}")
        return {"model_name": self.model_name, "status": "trained"}

    def evaluate(self) -> Dict[str, Any]:
        """评估模型，返回完整指标"""
        if not self.is_fitted:
            raise MLError("模型未训练")

        y_test = self.y_test
        y_pred = self.y_pred
        y_proba = self.y_proba

        acc = accuracy_score(y_test, y_pred)
        prec = precision_score(y_test, y_pred, zero_division=0)
        rec = recall_score(y_test, y_pred, zero_division=0)
        f1 = f1_score(y_test, y_pred, zero_division=0)

        # 混淆矩阵
        cm = confusion_matrix(y_test, y_pred)
        tn, fp, fn, tp = cm.ravel() if cm.size == 4 else (0, 0, 0, 0)

        # ROC-AUC
        try:
            roc_auc = roc_auc_score(y_test, y_proba)
            fpr, tpr, roc_thresholds = roc_curve(y_test, y_proba)
        except Exception:
            roc_auc = 0.0
            fpr, tpr, roc_thresholds = [0], [0], [0]

        # PR-AUC
        try:
            pr_auc = average_precision_score(y_test, y_proba)
            precision_curve, recall_curve, pr_thresholds = precision_recall_curve(y_test, y_proba)
        except Exception:
            pr_auc = 0.0
            precision_curve, recall_curve, pr_thresholds = [0], [0], [0]

        return {
            "model_name": self.model_name,
            "accuracy": round(float(acc), 4),
            "precision": round(float(prec), 4),
            "recall": round(float(rec), 4),
            "f1_score": round(float(f1), 4),
            "roc_auc": round(float(roc_auc), 4),
            "pr_auc": round(float(pr_auc), 4),
            "confusion_matrix": {
                "tn": int(tn), "fp": int(fp),
                "fn": int(fn), "tp": int(tp),
                "matrix": cm.tolist()
            },
            "roc_curve": {
                "fpr": fpr[:100].tolist(),
                "tpr": tpr[:100].tolist(),
                "thresholds": roc_thresholds[:100].tolist()
            },
            "pr_curve": {
                "precision": precision_curve[:100].tolist(),
                "recall": recall_curve[:100].tolist(),
                "thresholds": pr_thresholds[:100].tolist() if len(pr_thresholds) > 0 else []
            },
            "classification_report": classification_report(
                y_test, y_pred, target_names=['<=50K', '>50K'], output_dict=True
            ),
            "training_stats": self.training_stats,
        }

    def feature_importance(self, top_n: int = 15) -> Dict[str, Any]:
        """获取特征重要性"""
        if not self.is_fitted:
            raise MLError("模型未训练")

        classifier = self.model.named_steps['classifier']

        if hasattr(classifier, 'feature_importances_'):
            importances = classifier.feature_importances_
        elif hasattr(classifier, 'coef_'):
            importances = np.abs(classifier.coef_[0])
        else:
            raise MLError("模型不支持特征重要性")

        # 获取预处理器输出的特征名
        try:
            ohe = self.model.named_steps['preprocessor'].named_transformers_['cat']
            cat_features = ohe.get_feature_names_out().tolist()
            num_features = self.training_stats.get('numeric_features', [])
            all_features = num_features + cat_features
        except Exception:
            all_features = [f"feature_{i}" for i in range(len(importances))]

        # 按重要性排序
        indices = np.argsort(importances)[::-1][:top_n]
        top_features = []
        for idx in indices:
            if idx < len(all_features):
                top_features.append({
                    "feature": all_features[idx],
                    "importance": round(float(importances[idx]), 6)
                })

        return {
            "model_name": self.model_name,
            "top_features": top_features,
            "feature_names": all_features[:len(importances)],
            "importances": importances.tolist()
        }

    def fairness_audit(
        self,
        sensitive_cols: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        公平性审计：按敏感属性分组计算指标

        Args:
            sensitive_cols: 敏感属性列名列表，默认 ['sex', 'race']
        """
        if not self.is_fitted:
            raise MLError("模型未训练")

        if sensitive_cols is None:
            sensitive_cols = ['sex', 'race']

        y_test = self.y_test
        y_pred = self.y_pred

        results = {}

        for col in sensitive_cols:
            if col not in self.X_test.columns:
                logger.warning(f"敏感属性 '{col}' 不在测试集中，跳过")
                continue

            group_metrics = []
            groups = self.X_test[col].unique()

            for group in groups:
                mask = self.X_test[col] == group
                if mask.sum() < 5:
                    continue

                y_true_g = y_test[mask]
                y_pred_g = y_pred[mask]

                tn_g = ((y_true_g == 0) & (y_pred_g == 0)).sum()
                fp_g = ((y_true_g == 0) & (y_pred_g == 1)).sum()
                fn_g = ((y_true_g == 1) & (y_pred_g == 0)).sum()
                tp_g = ((y_true_g == 1) & (y_pred_g == 1)).sum()

                total_g = len(y_true_g)
                tpr_g = tp_g / (tp_g + fn_g) if (tp_g + fn_g) > 0 else 0
                fpr_g = fp_g / (fp_g + tn_g) if (fp_g + tn_g) > 0 else 0
                fnr_g = fn_g / (fn_g + tp_g) if (fn_g + tp_g) > 0 else 0
                acc_g = (tp_g + tn_g) / total_g if total_g > 0 else 0

                group_metrics.append({
                    "group": str(group).strip(),
                    "count": int(total_g),
                    "tp": int(tp_g), "fp": int(fp_g),
                    "fn": int(fn_g), "tn": int(tn_g),
                    "tpr": round(float(tpr_g), 4),
                    "fpr": round(float(fpr_g), 4),
                    "fnr": round(float(fnr_g), 4),
                    "accuracy": round(float(acc_g), 4),
                })

            if group_metrics:
                # 计算组间差异
                tprs = [g["tpr"] for g in group_metrics]
                fprs = [g["fpr"] for g in group_metrics]
                results[col] = {
                    "groups": group_metrics,
                    "tpr_gap": round(float(max(tprs) - min(tprs)), 4) if tprs else 0,
                    "fpr_gap": round(float(max(fprs) - min(fprs)), 4) if fprs else 0,
                }

        return {
            "model_name": self.model_name,
            "sensitive_attributes": results,
            "warning": "TPR/FPR 差异大于 0.1 可能表明公平性问题" if any(
                r.get("tpr_gap", 0) > 0.1 or r.get("fpr_gap", 0) > 0.1
                for r in results.values()
            ) else None
        }

    def cross_validate(
        self,
        X_train: pd.DataFrame,
        y_train: pd.Series,
        cv: int = 5
    ) -> Dict[str, Any]:
        """5 折交叉验证"""
        if self.model is None:
            raise MLError("请先调用 train()")

        skf = StratifiedKFold(n_splits=cv, shuffle=True, random_state=42)
        scores = cross_val_score(
            self.model, X_train, y_train,
            cv=skf, scoring='f1', n_jobs=-1
        )

        return {
            "cv_folds": cv,
            "mean_f1": round(float(scores.mean()), 4),
            "std_f1": round(float(scores.std()), 4),
            "fold_scores": [round(float(s), 4) for s in scores]
        }

    def get_state(self) -> Dict[str, Any]:
        """获取可序列化的状态（用于 session 持久化）"""
        import pickle
        import base64

        if not self.is_fitted:
            return {"is_fitted": False}

        return {
            "is_fitted": True,
            "model_name": self.model_name,
            "model_pkl": base64.b64encode(pickle.dumps(self.model)).decode('ascii'),
            "target_col": self.target_col,
            "feature_names": self.feature_names,
            "training_stats": self.training_stats,
            "y_test_pkl": base64.b64encode(pickle.dumps(self.y_test)).decode('ascii'),
            "y_pred_pkl": base64.b64encode(pickle.dumps(self.y_pred)).decode('ascii'),
            "y_proba_pkl": base64.b64encode(pickle.dumps(self.y_proba)).decode('ascii'),
        }

    def load_state(self, state: Dict[str, Any]) -> None:
        """从序列化状态恢复"""
        import pickle
        import base64

        if not state.get("is_fitted"):
            return

        self.model = pickle.loads(base64.b64decode(state["model_pkl"]))
        self.model_name = state["model_name"]
        self.target_col = state["target_col"]
        self.feature_names = state["feature_names"]
        self.training_stats = state["training_stats"]
        self.y_test = pickle.loads(base64.b64decode(state["y_test_pkl"]))
        self.y_pred = pickle.loads(base64.b64decode(state["y_pred_pkl"]))
        self.y_proba = pickle.loads(base64.b64decode(state["y_proba_pkl"]))
        self.preprocessor = self.model.named_steps['preprocessor']
        self.is_fitted = True
