import re
import requests
import pandas as pd
import streamlit as st
import plotly.express as px

st.set_page_config(page_title="지방 소멸위기 지도", layout="wide")
st.title("🗺️ 지방 소멸위기 지도")
st.caption(
    "시군구별 소멸위기지수 = 63세 이상 인구 ÷ 19~45세 인구 "
    "(행정안전부 주민등록 인구, 지수 3 이상이면 소멸위기 지역으로 분류)"
)

POP_URL = "https://raw.githubusercontent.com/greatsong/modudata/main/data/population_yearly.csv.gz"
GEO_URL = "https://raw.githubusercontent.com/greatsong/modudata/main/data/boundaries/sigungu_kr.geojson"

# 소멸위기 판정 기준: 63세 이상 인구 : 19~45세 인구 = 3 : 1
RISK_THRESHOLD = 3


@st.cache_data(show_spinner="인구 데이터를 불러오는 중입니다...")
def load_population():
    # '코드' 열은 앞자리 0이 사라지지 않게 글자로 읽습니다
    return pd.read_csv(POP_URL, dtype={"코드": str})


@st.cache_data(show_spinner="지도 경계를 불러오는 중입니다...")
def load_geojson():
    return requests.get(GEO_URL, timeout=30).json()


df = load_population()
geojson = load_geojson()

# 1. 가장 최신 연도만 사용
latest_year = int(df["연도"].max())
df = df[df["연도"] == latest_year].copy()

# 2. '계_'로 시작하는 나이 열만 (남_·여_ 열까지 더하면 두 배가 됩니다)
total_cols = [c for c in df.columns if c.startswith("계_")]


def age_of(col):
    m = re.match(r"계_(\d+)세", col)
    return int(m.group(1)) if m else None


# 3. 63세 이상 열 / 19~45세 열 각각 추출
senior_cols = [c for c in total_cols if age_of(c) is not None and age_of(c) >= 63]
prime_cols = [c for c in total_cols if age_of(c) is not None and 19 <= age_of(c) <= 45]

# 4. 동 단위로 전체·고령·핵심생산연령 인구 계산
df["전체인구"] = df[total_cols].sum(axis=1)
df["고령인구_63이상"] = df[senior_cols].sum(axis=1)
df["핵심인구_19_45"] = df[prime_cols].sum(axis=1)

# 5. '코드' 앞 5자리 = 시군구 코드 → 시군구별로 묶어 계산
df["시군구코드"] = df["코드"].str[:5]
grouped = df.groupby("시군구코드")[["전체인구", "고령인구_63이상", "핵심인구_19_45"]].sum().reset_index()

# 6. 소멸위기지수 계산 (핵심인구가 0인 곳은 나눗셈 오류 방지)
grouped["소멸위기지수"] = (
    grouped["고령인구_63이상"] / grouped["핵심인구_19_45"].replace(0, pd.NA)
).round(2)
grouped["소멸위기여부"] = grouped["소멸위기지수"] >= RISK_THRESHOLD

# 경계 파일에서 코드 → 시군구·시도 이름 짝 만들기
names = pd.DataFrame([
    {
        "시군구코드": str(f["properties"]["코드"]),
        "시군구": f["properties"]["시군구"],
        "시도": f["properties"]["시도"],
    }
    for f in geojson["features"]
])
merged = grouped.merge(names, on="시군구코드", how="left")

# 7. 5단계 색 구간 (지수 3을 명확한 경계선으로 포함)
BINS = [0, 1.5, 2, 3, 5, 100]
LABELS = ["1.5 미만(안정)", "1.5~2", "2~3", "3~5(소멸위기)", "5 이상(고위험)"]
COLORS = {
    "1.5 미만(안정)": "#fff7bc",
    "1.5~2": "#fec44f",
    "2~3": "#fe9929",
    "3~5(소멸위기)": "#d95f0e",
    "5 이상(고위험)": "#993404",
}
merged["단계"] = pd.cut(merged["소멸위기지수"], bins=BINS, labels=LABELS, right=False)

# 8. 상단 요약 지표
risk_count = int(merged["소멸위기여부"].sum())
total_count = int(merged["소멸위기여부"].notna().sum())
m1, m2, m3 = st.columns(3)
m1.metric("전체 시군구 수", f"{total_count}개")
m2.metric(f"소멸위기 지역 (지수 {RISK_THRESHOLD} 이상)", f"{risk_count}개")
m3.metric("소멸위기 지역 비율", f"{(risk_count / total_count * 100):.1f}%")

# 9. 단계구분도 그리기
fig = px.choropleth(
    merged,
    geojson=geojson,
    locations="시군구코드",
    featureidkey="properties.코드",
    color="단계",
    category_orders={"단계": LABELS},
    color_discrete_map=COLORS,
    hover_name="시군구",
    hover_data={
        "소멸위기지수": True,
        "고령인구_63이상": True,
        "핵심인구_19_45": True,
        "시도": True,
        "시군구코드": False,
        "단계": False,
    },
    labels={"소멸위기지수": "소멸위기지수(63세이상÷19~45세)"},
)
fig.update_geos(fitbounds="locations", visible=False)
fig.update_layout(
    margin=dict(l=0, r=0, t=10, b=0),
    height=700,
    legend_title_text=f"소멸위기지수 ({latest_year}년, 기준 {RISK_THRESHOLD})",
)
st.plotly_chart(fig, width="stretch")

# 10. 시도별 소멸위기 지역 개수 집계
st.subheader("📊 시도별 소멸위기 지역 개수")
province_summary = (
    merged.groupby("시도")
    .agg(전체시군구수=("시군구", "count"), 소멸위기지역수=("소멸위기여부", "sum"))
    .reset_index()
)
province_summary["소멸위기지역수"] = province_summary["소멸위기지역수"].astype(int)
province_summary["소멸위기비율(%)"] = (
    province_summary["소멸위기지역수"] / province_summary["전체시군구수"] * 100
).round(1)
province_summary = province_summary.sort_values("소멸위기지역수", ascending=False).reset_index(drop=True)
st.dataframe(province_summary, width="stretch")

# 11. 소멸위기 지역 전체 목록 + 위기지수 상위 10곳
st.subheader(f"🚨 소멸위기 지역 전체 목록 (지수 {RISK_THRESHOLD} 이상, {risk_count}개)")
risk_table = merged[merged["소멸위기여부"] == True][
    ["시도", "시군구", "소멸위기지수", "고령인구_63이상", "핵심인구_19_45"]
].sort_values("소멸위기지수", ascending=False).reset_index(drop=True)
st.dataframe(risk_table, width="stretch")

c1, c2 = st.columns(2)
cols = ["시도", "시군구", "소멸위기지수"]
with c1:
    st.subheader("🔴 소멸위기지수 가장 높은 곳 10")
    st.dataframe(merged.nlargest(10, "소멸위기지수")[cols].reset_index(drop=True))
with c2:
    st.subheader("🟢 소멸위기지수 가장 낮은 곳 10 (안정)")
    st.dataframe(merged.nsmallest(10, "소멸위기지수")[cols].reset_index(drop=True))
