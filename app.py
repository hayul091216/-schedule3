elif st.session_state.calendar_view_mode == "calendar":

    st.subheader("📅 월간 캘린더")

    events = []

    for item in st.session_state.schedule:
        events.append({
            "id": item["id"],
            "title": f"[{item['status']}] {item['title']} ({format_minutes(item['minutes'])})",
            "start": item["date"],
            "end": item["date"],
            "backgroundColor": STATUS_COLORS.get(
                item["status"], "#2563eb"
            ),
            "borderColor": STATUS_COLORS.get(
                item["status"], "#2563eb"
            ),
        })

    cal_options = {
        "initialView": "dayGridMonth",
        "headerToolbar": {
            "left": "prev,next today",
            "center": "title",
            "right": "dayGridMonth,listMonth",
        },
        "locale": "ko",
        "height": 600,
        "selectable": True,
        "editable": False,
    }

    st.write("🔥 CALENDAR 함수 실행 직전")

    try:
        cal_state = calendar(
            events=events,
            options=cal_options,
            key="main_calendar_optimized"
        ) or {}

        st.write("🔥 CALENDAR 함수 실행 직후")
        st.write(cal_state)

    except Exception as e:
        st.error(f"캘린더 오류: {e}")
        cal_state = {}

    st.caption(
        "🔵 예정 · 🟢 완료 · 🔴 실패"
    )
