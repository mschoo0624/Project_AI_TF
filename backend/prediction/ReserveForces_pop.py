import os
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression


PROJECT_DIR = Path(__file__).resolve().parent
_configured_data_dir = os.getenv("RESERVE_FORCES_DATA_DIR")
if _configured_data_dir:
    BASE = Path(_configured_data_dir).expanduser()
else:
    _data_dirs = (Path("/mnt/user-data/outputs"), PROJECT_DIR / "dataset", PROJECT_DIR / "data")
    BASE = next((path for path in _data_dirs if path.is_dir()), _data_dirs[-1])


def csv_path(filename: str) -> Path:
    path = BASE / filename
    if not path.is_file():
        raise FileNotFoundError(
            f"데이터셋을 찾을 수 없습니다: {path}\n"
            "CSV 파일을 dataset/ 폴더에 넣거나 RESERVE_FORCES_DATA_DIR 환경변수로 데이터셋 폴더를 지정하세요."
        )
    return path


np.random.seed(42)
RF_TREES = int(os.getenv("RESERVE_FORCES_RF_TREES", "50"))

# ---- 예비군 연령범위 설정 (20~29세) ----
# 실제는 20~29세 남성들 다 예비군이 아니지만, 통계상 5년 단위로 나눠서 20~29세 남성 인구를 근사치로 넣음
AGE_LO, AGE_HI = 20, 29
AGE_SPAN = AGE_HI - AGE_LO + 1  # 10
AGE_BIN_WEIGHT = {"20-24세": 1.0, "25-29세": 1.0}
MIN_COMP = 0.7

# ---- 데이터 로딩 ----
tfr = pd.read_csv(f"{BASE}/전국_합계출산율_TFR.csv").set_index("연도")["합계출산율"]
nat_marriage = pd.read_csv(f"{BASE}/지역별_연간_혼인건수.csv").groupby("연도")["혼인건수"].sum()
age_df = pd.read_csv(f"{BASE}/지역별_연간_초혼연령.csv")
nat_age = age_df[(age_df["지역"] == "전국") & (age_df["구분"] == "아내")].set_index("연도")["초혼연령"]
lfpr = pd.read_csv(f"{BASE}/전국_여성경제활동참가율.csv").set_index("연도")["여성경제활동참가율(%)"]

births = pd.read_csv(f"{BASE}/지역별_연간_출생아수.csv")
male_births_nat = births[(births["구분"] == "남자") & (births["지역"] == "전국")].set_index("연도")["value"]
male_births_reg = births[(births["구분"] == "남자") & (births["지역"] != "전국")].set_index(["지역", "연도"])["value"]
regions = sorted(male_births_reg.index.get_level_values(0).unique())

pop = pd.read_csv(f"{BASE}/지역별_성별_5세연령별_인구_실측.csv", encoding="cp949")
# The supplied KOSIS population file is a wide table (one column per year).
# Normalize it to the tidy schema used by the forecasting pipeline.
if "성별" not in pop.columns:
    year_columns = [c for c in pop.columns if str(c).strip().endswith("년") and str(c).strip().split()[0].isdigit()]
    pop = pop.melt(
        id_vars=["행정구역별", "연령별", "항목"],
        value_vars=year_columns,
        var_name="연도",
        value_name="인구수",
    )
    pop = pop.rename(columns={"행정구역별": "지역", "항목": "성별"})
    pop["연도"] = pop["연도"].str.extract(r"(\d{4})")[0].astype(int)
    pop["인구수"] = pd.to_numeric(pop["인구수"], errors="coerce")


def _weighted_bin_sum(df, value_col):
    """20-24/25-29/30-34세 인구(또는 순이동)를 23-30세 근사 가중치로 합산."""
    sub = df[df["연령별"].isin(AGE_BIN_WEIGHT.keys())].copy()
    sub["가중값"] = sub.apply(lambda r: r[value_col] * AGE_BIN_WEIGHT[r["연령별"]], axis=1) 
    return sub.groupby(["지역", "연도"])["가중값"].sum(min_count=1)


real_target = _weighted_bin_sum(pop[pop["성별"] == "남자"], "인구수") / 10000

mig = pd.read_csv(f"{BASE}/지역별_성별_5세연령별_순이동_실측.csv")
mig_m = mig[(mig["성별"] == "남자") & (mig["항목"] == "순이동자수[명]")]
net_mig = _weighted_bin_sum(mig_m, "값") / 10000

