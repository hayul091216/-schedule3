import json
import re
import uuid
from datetime import date, datetime, time as dtime, timedelta

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from openai import OpenAI
from streamlit_calendar import calendar


# ============================================================
# 기본 설정
# ============================================================
st.set_page_config(
    page_title="AI 과제 플래너",
    page_icon="🗓️",
    layout="wide"
)

# ============================================================
# CSS
# ============================================================
st.markdown("""
<style>
    .stButton > button {
        border-radius: 8px;
        border: 1px solid #3b82f6 !important;
    }

    div[data-testid="stMetricValue"] {
        color: #1d4ed8;
    }

    .stTextInput > div > div > input,
    .stSelectbox > div > div > div,
    .stDateInput > div > div > input {
        border: 1px solid #93c5fd !important;
        border-radius: 8px;
    }

    div[data-testid="stContainer"],
    div.stExpander {
        border: 1px solid #93c5fd !important;
        border-radius: 12px;
        box-shadow: 0 2px 4px rgba(59, 130, 246, 0.05);
    }

    textarea {
        border: 1px solid #93c5fd !important;
        border-radius: 8px !important;
    }
</style>
""", unsafe_allow_html=True)


UPSTAGE_MODEL = "solar-pro2"

IMPORTANCE_OPTIONS = [
    "낮음",
    "보통",
    "높음",
    "매우 높음"
]

STATUS_COLORS = {
    "예정": "#2563eb",
    "완료": "#16a34a",
    "실패": "#dc2626"
}


# ============================================================
# 세션 상태 초기화
# ============================================================
def init_state():

    if "tasks" not in st.session_state:
        st.session_state.tasks = []

    if "schedule" not in st.session_state:
        st.session_state.schedule = []

    if "api_key" not in st.session_state:
        try:
            st.session_state.api_key = st.secrets.get(
                "UPSTAGE_API_KEY",
                ""
            )
        except Exception:
            st.session_state.api_key = ""

    if "weekly_minutes" not in st.session_state:
        st.session_state.weekly_minutes = 1680

    if "daily_minutes" not in st.session_state:
        st.session_state.daily_minutes = (
            st.session_state.weekly_minutes / 7
        )

    if "weekly_start_times" not in st.session_state:
        st.session_state.weekly_start_times = {
            i: dtime(18, 0)
            for i in range(7)
        }

    if "calendar_view_mode" not in st.session_state:
        st.session_state.calendar_view_mode = "calendar"

    if "selected_date" not in st.session_state:
        st.session_state.selected_date = (
            date.today().strftime("%Y-%m-%d")
        )

    if "show_import" not in st.session_state:
        st.session_state.show_import = False

    if "show_help" not in st.session_state:
        st.session_state.show_help = False


init_state()


# ============================================================
# 유틸 함수
# ============================================================
def format_minutes(minutes: float) -> str:

    total_mins = int(round(minutes))
    hours, mins = divmod(total_mins, 60)

    if hours and mins:
        return f"{hours}시간 {mins}분"

    if hours:
        return f"{hours}시간"

    return f"{mins}분"


def extract_json(raw_text: str) -> dict:

    match = re.search(
        r"\{.*\}",
        raw_text,
        re.DOTALL
    )

    if not match:
        raise ValueError(
            "응답에서 JSON 블록을 찾지 못했습니다."
        )

    return json.loads(match.group(0))


def get_client(api_key: str) -> OpenAI:

    return OpenAI(
        api_key=api_key,
        base_url="https://api.upstage.ai/v1"
    )


def parse_calendar_date(raw: str) -> str:

    raw = raw.strip()

    if re.fullmatch(
        r"\d{4}-\d{2}-\d{2}",
        raw
    ):
        return raw

    normalized = raw.replace(
        "Z",
        "+00:00"
    )

    try:
        dt = datetime.fromisoformat(normalized)

    except ValueError:

        match = re.search(
            r"(\d{4}-\d{2}-\d{2})",
            raw
        )

        return match.group(1) if match else raw

    if (
        dt.tzinfo is not None
        and dt.utcoffset() == timedelta(0)
    ):
        dt = dt + timedelta(hours=9)

    return dt.strftime("%Y-%m-%d")


def mark_overdue_as_failed():

    today = date.today()

    for item in st.session_state.schedule:

        try:

            item_date = datetime.strptime(
                item["date"],
                "%Y-%m-%d"
            ).date()

            if (
                item_date < today
                and item["status"] == "예정"
            ):
                item["status"] = "실패"

        except Exception:
            continue


def get_practice_index(start_date):

    end_date = start_date + timedelta(days=6)

    week_items = []

    for item in st.session_state.schedule:

        try:

            item_date = datetime.strptime(
                item["date"],
                "%Y-%m-%d"
            ).date()

            if start_date <= item_date <= end_date:
                week_items.append(item)

        except Exception:
            continue

    target_minutes = sum(
        int(item["minutes"])
        for item in week_items
    )

    completed_minutes = sum(
        int(item["minutes"])
        for item in week_items
        if item["status"] == "완료"
    )

    if target_minutes == 0:
        score = 0
    else:
        score = round(
            completed_minutes
            / target_minutes
            * 100
        )

    return (
        min(score, 100),
        completed_minutes,
        target_minutes,
        week_items
    )


