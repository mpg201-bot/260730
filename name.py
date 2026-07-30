import re
import requests
import pandas as pd
import streamlit as st
import plotly.express as px

st.set_page_config(page_title="전국 학령인구 지도", layout="wide")
st.title("🗺️ 전국 학령인구(8~16세) 지도")
st.caption("시군구별 8~16세 인구 비율 (행정안전부 주민등록 인구) — 고등학교 신입생 모집 홍보 참고용")

POP_URL = "https://raw.githubusercontent.com/greatsong/modudata/main/data/population_yearly.csv.gz"
GEO_URL = "https://raw.githubusercontent.com/greatsong/modudata/main/data/boundaries/sigungu_kr.geojson"


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


# 3. 그중 8~16세 열만 (초등 고학년~중학생, 향후 고등학교 입학 예비군)
target_cols = [c for c in total_cols if age_of(c) is not None and 8 <= age_of(c) <= 16]

# 4. 동 단위로 전체 인구·대상 인구 계산
df["전체인구"] = df[total_cols].sum(axis=1)
df["학령인구"] = df[target_cols].sum(axis=1)

# 5. '코드' 앞 5자리 = 시군구 코드 → 시군구별로 묶어 비율 계산
df["시군구코드"] = df["코드"].str[:5]
grouped = df.groupby("시군구코드")[["전체인구", "학령인구"]].sum().reset_index()
grouped["학령인구비율"] = (grouped["학령인구"] / grouped["전체인구"] * 100).round(2)

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

# 6. 5단계 색 구간 (필요에 따라 실제 데이터 분포에 맞게 조정하세요)
BINS = [0, 6, 8, 10, 12, 100]
LABELS = ["6% 미만", "6~8%", "8~10%", "10~12%", "12% 이상"]
COLORS = {
    "6% 미만": "#edf8e9",
    "6~8%": "#bae4b3",
    "8~10%": "#74c476",
    "10~12%": "#31a354",
    "12% 이상": "#006d2c",
}
merged["단계"] = pd.cut(merged["학령인구비율"], bins=BINS, labels=LABELS, right=False)

# 7. 단계구분도 그리기 (배경 지도 타일 없이 경계만)
fig = px.choropleth(
    merged,
    geojson=geojson,
    locations="시군구코드",
    featureidkey="properties.코드",
    color="단계",
    category_orders={"단계": LABELS},
    color_discrete_map=COLORS,
    hover_name="시군구",
    hover_data={"학령인구비율": True, "시도": True, "시군구코드": False, "단계": False},
    labels={"학령인구비율": "8~16세 비율(%)"},
)
fig.update_geos(fitbounds="locations", visible=False)
fig.update_layout(
    margin=dict(l=0, r=0, t=10, b=0),
    height=700,
    legend_title_text=f"8~16세 비율 ({latest_year}년)",
)
st.plotly_chart(fig, width="stretch")

# 8. 지도 아래 순위 표 두 개
c1, c2 = st.columns(2)
cols = ["시도", "시군구", "학령인구비율"]
with c1:
    st.subheader("🟢 8~16세 비율 높은 곳 10 (모집 유망 지역)")
    st.dataframe(merged.nlargest(10, "학령인구비율")[cols].reset_index(drop=True))
with c2:
    st.subheader("⚪ 8~16세 비율 낮은 곳 10")
    st.dataframe(merged.nsmallest(10, "학령인구비율")[cols].reset_index(drop=True))