growth_source = BASE / "전국_인구성장률등_주요지표.csv"
if growth_source.is_file():
    growth_rate = pd.read_csv(growth_source)
else:
    growth_rate = pd.read_csv(BASE / "05_주요인구지표_전국_1960_2072_tidy.csv")
growth_rate = growth_rate[growth_rate["지표"] == "인구성장률"].set_index("연도")["값"]
# =====================================================================================
# 1. AI 1 — 미래 출산율(TFR) 예측 using CNN
# =====================================================================================

series = {"TFR": tfr, "혼인건수": nat_marriage, "초혼연령": nat_age, "여성경활율": lfpr}
CHANNELS = ["TFR", "혼인건수", "초혼연령", "여성경활율"]
YEARS = list(range(1970, 2026))
norm = {k: (s.reindex(YEARS).mean(), s.reindex(YEARS).std()) for k, s in series.items()}
WINDOW, KERNEL, FILTERS, HID = 4, 2, 6, 8 # 데이터 길이, 커널 길이. 필터 수, hidden_layer 수
out_len = WINDOW - KERNEL + 1

def relu(x):
    return np.maximum(x, 0)

def forward(p, X):
    N = X.shape[0]
    conv_out = np.zeros((N, out_len, FILTERS))
    for t in range(out_len):
        patch = X[:, t:t + KERNEL, :].reshape(N, -1)
        conv_out[:, t, :] = relu(patch @ p["Wc"] + p["bc"])
    h = relu(conv_out.reshape(N, -1) @ p["W1"] + p["b1"])
    return (h @ p["W2"] + p["b2"]).flatten()

# creates the CNN's starting weights before training
def init_params():
    return {"Wc": np.random.randn(KERNEL * len(CHANNELS), FILTERS) * 0.3, "bc": np.zeros(FILTERS),
            "W1": np.random.randn(out_len * FILTERS, HID) * 0.3, "b1": np.zeros(HID),
            "W2": np.random.randn(HID, 1) * 0.3, "b2": np.zeros(1)}

def flatten_params(p):
    return np.concatenate([p[k].flatten() for k in ["Wc", "bc", "W1", "b1", "W2", "b2"]])

def unflatten_params(flat, shapes):
    p, i = {}, 0
    for k, shp in shapes.items():
        n = int(np.prod(shp)); p[k] = flat[i:i + n].reshape(shp); i += n
    return p

def train_cnn(X, y, iters=250, lr=0.08, seed=42):
    """Train the small CNN with analytic backpropagation + Adam.

    The original prototype estimated every gradient component with finite differences,
    which made application startup unnecessarily expensive. This keeps the same
    architecture, MSE + L2 objective, initialization and optimizer while computing
    exact gradients in one backward pass per iteration.
    """
    np.random.seed(seed)
    p = init_params()
    m = {k: np.zeros_like(v) for k, v in p.items()}
    v = {k: np.zeros_like(v) for k, v in p.items()}
    b1_, b2_, eps = 0.9, 0.999, 1e-8
    n = X.shape[0]

    patches = np.stack(
        [X[:, t:t + KERNEL, :].reshape(n, -1) for t in range(out_len)],
        axis=1,
    )

    for it in range(1, iters + 1):
        zc = np.einsum("ntk,kf->ntf", patches, p["Wc"]) + p["bc"]
        conv = relu(zc)
        conv_flat = conv.reshape(n, -1)
        z1 = conv_flat @ p["W1"] + p["b1"]
        h = relu(z1)
        pred = (h @ p["W2"] + p["b2"]).reshape(-1)

        dpred = (2.0 / n) * (pred - y)
        grad = {}
        grad["W2"] = h.T @ dpred[:, None] + 0.02 * p["W2"]
        grad["b2"] = np.array([dpred.sum()])

        dh = dpred[:, None] @ p["W2"].T
        dz1 = dh * (z1 > 0)
        grad["W1"] = conv_flat.T @ dz1 + 0.02 * p["W1"]
        grad["b1"] = dz1.sum(axis=0)

        dconv = (dz1 @ p["W1"].T).reshape(n, out_len, FILTERS)
        dzc = dconv * (zc > 0)
        grad["Wc"] = np.einsum("ntk,ntf->kf", patches, dzc) + 0.02 * p["Wc"]
        grad["bc"] = dzc.sum(axis=(0, 1))

        for key in p:
            m[key] = b1_ * m[key] + (1 - b1_) * grad[key]
            v[key] = b2_ * v[key] + (1 - b2_) * (grad[key] ** 2)
            mh = m[key] / (1 - b1_ ** it)
            vh = v[key] / (1 - b2_ ** it)
            p[key] -= lr * mh / (np.sqrt(vh) + eps)

    return p