mark_overdue_as_failed()


# ============================================================
# 환경 설정 모달
# ============================================================
@st.dialog("⚙️ 환경 설정")
def settings_modal():

    st.markdown(
        "Upstage API 키와 일주일간 공부 환경을 설정하세요."
    )

    if "temp_api_key" not in st.session_state:
        st.session_state.temp_api_key = (
            st.session_state.api_key
        )

    if "temp_weekly_mins" not in st.session_state:
        st.session_state.temp_weekly_mins = (
            st.session_state.weekly_minutes
        )

    if "temp_weekly_start_times" not in st.session_state:
        st.session_state.temp_weekly_start_times = (
            st.session_state.weekly_start_times.copy()
        )

    api_key_input = st.text_input(
        "Upstage API Key",
        value=st.session_state.temp_api_key,
        type="password",
        help="console.upstage.ai 에서 발급받은 키"
    )

    st.markdown("---")

    st.markdown(
        "🕒 **일주일간 공부 가능 시간 설정**"
    )

    cur_total = st.session_state.temp_weekly_mins

    cur_h = cur_total // 60
    cur_m = cur_total % 60

    col_h, col_m = st.columns(2)

    with col_h:

        h_input = st.number_input(
            "시간",
            min_value=0,
            max_value=168,
            value=int(cur_h),
            step=1
        )

    with col_m:

        m_input = st.number_input(
            "분",
            min_value=0,
            max_value=120,
            value=int(cur_m),
            step=10
        )

    if m_input >= 60:

        h_input += m_input // 60
        m_input = m_input % 60

    calculated_weekly_mins = (
        h_input * 60 + m_input
    )

    st.caption("⚡ 프리셋 선택")

    b1, b2, b3, b4, b5 = st.columns(5)

    if b1.button(
        "14시간",
        use_container_width=True,
        key="preset_14"
    ):

        st.session_state.temp_weekly_mins = 14 * 60
        st.rerun()

    if b2.button(
        "21시간",
        use_container_width=True,
        key="preset_21"
    ):

        st.session_state.temp_weekly_mins = 21 * 60
        st.rerun()

    if b3.button(
        "28시간",
        use_container_width=True,
        key="preset_28"
    ):

        st.session_state.temp_weekly_mins = 28 * 60
        st.rerun()

    if b4.button(
        "35시간",
        use_container_width=True,
        key="preset_35"
    ):

        st.session_state.temp_weekly_mins = 35 * 60
        st.rerun()

    if b5.button(
        "42시간",
        use_container_width=True,
        key="preset_42"
    ):

        st.session_state.temp_weekly_mins = 42 * 60
        st.rerun()

    avg_daily_mins = (
        calculated_weekly_mins / 7
    )

    st.markdown(
        f"""
        <div style="
            background:#eff6ff;
            padding:12px 16px;
            border-radius:10px;
            margin-top:10px;
            margin-bottom:10px;
            border:1px solid #93c5fd;
            color:#1e40af;
        ">
            📅 <b>일주일 총:</b>
            {format_minutes(calculated_weekly_mins)}
            <br>
            ⏱️ <b>하루 평균:</b>
            {format_minutes(avg_daily_mins)}
        </div>
        """,
        unsafe_allow_html=True
    )

    st.markdown("---")

    st.markdown(
        "⏰ **요일별 개별 공부 시작 시각 설정**"
    )

    day_names_full = [
        "월요일",
        "화요일",
        "수요일",
        "목요일",
        "금요일",
        "토요일",
        "일요일"
    ]

    for i, d_name in enumerate(day_names_full):

        cur_t = (
            st.session_state
            .temp_weekly_start_times
            .get(i, dtime(18, 0))
        )

        col_d1, col_d2 = st.columns([1, 2])

        with col_d1:
            st.markdown(f"**{d_name}**")

        with col_d2:

            selected_h = st.selectbox(
                f"{d_name} 시작 시각",
                options=list(range(24)),
                index=cur_t.hour,
                format_func=lambda x: f"{x:02d}:00",
                key=f"temp_start_h_{i}",
                label_visibility="collapsed"
            )

            st.session_state.temp_weekly_start_times[i] = (
                dtime(selected_h, 0)
            )

    st.write("")

    if st.button(
        "저장하기",
        type="primary",
        use_container_width=True
    ):

        st.session_state.api_key = api_key_input

        st.session_state.weekly_minutes = (
            calculated_weekly_mins
        )

        st.session_state.daily_minutes = (
            avg_daily_mins
        )

        st.session_state.weekly_start_times = (
            st.session_state
            .temp_weekly_start_times
            .copy()
        )

        for key in [
            "temp_api_key",
            "temp_weekly_mins",
            "temp_weekly_start_times"
        ]:

            if key in st.session_state:
                del st.session_state[key]

        st.success(
            "설정이 저장되었습니다!"
        )

        st.rerun()


