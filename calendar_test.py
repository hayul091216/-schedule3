import streamlit as st
from streamlit_calendar import calendar

st.set_page_config(
    page_title="Calendar Test",
    layout="wide"
)

st.title("📅 캘린더 테스트")

events = [
    {
        "id": "1",
        "title": "테스트 일정",
        "start": "2026-08-14",
    },
    {
        "id": "2",
        "title": "두 번째 일정",
        "start": "2026-08-20",
    },
]

options = {
    "initialView": "dayGridMonth",
    "height": 600,
    "locale": "ko",
}

st.write("BEFORE")

result = calendar(
    events=events,
    options=options,
    key="calendar_test"
)

st.write("AFTER")

st.write(result)