def build_window(target_year, get_fn):
    rows = []
    for back in range(WINDOW, 0, -1):
        y = target_year - back
        vals = []
        for c in CHANNELS:
            v = get_fn(c, y)
            if v is None or pd.isna(v):
                return None
            mu, sd = norm[c]; vals.append((v - mu) / sd)
        rows.append(vals)
    return np.array(rows)

# 1970년부터 2025년까지 각 연도 y
X_list, y_list = [], []
for y in range(1970, 2026):
    w = build_window(y, lambda c, yy: series[c].get(yy))
    tv = tfr.get(y)
    if w is not None and pd.notna(tv):
        X_list.append(w); y_list.append((tv - norm["TFR"][0]) / norm["TFR"][1])

# 실제 학습
p_cnn = train_cnn(np.stack(X_list), np.array(y_list), iters=250, lr=0.08)

future_exog = {"혼인건수": {}, "초혼연령": {}, "여성경활율": {}}
for k in future_exog:
    s = series[k]; last_year = s.dropna().index.max(); last_val = s.loc[last_year]
    delta = s.loc[last_year - 4:last_year].diff().mean(); damping = 0.85
    val, d = last_val, delta
    for y in range(last_year + 1, 2051):
        d *= damping; val += d; future_exog[k][y] = val


def get_val(k, y):
    s = series[k]
    if y in future_exog.get(k, {}) and (pd.isna(s.get(y)) or y > s.dropna().index.max()):
        return future_exog[k][y]
    return s.get(y)

# TFR을 한 해씩 앞으로 밀며 예측
tfr_pred = dict(tfr.dropna())
for y in range(2026, 2051):
    w = build_window(y, lambda c, yy: (tfr_pred.get(yy) if c == "TFR" else get_val(c, yy)))
    if w is None:
        break
    pn = forward(p_cnn, w[None, :, :])[0]
    tfr_pred[y] = max(pn * norm["TFR"][1] + norm["TFR"][0], 0.1)


# =====================================================================================
# 2. [계산 — 코호트 베이스라인] TFR -> 전국/지역별 미래 출생아수
# =====================================================================================

bdf = pd.DataFrame([{"TFR": tfr.get(y), "출생아수": male_births_nat.get(y)} for y in range(1997, 2026)
                     if pd.notna(tfr.get(y)) and pd.notna(male_births_nat.get(y))])
births_model = LinearRegression().fit(bdf[["TFR"]], bdf["출생아수"])
future_nat_births = {y: max(float(births_model.predict(pd.DataFrame({"TFR": [tfr_pred[y]]}))[0]), 10000)
                      for y in range(2026, 2033)}

# 지역별 출생 비중(share) 추세 계산
share_rows = [{"지역": r, "연도": y, "비중": male_births_reg.get((r, y)) / male_births_nat.get(y)}
              for r in regions for y in range(2010, 2026)
              if pd.notna(male_births_reg.get((r, y))) and pd.notna(male_births_nat.get(y)) and male_births_nat.get(y)]
sdf = pd.DataFrame(share_rows)

future_region_births = {}
for region in regions:
    sub = sdf[sdf["지역"] == region].sort_values("연도")
    recent_share = sub["비중"].iloc[-3:].mean()
    if len(sub) >= 5:
        # 지역별 미래 출생아수 = 전국 예측 × 지역 비중 예측
        m = LinearRegression().fit(sub[["연도"]], sub["비중"])
        for y in range(2026, 2033):
            trend = m.predict(pd.DataFrame({"연도": [y]}))[0]
            future_region_births.setdefault(region, {})[y] = max(0.5 * trend + 0.5 * recent_share, 0.001) * future_nat_births[y]
    else:
        for y in range(2026, 2033):
            future_region_births.setdefault(region, {})[y] = recent_share * future_nat_births[y]

def get_male_births(region, year):
    v = male_births_reg.get((region, year))
    return v if pd.notna(v) else future_region_births.get(region, {}).get(year, np.nan)

def cohort_baseline(region, target_year):
    vals = [v for v in (get_male_births(region, target_year - b) for b in range(AGE_LO, AGE_HI + 1)) if pd.notna(v)]
    comp = len(vals) / AGE_SPAN
    if not vals or comp < MIN_COMP:
        return np.nan, comp
    return (np.mean(vals) * AGE_SPAN) / 10000.0, comp