# ============================================================
# Upstage API
# ============================================================
def call_solar_plan(
    api_key: str,
    tasks: list,
    daily_minutes: float,
    start_time_str: str,
    user_feedback: str = ""
) -> dict:

    client = get_client(api_key)

    tasks_json = json.dumps(
        [
            {
                "id": t["id"],
                "title": t["title"],
                "deadline": t["deadline"],
                "importance": t["importance"]
            }
            for t in tasks
        ],
        ensure_ascii=False
    )

    feedback_block = ""

    if user_feedback.strip():

        feedback_block = (
            f"\n사용자가 기존 일정에 대해 남긴 의견: "
            f"{user_feedback}\n"
            "이 의견을 반영해서 일정을 조정해줘."
        )

    system_prompt = f"""
너는 학생의 과제/공부 계획을 짜주는 AI 플래너야.

오늘 날짜: {date.today()}
참고 공부 시작 시각: {start_time_str}
하루 최대 공부 가능 시간 (평균): {round(daily_minutes)}분

할 일:
{tasks_json}

규칙:

1. 각 할 일마다 현실적인 예상 소요시간
(estimated_minutes, 10의 배수 정수)을 산정해.

2. 각 할 일마다 한두 문장짜리
피드백(feedback)을 줘.

3. 오늘부터 각 할 일의 마감일까지,
하루 평균 공부 시간을 넘지 않는 선에서
일정을 배분해.

4. 마감이 임박하거나 중요도가 높은
항목을 우선 배치해.

5. minutes 값은 반드시 10의 배수 정수.

{feedback_block}

6. 설명 없이 아래 JSON 형식 하나만 출력해.

JSON 형식:

{{
  "tasks": [
    {{
      "id": "할일ID",
      "estimated_minutes": 정수,
      "feedback": "문장"
    }}
  ],
  "schedule": [
    {{
      "task_id": "할일ID",
      "date": "YYYY-MM-DD",
      "minutes": 정수
    }}
  ]
}}
"""

    response = client.chat.completions.create(
        model=UPSTAGE_MODEL,
        messages=[
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": "위 조건대로 계획을 세워줘."
            }
        ],
        temperature=0.3
    )

    raw = response.choices[0].message.content.strip()

    data = extract_json(raw)

    for t in data.get("tasks", []):

        t["estimated_minutes"] = (
            round(
                float(t["estimated_minutes"]) / 10
            ) * 10
        )

    for s in data.get("schedule", []):

        s["minutes"] = (
            round(
                float(s["minutes"]) / 10
            ) * 10
        )

    return data


def apply_plan_result(data: dict):

    task_by_id = {
        t["id"]: t
        for t in st.session_state.tasks
    }

    for t in data.get("tasks", []):

        if t["id"] in task_by_id:

            task_by_id[t["id"]]["est_minutes"] = int(
                t["estimated_minutes"]
            )

            task_by_id[t["id"]]["feedback"] = (
                t["feedback"]
            )

    new_schedule = []

    for s in data.get("schedule", []):

        task = task_by_id.get(
            s["task_id"]
        )

        if not task:
            continue

        new_schedule.append(
            {
                "id": str(uuid.uuid4()),
                "task_id": s["task_id"],
                "title": task["title"],
                "date": s["date"],
                "minutes": int(s["minutes"]),
                "status": "예정"
            }
        )

    st.session_state.schedule = new_schedule


# ============================================================
# 헤더
# ============================================================
c_h1, c_h2 = st.columns([6, 1])

with c_h1:

    st.markdown(
        "### 🗓️ AI 과제 플래너"
    )

    st.caption(
        "과제를 분석하고 최적의 계획을 세워드려요"
    )

with c_h2:

    st.markdown(
        f"""
        <div style="
            text-align:right;
            font-size:0.9em;
            color:#1e3a8a;
            padding-top:10px;
            font-weight:600;
        ">
            ☀️ {date.today().strftime("%Y년 %m월 %d일 (%a)")}
        </div>
        """,
        unsafe_allow_html=True
    )


# ============================================================
# 상단 버튼
# ============================================================
btn_save, btn_import, btn_help, btn_reset = st.columns(4)


with btn_save:

    save_data = {
        "tasks": st.session_state.tasks,
        "schedule": st.session_state.schedule
    }

    save_json = json.dumps(
        save_data,
        ensure_ascii=False,
        indent=2
    )

    st.download_button(
        "💾 저장",
        data=save_json,
        file_name="AI_과제플래너.json",
        mime="application/json",
        use_container_width=True
    )


with btn_import:

    if st.button(
        "📂 불러오기",
        use_container_width=True
    ):

        st.session_state.show_import = (
            not st.session_state.show_import
        )

        st.rerun()


with btn_help:

    if st.button(
        "📖 사용방법",
        use_container_width=True
    ):

        st.session_state.show_help = (
            not st.session_state.show_help
        )

        st.rerun()


with btn_reset:

    if st.button(
        "🗑️ 전체 초기화",
        use_container_width=True
    ):

        st.session_state.tasks = []
        st.session_state.schedule = []

        st.success(
            "모든 데이터가 초기화되었습니다."
        )

        st.rerun()