# =====================================================================================
# 3. [AI 2] 순이동 예측 AI (RandomForest)
# =====================================================================================
mig_models = {}
for h in range(1, 30):
    X_rows, y_rows = [], []
    for region in regions:
        years = net_mig.loc[region].index if region in net_mig.index.get_level_values(0) else []
        for t in years:
            fv, lag1, lag5 = net_mig.get((region, t + h)), net_mig.get((region, t - 1)), net_mig.get((region, t - 5)) # 1년 전 5년 전
            gr, v0 = growth_rate.get(t), net_mig.get((region, t))
            if any(pd.isna(x) for x in [fv, lag1, lag5, gr, v0]):
                continue
            X_rows.append({"연도": t, "순이동_올해": v0, "순이동_lag1": lag1, "순이동_lag5": lag5,
                            "전국_인구성장률": gr, "지역": region})
            y_rows.append(fv)
    if len(X_rows) < 15:
        continue
    Xd = pd.get_dummies(pd.DataFrame(X_rows), columns=["지역"])
    m = RandomForestRegressor(n_estimators=RF_TREES, max_depth=4, min_samples_leaf=3, random_state=42, n_jobs=1).fit(Xd, pd.Series(y_rows))
    mig_models[h] = {"model": m, "cols": list(Xd.columns)}

BASE_YEAR = 2023


@lru_cache(maxsize=None)
def get_net_mig(region, year, toggle=0.0):
    """toggle: 그 지역 이동패턴(부호포함)을 ±비율만큼 강화/완화 (예: +0.05 = 유출입 5% 심화)"""
    v = net_mig.get((region, year))
    if pd.notna(v):
        return v
    h = year - BASE_YEAR
    if h not in mig_models:
        base_val = net_mig.get((region, BASE_YEAR))
    else:
        v0, lag1, lag5 = net_mig.get((region, BASE_YEAR)), net_mig.get((region, BASE_YEAR - 1)), net_mig.get((region, BASE_YEAR - 5))
        gr = growth_rate.get(BASE_YEAR)
        if any(pd.isna(x) for x in [v0, lag1, lag5, gr]):
            base_val = net_mig.get((region, BASE_YEAR))
        else:
            rec = {"연도": BASE_YEAR, "순이동_올해": v0, "순이동_lag1": lag1, "순이동_lag5": lag5, "전국_인구성장률": gr}
            for c in mig_models[h]["cols"]:
                if c.startswith("지역_"):
                    rec[c] = 1 if c == f"지역_{region}" else 0
            base_val = mig_models[h]["model"].predict(pd.DataFrame([rec])[mig_models[h]["cols"]])[0]
    return base_val * (1 + toggle)


# =====================================================================================
# [AI 3] gap모델 : 순이동 -> "실거주인구 - 코호트베이스라인"
# =====================================================================================
rows = []
for region in regions:
    for year in range(1993, 2026):
        tgt = real_target.get((region, year)); base, comp = cohort_baseline(region, year)
        if pd.isna(tgt) or pd.isna(base):
            continue
        nm, nm1, nm5 = net_mig.get((region, year)), net_mig.get((region, year - 1)), net_mig.get((region, year - 5))
        if pd.isna(nm) or pd.isna(nm1):
            continue
        rows.append({"지역": region, "연도": year, "gap": tgt - base, "순이동_올해": nm, "순이동_작년": nm1,
                      "순이동_5년전": nm5 if pd.notna(nm5) else nm1})
gdf = pd.DataFrame(rows)
region_dummies = pd.get_dummies(gdf["지역"], prefix="지역")
X_gap = pd.concat([gdf[["연도", "순이동_올해", "순이동_작년", "순이동_5년전"]], region_dummies], axis=1)
gap_model = RandomForestRegressor(n_estimators=RF_TREES, max_depth=4, min_samples_leaf=3, random_state=42, n_jobs=1).fit(X_gap, gdf["gap"])


# =====================================================================================
# 4. 최종 예측 (2024~2052) = 코호트베이스라인 + gap
# =====================================================================================
def predict_population(region, target_year, toggle=0.0):
    base, comp = cohort_baseline(region, target_year)
    if pd.isna(base):
        return None
    nm_now = get_net_mig(region, target_year, toggle)
    nm_1 = get_net_mig(region, target_year - 1, toggle)
    nm_5 = get_net_mig(region, target_year - 5, toggle)
    if pd.isna(nm_now) or pd.isna(nm_1):
        return None
    rec = {"연도": target_year, "순이동_올해": nm_now, "순이동_작년": nm_1, "순이동_5년전": nm_5 if pd.notna(nm_5) else nm_1}
    for c in region_dummies.columns:
        rec[c] = 1 if c == f"지역_{region}" else 0
    x = pd.DataFrame([rec])[list(X_gap.columns)]
    return base + gap_model.predict(x)[0]