# ============================================================
# 불러오기
# ============================================================
if st.session_state.show_import:

    with st.container(border=True):

        st.markdown(
            "**📂 저장한 일정 불러오기**"
        )

        uploaded_file = st.file_uploader(
            "JSON 파일 선택",
            type=["json"],
            key="schedule_uploader"
        )

        if uploaded_file is not None:

            if st.button(
                "📥 불러오기 적용",
                key="apply_import"
            ):

                try:

                    data = json.load(
                        uploaded_file
                    )

                    loaded_tasks = data.get(
                        "tasks",
                        []
                    )

                    loaded_schedule = data.get(
                        "schedule",
                        []
                    )

                    if (
                        not isinstance(
                            loaded_tasks,
                            list
                        )
                        or
                        not isinstance(
                            loaded_schedule,
                            list
                        )
                    ):
                        raise ValueError(
                            "파일 형식이 올바르지 않습니다."
                        )

                    st.session_state.tasks = (
                        loaded_tasks
                    )

                    st.session_state.schedule = (
                        loaded_schedule
                    )

                    st.session_state.show_import = False

                    st.success(
                        "✅ 저장된 일정을 불러왔습니다."
                    )

                    st.rerun()

                except Exception as error:

                    st.error(
                        "파일을 불러오지 못했습니다."
                    )

                    st.code(str(error))


# ============================================================
# 사용방법
# ============================================================
if st.session_state.show_help:

    with st.container(border=True):

        st.markdown("""
#### 📖 AI 과제 플래너 사용방법

**① 할 일 입력** — 할 일 이름, 마감일, 중요도를 입력합니다.

**② 하루 공부 시간 설정** — 사이드바의 환경 설정에서 일주일 공부 가능 시간과 요일별 시작 시각을 정합니다.

**③ AI 일정 생성** — 입력한 과제의 중요도와 마감일을 분석해 AI가 예상 소요시간과 피드백을 계산합니다.

**④ 날짜별 일정 배분** — AI가 예상 시간을 마감일까지 여러 날짜에 나누어 배정합니다.

**⑤ 캘린더 확인 및 수정** — 캘린더에서 날짜를 클릭하면 그날 일정을 자세히 보고 직접 수정할 수 있습니다.

**⑥ 완료/실패 표시** — 일정을 완료로 표시하거나, 마감이 지나면 자동으로 실패 처리됩니다.

**⑦ 저장 / 불러오기** — 상단 💾 저장으로 현재 과제·일정을 JSON으로 내려받고, 📂 불러오기로 다시 불러올 수 있습니다.
""")


# ============================================================
# 오늘 요약 계산
# ============================================================
today_str = date.today().strftime("%Y-%m-%d")

today_items = [
    x
    for x in st.session_state.schedule
    if x["date"] == today_str
]

today_planned_count = len(today_items)

today_total_mins = sum(
    x["minutes"]
    for x in today_items
)

completed_items = [
    x
    for x in today_items
    if x["status"] == "완료"
]

completed_count = len(completed_items)

completed_mins = sum(
    x["minutes"]
    for x in completed_items
)

upcoming_deadline_count = 0

for t in st.session_state.tasks:

    try:

        d_date = datetime.strptime(
            t["deadline"],
            "%Y-%m-%d"
        ).date()

        if 0 <= (
            d_date - date.today()
        ).days <= 7:

            upcoming_deadline_count += 1

    except Exception:
        pass

rem_mins = max(
    0,
    today_total_mins - completed_mins
)

ratio = (
    completed_mins / today_total_mins
    if today_total_mins > 0
    else 0
)


# ============================================================
# 메트릭
# ============================================================
col_m1, col_m2, col_m3, col_m4 = st.columns(4)


with col_m1:

    with st.container(border=True):

        st.markdown(
            "오늘 예정된 공부"
        )

        st.markdown(
            f"### **{today_planned_count}개**"
        )

        st.caption(
            format_minutes(today_total_mins)
        )


with col_m2:

    with st.container(border=True):

        st.markdown(
            "완료한 공부"
        )

        st.markdown(
            f"### **{completed_count}개**"
        )

        st.caption(
            format_minutes(completed_mins)
        )


with col_m3:

    with st.container(border=True):

        st.markdown(
            "남은 공부 시간"
        )

        st.markdown(
            f"### **{format_minutes(rem_mins)}**"
        )

        st.caption(
            f"({int(ratio * 100)}%)"
        )


with col_m4:

    with st.container(border=True):

        st.markdown(
            "다가오는 마감"
        )

        st.markdown(
            f"### **{upcoming_deadline_count}개**"
        )

        st.caption(
            "7일 이내"
        )


st.write("")


# ============================================================
# 사이드바
# ============================================================
with st.sidebar:

    st.markdown(
        "### 🗓️ AI 과제 플래너"
    )

    st.caption(
        "스마트 플래너"
    )

    st.divider()

    st.subheader("⚙️ 설정")

    if st.button(
        "⚙️ 환경 설정 열기",
        use_container_width=True,
        type="secondary"
    ):

        settings_modal()

    if st.session_state.api_key:

        st.success(
            "API 키가 설정되어 있어요"
        )

    else:

        st.warning(
            "API 키를 설정해주세요."
        )

    st.markdown(
        f"**일주일 공부 시간**: "
        f"{format_minutes(st.session_state.weekly_minutes)}"
    )

    today_wday = date.today().weekday()

    today_start_t = (
        st.session_state.weekly_start_times
        .get(
            today_wday,
            dtime(18, 0)
        )
    )

    day_kr = [
        "월",
        "화",
        "수",
        "목",
        "금",
        "토",
        "일"
    ][today_wday]

    st.markdown(
        f"**오늘({day_kr}) 시작 시각**: "
        f"{today_start_t.strftime('%H:%M')}"
    )

    st.divider()

    st.subheader("오늘 요약")

    st.write(
        f"- 예정된 공부: **{today_planned_count}개**"
    )

    st.write(
        f"- 총 공부 시간: **{format_minutes(today_total_mins)}**"
    )

    st.write(
        f"- 남은 공부 시간: **{format_minutes(rem_mins)}**"
    )

    st.progress(
        min(ratio, 1.0)
    )

    csv_data = (
        pd.DataFrame(
            st.session_state.schedule
        ).to_csv(
            index=False
        ).encode("utf-8-sig")
        if st.session_state.schedule
        else None
    )

    if csv_data:

        st.write("")

        st.download_button(
            "📥 일정 CSV 다운로드",
            csv_data,
            "schedule.csv",
            "text/csv",
            use_container_width=True
        )

    st.divider()

    st.info(
        "💡 **Tip**\n\n"
        "효율적으로 일정을 관리해보세요!"
    )


# ============================================================
# 메인 탭
# ============================================================
tab_tasks, tab_calendar, tab_alarm = st.tabs(
    [
        "📝 할 일 관리",
        "📅 캘린더",
        "🔔 알림"
    ]
)


# ============================================================
# 할 일 관리
# ============================================================
with tab_tasks:

    st.subheader("새 할 일 추가")

    with st.form(
        "add_task_form",
        clear_on_submit=True
    ):

        c1, c2, c3 = st.columns(
            [2, 1, 1]
        )

        title = c1.text_input(
            "할 일 이름",
            placeholder="예: 물리 발표 준비"
        )

        deadline = c2.date_input(
            "마감일",
            value=date.today()
            + timedelta(days=3),
            min_value=date.today(),
            format="YYYY/MM/DD"
        )

        importance = c3.selectbox(
            "중요도",
            IMPORTANCE_OPTIONS,
            index=1
        )

        submitted = st.form_submit_button(
            "추가",
            type="primary"
        )

        if submitted:

            if not title.strip():

                st.error(
                    "할 일 이름을 입력해주세요."
                )

            elif deadline < date.today():

                st.error(
                    "마감일은 오늘 이전으로 설정할 수 없습니다."
                )

            else:

                st.session_state.tasks.append(
                    {
                        "id": str(uuid.uuid4()),
                        "title": title.strip(),
                        "deadline": deadline.strftime(
                            "%Y-%m-%d"
                        ),
                        "importance": importance,
                        "est_minutes": None,
                        "feedback": None
                    }
                )

                st.rerun()


    st.divider()

    st.subheader(
        "할 일 목록"
    )

    if not st.session_state.tasks:

        st.info(
            "아직 등록된 할 일이 없어요. "
            "위에서 추가해보세요."
        )

    else:

        for t in st.session_state.tasks:

            with st.container(
                border=True
            ):

                c1, c2 = st.columns(
                    [4, 1]
                )

                with c1:

                    st.markdown(
                        f"**{t['title']}** · "
                        f"마감 {t['deadline']} · "
                        f"중요도 {t['importance']}"
                    )

                    if t["est_minutes"] is not None:

                        st.caption(
                            "AI 예상 소요시간: "
                            + format_minutes(
                                t["est_minutes"]
                            )
                        )

                    if t["feedback"]:

                        st.info(
                            t["feedback"],
                            icon="💡"
                        )

                with c2:

                    if st.button(
                        "삭제",
                        key=f"del_{t['id']}"
                    ):

                        st.session_state.tasks = [
                            x
                            for x in st.session_state.tasks
                            if x["id"] != t["id"]
                        ]

                        st.session_state.schedule = [
                            x
                            for x in st.session_state.schedule
                            if x["task_id"] != t["id"]
                        ]

                        st.rerun()


        st.divider()

        st.subheader(
            "💬 일정 피드백"
        )

        st.caption(
            "일정을 생성하거나 피드백을 반영해 "
            "일정을 조정할 수 있습니다."
        )

        feedback_text = st.text_area(
            "사용자 피드백 (선택 사항)",
            placeholder=(
                "예: 수학 공부 시간을 늘려줘\n"
                "주말에는 공부량을 줄여줘\n"
                "영어 과제를 먼저 배치해줘"
            ),
            key="user_feedback_textarea"
        )

        if st.button(
            "일정 생성",
            type="primary",
            use_container_width=True,
            key="generate_plan_btn"
        ):

            if not st.session_state.api_key:

                st.error(
                    "환경 설정에서 Upstage API Key를 "
                    "먼저 입력해주세요."
                )

            elif not st.session_state.tasks:

                st.warning(
                    "먼저 할 일을 추가해주세요."
                )

            else:

                today_wday = date.today().weekday()

                today_start_t = (
                    st.session_state
                    .weekly_start_times
                    .get(
                        today_wday,
                        dtime(18, 0)
                    )
                )

                with st.spinner(
                    "AI가 일정을 생성하는 중..."
                ):

                    try:

                        result = call_solar_plan(
                            st.session_state.api_key,
                            st.session_state.tasks,
                            st.session_state.daily_minutes,
                            today_start_t.strftime(
                                "%H:%M"
                            ),
                            feedback_text.strip()
                        )

                        apply_plan_result(
                            result
                        )

                        st.success(
                            "일정이 성공적으로 생성되었습니다."
                        )

                    except Exception as e:

                        st.error(
                            "일정 생성 중 오류가 발생했습니다: "
                            + str(e)
                        )