if __name__ == "__main__":
    out_rows = []
    for region in regions:
        for target_year in range(2024, 2053):
            pred = predict_population(region, target_year, toggle=0.0)
            out_rows.append({"지역": region, "연도": target_year, "예측(만명)": round(pred, 2) if pred is not None else None})
    final = pd.DataFrame(out_rows).sort_values(["지역", "연도"])
    output_path = BASE / "39_CNN경로_v2_순이동AI_예측_2024_2052.csv"
    final.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"저장 완료: 39_CNN경로_v2_순이동AI_예측_2024_2052.csv ({len(final)}행)")
    holdout_rows = []
    for holdout_year in sorted(gdf["연도"].unique()):
        train = gdf[gdf["연도"] != holdout_year]
        Xtr = pd.concat([train[["연도", "순이동_올해", "순이동_작년", "순이동_5년전"]], region_dummies.loc[train.index]], axis=1)
        m = RandomForestRegressor(n_estimators=RF_TREES, max_depth=4, min_samples_leaf=3, random_state=42, n_jobs=1).fit(Xtr, train["gap"])
        test = gdf[gdf["연도"] == holdout_year]
        Xte = pd.concat([test[["연도", "순이동_올해", "순이동_작년", "순이동_5년전"]], region_dummies.loc[test.index]], axis=1)[Xtr.columns]
        pred_gap = m.predict(Xte)
        for i, (idx, row) in enumerate(test.iterrows()):
            base, comp = cohort_baseline(row["지역"], row["연도"])
            actual = real_target.get((row["지역"], row["연도"]))
            if pd.notna(actual) and actual > 0:
                pred = base + pred_gap[i]
                holdout_rows.append({"연도": holdout_year, "지역": row["지역"], "실제": actual, "예측": pred,
                                      "오차%": (pred - actual) / actual * 100})
    hdf = pd.DataFrame(holdout_rows)
    print(f"\n=== 홀드아웃 검증 (leave-one-year-out, {AGE_LO}-{AGE_HI}세) ===")
    print("연도별 지역 평균 절대오차%:")
    print(hdf.groupby("연도")["오차%"].apply(lambda s: s.abs().mean()).round(2))
    print("전체 지역 평균 절대오차%:", round(hdf["오차%"].abs().mean(), 2))
    nat = hdf.groupby("연도").agg({"실제": "sum", "예측": "sum"})
    nat["오차%"] = (nat["예측"] - nat["실제"]) / nat["실제"] * 100
    print("\n전국 합계 기준 오차%:")
    print(nat.round(1))


SCENARIO_TOGGLES = {
    "outflow_down": -0.05,
    "baseline": 0.0,
    "outflow_up": 0.05,
}


def generate_dashboard_data(start_year=2025, end_year=2052):
    """Generate the JSON-serializable payload consumed by the home forecast dashboard.

    The historical cutoff is 2025. 2025 uses the measured 20-29 male population,
    while 2026 onward uses this module's cohort + migration gap forecast.
    """
    years = list(range(start_year, end_year + 1))
    hist_cutoff = 2025
    dashboard_regions = list(regions) + ["전국"]
    data = {scenario: {} for scenario in SCENARIO_TOGGLES}

    for scenario, toggle in SCENARIO_TOGGLES.items():
        for region in regions:
            values = {}
            for year in years:
                if year <= hist_cutoff:
                    measured = real_target.get((region, year))
                    value = None if pd.isna(measured) else float(measured)
                else:
                    predicted = predict_population(region, year, toggle=toggle)
                    value = None if predicted is None or pd.isna(predicted) else float(predicted)
                values[str(year)] = None if value is None else round(value, 2)
            data[scenario][region] = values

        national = {}
        for year in years:
            region_values = [data[scenario][region][str(year)] for region in regions]
            national[str(year)] = (
                None if any(value is None for value in region_values)
                else round(sum(region_values), 2)
            )
        data[scenario]["전국"] = national

    return {
        "scenarios": list(SCENARIO_TOGGLES),
        "years": years,
        "hist_cutoff": hist_cutoff,
        "regions": dashboard_regions,
        "data": data,
    }