# ============================================================
# 캘린더
# ============================================================
with tab_calendar:

    # 디버그 정보
    st.write(
        "DEBUG calendar_view_mode:",
        st.session_state.calendar_view_mode
    )

    st.write(
        "DEBUG schedule 개수:",
        len(st.session_state.schedule)
    )

    if not st.session_state.schedule:

        st.info(
            "아직 생성된 일정이 없어요. "
            "'할 일 관리' 탭에서 먼저 일정을 만들어보세요."
        )

    elif st.session_state.calendar_view_mode == "calendar":

        # ====================================================
        # 중요:
        # 기존 st.columns() 안에 calendar를 넣지 않음
        # ====================================================

        st.subheader(
            "📅 월간 캘린더"
        )

        events = []

        for item in st.session_state.schedule:

            color = STATUS_COLORS.get(
                item["status"],
                "#2563eb"
            )

            events.append(
                {
                    "id": item["id"],
                    "title": (
                        f"[{item['status']}] "
                        f"{item['title']} "
                        f"({format_minutes(item['minutes'])})"
                    ),
                    "start": item["date"],
                    "end": item["date"],
                    "backgroundColor": color,
                    "borderColor": color
                }
            )

        cal_options = {
            "initialView": "dayGridMonth",
            "headerToolbar": {
                "left": "prev,next today",
                "center": "title",
                "right": "dayGridMonth,listMonth"
            },
            "locale": "ko",
            "height": 600,
            "selectable": True,
            "editable": False
        }

        st.write(
            "🔥 CALENDAR 함수 실행 직전"
        )

        try:

            cal_state = calendar(
                events=events,
                options=cal_options,
                key="main_calendar_optimized"
            ) or {}

            st.write(
                "🔥 CALENDAR 함수 실행 직후"
            )

            st.write(
                cal_state
            )

        except Exception as e:

            cal_state = {}

            st.error(
                "캘린더를 불러오는 중 오류가 발생했어요: "
                + str(e)
            )

        st.caption(
            "🔵 예정 · 🟢 완료 · 🔴 실패 "
            "(날짜나 일정을 클릭하면 해당 날짜의 상세 일정이 열립니다.)"
        )

        # ====================================================
        # 날짜 / 이벤트 클릭 처리
        # ====================================================
        clicked_date = None

        if isinstance(
            cal_state,
            dict
        ):

            callback_name = cal_state.get(
                "callback"
            )

            if callback_name == "dateClick":

                d_click = cal_state.get(
                    "dateClick",
                    {}
                )

                if isinstance(
                    d_click,
                    dict
                ):

                    clicked_date = (
                        d_click.get("dateStr")
                        or d_click.get("date")
                    )

            elif callback_name == "eventClick":

                e_click = cal_state.get(
                    "eventClick",
                    {}
                )

                if isinstance(
                    e_click,
                    dict
                ):

                    ev = e_click.get(
                        "event",
                        {}
                    )

                    s_val = ev.get(
                        "start"
                    )

                    if s_val:
                        clicked_date = s_val

        if clicked_date:

            st.session_state.selected_date = (
                parse_calendar_date(
                    str(clicked_date)
                )
            )

            st.session_state.calendar_view_mode = (
                "day"
            )

            st.rerun()

        # ====================================================
        # 주간 실천지수
        # 캘린더 아래에 배치
        # ====================================================
        st.divider()

        with st.container(
            border=True
        ):

            st.subheader(
                "📊 주간 실천지수"
            )

            period_option = st.selectbox(
                "조회 기간 선택",
                [
                    "최근 7일 (이번 주)",
                    "1주 전",
                    "2주 전",
                    "3주 전",
                    "4주 전",
                    "특정 주 선택 (날짜 지정)"
                ],
                key="practice_period_option"
            )

            today = date.today()

            if (
                period_option
                == "최근 7일 (이번 주)"
            ):

                end_d = today
                start_d = (
                    end_d
                    - timedelta(days=6)
                )

            elif period_option == "1주 전":

                end_d = (
                    today
                    - timedelta(days=7)
                )

                start_d = (
                    end_d
                    - timedelta(days=6)
                )

            elif period_option == "2주 전":

                end_d = (
                    today
                    - timedelta(days=14)
                )

                start_d = (
                    end_d
                    - timedelta(days=6)
                )

            elif period_option == "3주 전":

                end_d = (
                    today
                    - timedelta(days=21)
                )

                start_d = (
                    end_d
                    - timedelta(days=6)
                )

            elif period_option == "4주 전":

                end_d = (
                    today
                    - timedelta(days=28)
                )

                start_d = (
                    end_d
                    - timedelta(days=6)
                )

            else:

                custom_start = st.date_input(
                    "시작일 선택 (7일간)",
                    value=(
                        today
                        - timedelta(days=6)
                    ),
                    key="practice_custom_start"
                )

                start_d = custom_start

                end_d = (
                    custom_start
                    + timedelta(days=6)
                )

            weekly_items = []

            for x in st.session_state.schedule:

                try:

                    x_date = datetime.strptime(
                        x["date"],
                        "%Y-%m-%d"
                    ).date()

                    if (
                        start_d
                        <= x_date
                        <= end_d
                    ):

                        weekly_items.append(x)

                except Exception:
                    continue

            total_weekly_min = sum(
                x["minutes"]
                for x in weekly_items
            )

            done_weekly_min = sum(
                x["minutes"]
                for x in weekly_items
                if x["status"] == "완료"
            )

            weekly_score = (
                round(
                    done_weekly_min
                    / total_weekly_min
                    * 100
                )
                if total_weekly_min > 0
                else 0
            )

            st.metric(
                label="실천 점수",
                value=f"{weekly_score}점 / 100점"
            )

            st.progress(
                min(
                    max(
                        weekly_score,
                        0
                    ),
                    100
                ) / 100
            )

            st.caption(
                f"📅 대상 기간: "
                f"{start_d.strftime('%m/%d')} ~ "
                f"{end_d.strftime('%m/%d')}"
            )

            st.write(
                f"✅ 완료: **{format_minutes(done_weekly_min)}**"
            )

            st.write(
                f"🎯 목표: **{format_minutes(total_weekly_min)}**"
            )

            if total_weekly_min == 0:

                st.info(
                    "해당 기간에 설정된 일정이 없습니다."
                )

            elif weekly_score >= 80:

                st.success(
                    "🎉 대단해요! 목표를 성실히 실천했습니다!"
                )

            elif weekly_score >= 50:

                st.info(
                    "👍 잘했어요! 조금만 더 분발해봅시다!"
                )

            else:

                st.warning(
                    "💪 아직 기회가 있어요! 조금 더 힘내봐요!"
                )


    # ========================================================
    # 날짜 상세 화면
    # ========================================================
    else:

        if st.button(
            "← 되돌아가기",
            key="back_calendar",
            type="primary"
        ):

            st.session_state.calendar_view_mode = (
                "calendar"
            )

            st.rerun()

        sel_date = (
            st.session_state.selected_date
        )

        sel_dt = datetime.strptime(
            sel_date,
            "%Y-%m-%d"
        ).date()

        wday = sel_dt.weekday()

        day_start_time = (
            st.session_state
            .weekly_start_times
            .get(
                wday,
                dtime(18, 0)
            )
        )

        st.subheader(
            f"📌 {sel_date} "
            f"({['월','화','수','목','금','토','일'][wday]}) "
            f"시간표 및 직접 수정"
        )

        st.caption(
            f"설정된 공부 시작 시각: "
            f"{day_start_time.strftime('%H:%M')} | "
            "아래에서 일정을 직접 수정하거나 삭제할 수 있습니다."
        )

        day_items = [
            x
            for x in st.session_state.schedule
            if x["date"] == sel_date
        ]

        if not day_items:

            st.info(
                "이 날짜엔 예정된 일정이 없어요."
            )

        else:

            cur = datetime.combine(
                sel_dt,
                day_start_time
            )

            for item in day_items:

                begin = cur.strftime(
                    "%H:%M"
                )

                cur_item_mins = int(
                    item["minutes"]
                )

                cur += timedelta(
                    minutes=cur_item_mins
                )

                end = cur.strftime(
                    "%H:%M"
                )

                color = STATUS_COLORS.get(
                    item["status"],
                    "#94a3b8"
                )

                st.markdown(
                    f"""
                    <div style="
                        background:{color}22;
                        border-left:5px solid {color};
                        border-radius:10px;
                        padding:14px 18px;
                        margin-bottom:6px;
                    ">

                        <div style="
                            font-size:0.85em;
                            color:#555;
                        ">
                            {begin} ~ {end}
                            · {item['status']}
                        </div>

                        <div style="
                            font-weight:700;
                            font-size:1.05em;
                            margin-top:3px;
                        ">
                            {item['title']}
                        </div>

                        <div style="
                            font-size:0.85em;
                            color:#777;
                            margin-top:3px;
                        ">
                            공부시간 ·
                            {format_minutes(cur_item_mins)}
                        </div>

                    </div>
                    """,
                    unsafe_allow_html=True
                )

                with st.expander(
                    f"✏️ '{item['title']}' 직접 수정하기"
                ):

                    with st.form(
                        key=f"edit_sch_{item['id']}"
                    ):

                        new_title = st.text_input(
                            "일정 제목",
                            value=item["title"],
                            key=f"et_{item['id']}"
                        )

                        new_date = st.date_input(
                            "날짜 변경",
                            value=datetime.strptime(
                                item["date"],
                                "%Y-%m-%d"
                            ).date(),
                            key=f"ed_{item['id']}"
                        )

                        new_mins = st.number_input(
                            "소요 시간(분)",
                            min_value=10,
                            max_value=600,
                            step=10,
                            value=cur_item_mins,
                            key=f"em_{item['id']}"
                        )

                        new_status = st.selectbox(
                            "상태 변경",
                            [
                                "예정",
                                "완료",
                                "실패"
                            ],
                            index=[
                                "예정",
                                "완료",
                                "실패"
                            ].index(
                                item["status"]
                            ),
                            key=f"es_{item['id']}"
                        )

                        col_s1, col_s2 = st.columns(2)

                        if col_s1.form_submit_button(
                            "수정 저장",
                            type="primary"
                        ):

                            item["title"] = new_title

                            item["date"] = (
                                new_date.strftime(
                                    "%Y-%m-%d"
                                )
                            )

                            item["minutes"] = int(
                                new_mins
                            )

                            item["status"] = (
                                new_status
                            )

                            st.success(
                                "일정이 수정되었습니다!"
                            )

                            st.rerun()

                        if col_s2.form_submit_button(
                            "일정 삭제"
                        ):

                            st.session_state.schedule = [
                                x
                                for x in st.session_state.schedule
                                if x["id"] != item["id"]
                            ]

                            st.success(
                                "일정이 삭제되었습니다!"
                            )

                            st.rerun()


# ============================================================
# 알림
# ============================================================
with tab_alarm:

    st.subheader(
        "오늘 일정 브라우저 알림"
    )

    st.caption(
        "⚠️ 이건 OS(윈도우) 알림이 아니라 "
        "**브라우저 알림**이에요. "
        "이 탭을 열어두고 브라우저 알림 권한을 허용해야 작동해요."
    )

    components.html(
        """
        <script>
        if (
            window.Notification &&
            Notification.permission === 'default'
        ) {
            Notification.requestPermission();
        }
        </script>
        """,
        height=0
    )

    today_date = date.today()

    today_str = (
        today_date.strftime("%Y-%m-%d")
    )

    today_items = [
        x
        for x in st.session_state.schedule
        if x["date"] == today_str
    ]

    if not today_items:

        st.info(
            "오늘 일정이 없어서 알림을 예약할 게 없어요."
        )

    else:

        today_start_t = (
            st.session_state
            .weekly_start_times
            .get(
                today_date.weekday(),
                dtime(18, 0)
            )
        )

        cur = datetime.combine(
            today_date,
            today_start_t
        )

        alarm_items = []

        for item in today_items:

            alarm_items.append(
                {
                    "time": cur.strftime("%H:%M"),
                    "title": item["title"]
                }
            )

            cur += timedelta(
                minutes=item["minutes"]
            )

        st.dataframe(
            pd.DataFrame(
                alarm_items
            ).rename(
                columns={
                    "time": "시작 시각",
                    "title": "할 일"
                }
            ),
            use_container_width=True,
            hide_index=True
        )

        alarm_json = json.dumps(
            alarm_items,
            ensure_ascii=False
        )

        components.html(
            f"""
            <div>

                <button
                    id="notif-btn"
                    style="
                        padding:8px 16px;
                        border-radius:8px;
                        border:none;
                        background:#2563eb;
                        color:white;
                        cursor:pointer;
                        font-weight:600;
                    "
                >
                    브라우저 알림 켜기
                </button>

                <span
                    id="notif-status"
                    style="
                        margin-left:10px;
                        color:#1e3a8a;
                    "
                ></span>

            </div>

            <script>

            const alarms = {alarm_json};

            const fired = new Set();

            const statusEl =
                document.getElementById(
                    'notif-status'
                );

            document
                .getElementById('notif-btn')
                .addEventListener(
                    'click',
                    () => {{

                    Notification
                        .requestPermission()
                        .then(
                            perm => {{

                            if (
                                perm === 'granted'
                            ) {{

                                statusEl.innerText =
                                    '알림이 켜졌어요. '
                                    + '이 탭을 열어두세요.';

                                setInterval(
                                    () => {{

                                    const now =
                                        new Date();

                                    const hh =
                                        String(
                                            now.getHours()
                                        ).padStart(
                                            2,
                                            '0'
                                        );

                                    const mm =
                                        String(
                                            now.getMinutes()
                                        ).padStart(
                                            2,
                                            '0'
                                        );

                                    const nowStr =
                                        hh + ':' + mm;

                                    alarms.forEach(
                                        a => {{

                                        if (
                                            a.time === nowStr
                                            &&
                                            !fired.has(
                                                a.time
                                                + a.title
                                            )
                                        ) {{

                                            fired.add(
                                                a.time
                                                + a.title
                                            );

                                            new Notification(
                                                '공부 시간이에요!',
                                                {{
                                                    body:
                                                        a.title
                                                }}
                                            );

                                        }}

                                    }});

                                }},
                                20000
                                );

                            }} else {{

                                statusEl.innerText =
                                    '알림 권한이 거부됐어요.';

                            }}

                        }});
                    }}
                );

            </script>
            """,
            height=60
        )
