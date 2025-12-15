"""
Samsara Temperature & Door Monitoring Script
---------------------------------------------
Pulls temperature and door data from the Samsara API and graphs it over time.
Auto-refreshes for real-time monitoring.

To run: streamlit run app.py
"""

import streamlit as st
import requests
import plotly.graph_objects as go
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from streamlit_autorefresh import st_autorefresh
import time

# Pacific timezone
PST = ZoneInfo("America/Los_Angeles")

# ============================================================
# CONFIGURATION
# ============================================================

# Samsara API token
API_TOKEN = "samsara_api_bHYDyVDSlCiHJT5TkjpMgtH0sBHLqW"

# API base URL
API_URL = "https://api.samsara.com"

# Sensor IDs (from vehicle config)
TEMP_SENSOR_ID = 278018087981461   # EM31 temperature sensor
DOOR_SENSOR_ID = 278018088610065   # Door sensor

# Refresh every 30 seconds
REFRESH_MS = 30000

# Samsara brand colors
SAMSARA_NAVY = "#00263e"      # Primary
SAMSARA_GRAY = "#515151"      # Secondary
SAMSARA_WHITE = "#ffffff"     # Background


# ============================================================
# API FUNCTIONS
# ============================================================

def get_headers():
    """
    Returns headers for Samsara API calls.
    Uses Bearer token authentication.
    """
    return {
        "Authorization": f"Bearer {API_TOKEN}",
        "Content-Type": "application/json"
    }


def get_current_temperature():
    """
    Gets current temperature from the EM31 sensor.
    Uses v1 sensors API.
    """
    try:
        response = requests.post(
            f"{API_URL}/v1/sensors/temperature",
            headers=get_headers(),
            json={"sensors": [TEMP_SENSOR_ID]},
            timeout=10
        )
        st.session_state.setdefault('debug_log', []).append(
            f"[current_temp] POST /v1/sensors/temperature → {response.status_code}"
        )
        if response.status_code == 200:
            data = response.json()
            sensors = data.get("sensors", [])
            if sensors:
                # Temperature is in milli-Celsius
                milli_c = sensors[0].get("ambientTemperature", 0)
                return milli_c_to_f(milli_c)
        return None
    except Exception as e:
        st.session_state.setdefault('debug_log', []).append(f"[current_temp] ERROR: {e}")
        return None


def get_temperature_history(start_dt, end_dt):
    """
    Gets temperature history from EM31 sensor.
    Returns list of (time, temp) tuples.
    """
    try:
        # Null check
        if start_dt is None or end_dt is None:
            st.session_state.setdefault('debug_log', []).append(
                f"[temp_history] ERROR: start_dt={start_dt}, end_dt={end_dt}"
            )
            return [], []

        start_ms = int(start_dt.timestamp() * 1000)
        end_ms = int(end_dt.timestamp() * 1000)

        response = requests.post(
            f"{API_URL}/v1/sensors/history",
            headers=get_headers(),
            json={
                "startMs": start_ms,
                "endMs": end_ms,
                "stepMs": 60000,  # 1-minute intervals
                "series": [{"field": "ambientTemperature", "widgetId": TEMP_SENSOR_ID}]
            },
            timeout=15
        )
        st.session_state.setdefault('debug_log', []).append(
            f"[temp_history] POST /v1/sensors/history (startMs={start_ms}, endMs={end_ms}) → {response.status_code}"
        )

        if response.status_code == 200:
            data = response.json()
            results = data.get("results", [])
            st.session_state.setdefault('debug_log', []).append(
                f"[temp_history] Got {len(results)} results"
            )

            times = []
            temps = []
            for r in results:
                time_ms = r.get("timeMs")
                series = r.get("series", [])

                # Skip records with missing data
                if time_ms is None:
                    continue

                # Temperature in milli-Celsius (series[0] can be None)
                milli_c = series[0] if series and series[0] is not None else None

                # Skip 0 milli-Celsius readings (no data / sensor off)
                if milli_c is None or milli_c == 0:
                    continue

                ts = datetime.fromtimestamp(time_ms / 1000, tz=timezone.utc)
                ts = ts.astimezone(PST)
                times.append(ts)
                temps.append(milli_c_to_f(milli_c))

            return times, temps
        else:
            st.session_state.setdefault('debug_log', []).append(
                f"[temp_history] Response: {response.text[:200]}"
            )
        return [], []
    except Exception as e:
        import traceback
        st.session_state.setdefault('debug_log', []).append(
            f"[temp_history] ERROR: {e} | Line: {traceback.format_exc().splitlines()[-2]}"
        )
        return [], []


def get_current_door_status():
    """
    Gets current door status.
    Returns True if closed, False if open.
    """
    try:
        response = requests.post(
            f"{API_URL}/v1/sensors/door",
            headers=get_headers(),
            json={"sensors": [DOOR_SENSOR_ID]},
            timeout=10
        )
        st.session_state.setdefault('debug_log', []).append(
            f"[current_door] POST /v1/sensors/door → {response.status_code}"
        )
        if response.status_code == 200:
            data = response.json()
            sensors = data.get("sensors", [])
            if sensors:
                return sensors[0].get("doorClosed", True)
        return None
    except Exception as e:
        st.session_state.setdefault('debug_log', []).append(f"[current_door] ERROR: {e}")
        return None


def get_door_history(start_dt, end_dt):
    """
    Gets door status history.
    Returns list of (time, is_open) tuples.
    """
    try:
        start_ms = int(start_dt.timestamp() * 1000)
        end_ms = int(end_dt.timestamp() * 1000)

        response = requests.post(
            f"{API_URL}/v1/sensors/history",
            headers=get_headers(),
            json={
                "startMs": start_ms,
                "endMs": end_ms,
                "stepMs": 60000,
                "series": [{"field": "doorClosed", "widgetId": DOOR_SENSOR_ID}]
            },
            timeout=15
        )
        st.session_state.setdefault('debug_log', []).append(
            f"[door_history] POST /v1/sensors/history → {response.status_code}"
        )

        if response.status_code == 200:
            data = response.json()
            results = data.get("results", [])

            events = []
            prev_state = None
            for r in results:
                time_ms = r.get("timeMs")
                series = r.get("series", [])

                # Skip records with missing data
                if time_ms is None:
                    continue

                ts = datetime.fromtimestamp(time_ms / 1000, tz=timezone.utc)
                ts = ts.astimezone(PST)

                # doorClosed: 1 = closed, 0 = open (series[0] can be None)
                is_closed = series[0] == 1 if series and series[0] is not None else True
                is_open = not is_closed

                # Only record state changes
                if prev_state is None or is_open != prev_state:
                    events.append((ts, is_open))
                    prev_state = is_open

            return events
        else:
            st.session_state.setdefault('debug_log', []).append(
                f"[door_history] Response: {response.text[:200]}"
            )
        return []
    except Exception as e:
        st.session_state.setdefault('debug_log', []).append(f"[door_history] ERROR: {e}")
        return []


# ============================================================
# DATA PROCESSING
# ============================================================

def milli_c_to_f(milli_c):
    """
    Converts milli-Celsius to Fahrenheit.
    Example: 21398 milli-C = 21.4°C = 70.5°F
    """
    celsius = milli_c / 1000
    return round((celsius * 9/5) + 32, 1)


# ============================================================
# CHART
# ============================================================

def create_chart(times, temps, door_events, min_threshold, max_threshold):
    """
    Creates the temperature vs time chart with door events.

    - Navy line: temperature over time
    - Gray dashed lines: min/max thresholds
    - Light navy shaded regions: door open periods
    """
    fig = go.Figure()

    # Temperature line (Samsara navy)
    fig.add_trace(go.Scatter(
        x=times,
        y=temps,
        mode='lines+markers',
        name='Temperature (°F)',
        line=dict(color=SAMSARA_NAVY, width=2),
        marker=dict(color=SAMSARA_NAVY, size=6)
    ))

    # Min threshold line (gray)
    fig.add_hline(
        y=min_threshold,
        line_dash="dash",
        line_color=SAMSARA_GRAY,
        annotation_text=f"Min: {min_threshold}°F",
        annotation_font_color=SAMSARA_GRAY,
        annotation_position="bottom left"
    )

    # Max threshold line (gray)
    fig.add_hline(
        y=max_threshold,
        line_dash="dash",
        line_color=SAMSARA_GRAY,
        annotation_text=f"Max: {max_threshold}°F",
        annotation_font_color=SAMSARA_GRAY,
        annotation_position="top left"
    )

    # Shaded regions for door open periods (light navy)
    if door_events:
        open_start = None
        for ts, is_open in door_events:
            if is_open and open_start is None:
                # Door opened
                open_start = ts
            elif not is_open and open_start is not None:
                # Door closed - add shaded region
                fig.add_vrect(
                    x0=open_start,
                    x1=ts,
                    fillcolor=SAMSARA_NAVY,
                    opacity=0.15,
                    line_width=0
                )
                open_start = None

        # If door is still open, shade until the last data point
        if open_start is not None and times:
            fig.add_vrect(
                x0=open_start,
                x1=times[-1],
                fillcolor=SAMSARA_NAVY,
                opacity=0.15,
                line_width=0
            )

    # Add invisible trace for legend entry for door open regions
    if door_events and any(is_open for _, is_open in door_events):
        fig.add_trace(go.Scatter(
            x=[None],
            y=[None],
            mode='markers',
            name='Door Open',
            marker=dict(size=15, color=SAMSARA_NAVY, opacity=0.15, symbol='square')
        ))

    fig.update_layout(
        title=dict(
            text="Temperature & Door Events vs Time",
            font=dict(color=SAMSARA_NAVY, size=20)
        ),
        xaxis_title=dict(text="Time (PST)", font=dict(color=SAMSARA_NAVY, size=14)),
        yaxis_title=dict(text="Temperature (°F)", font=dict(color=SAMSARA_NAVY, size=14)),
        height=450,
        plot_bgcolor=SAMSARA_WHITE,
        paper_bgcolor=SAMSARA_WHITE,
        font=dict(color=SAMSARA_NAVY),
        xaxis=dict(
            gridcolor="#e0e0e0",
            linecolor=SAMSARA_NAVY,
            tickfont=dict(color=SAMSARA_NAVY),
            tickformat="%I:%M %p"
        ),
        yaxis=dict(
            gridcolor="#e0e0e0",
            linecolor=SAMSARA_NAVY,
            tickfont=dict(color=SAMSARA_NAVY)
        )
    )

    return fig


# ============================================================
# MAIN APP
# ============================================================

def main():
    st.set_page_config(page_title="Samsara Temp Monitor", layout="wide")

    # Custom CSS for Samsara branding
    st.markdown(f"""
        <style>
        /* Main background */
        .stApp {{
            background-color: {SAMSARA_WHITE};
        }}

        /* Title styling */
        h1 {{
            color: {SAMSARA_NAVY} !important;
        }}

        /* Sidebar */
        [data-testid="stSidebar"] {{
            background-color: {SAMSARA_NAVY};
        }}
        [data-testid="stSidebar"] * {{
            color: {SAMSARA_WHITE} !important;
        }}

        /* Metrics */
        [data-testid="stMetricValue"] {{
            color: {SAMSARA_NAVY} !important;
        }}
        [data-testid="stMetricLabel"] {{
            color: {SAMSARA_GRAY} !important;
        }}

        /* General text */
        .stMarkdown, .stCaption, p {{
            color: {SAMSARA_GRAY};
        }}

        /* Success/error messages */
        .stSuccess {{
            background-color: #e8f4ea;
            color: {SAMSARA_NAVY};
        }}
        </style>
    """, unsafe_allow_html=True)

    # Auto-refresh for real-time
    st_autorefresh(interval=REFRESH_MS, key="refresh")

    # Header with logo
    st.markdown(f"""
        <div style="display: flex; justify-content: space-between; align-items: center;">
            <div>
                <h1 style="margin: 0; color: {SAMSARA_NAVY};">Temperature & Door Monitoring</h1>
                <p style="color: {SAMSARA_GRAY}; margin: 0;">Last updated: {datetime.now(PST).strftime('%I:%M:%S %p %Z')}</p>
            </div>
            <img src="https://cdn.brandfetch.io/id9K2B9C_Z/theme/dark/logo.svg?c=1bxid64Mup7aczewSAYMX&t=1667713430718"
                 alt="Samsara"
                 style="height: 40px;">
        </div>
    """, unsafe_allow_html=True)

    # Sidebar
    st.sidebar.subheader("Settings")

    max_threshold = st.sidebar.number_input("Max Threshold (°F)", min_value=0, max_value=100, value=75)
    min_threshold = st.sidebar.number_input("Min Threshold (°F)", min_value=0, max_value=100, value=35)

    st.sidebar.markdown("**Time Mode**")
    time_mode = st.sidebar.radio("", ["Current (Live)", "Custom Range"], index=0, label_visibility="collapsed")

    if time_mode == "Current (Live)":
        # Live mode - show last N hours up to now
        hours_back = st.sidebar.selectbox("Show last", [1, 2, 4, 8, 12, 24], index=1, format_func=lambda x: f"{x} hour{'s' if x > 1 else ''}")
        now = datetime.now(PST)
        end_dt = now
        start_dt = now - timedelta(hours=hours_back)
    else:
        # Custom range mode
        from datetime import time as dt_time
        import streamlit.components.v1 as components

        today = datetime.now(PST).date()
        now = datetime.now(PST)

        # Time picker CSS/HTML component
        def time_picker_html(key, default_hour=12, default_min=0, default_ampm="AM"):
            return f'''
            <style>
                .time-picker-{key} {{
                    background: {SAMSARA_NAVY};
                    border-radius: 8px;
                    padding: 10px;
                    color: white;
                    font-family: sans-serif;
                }}
                .time-display-{key} {{
                    background: #1a3a4a;
                    border-radius: 4px;
                    padding: 8px 12px;
                    display: flex;
                    align-items: center;
                    margin-bottom: 10px;
                }}
                .time-display-{key} span {{
                    flex: 1;
                    text-align: center;
                    font-size: 16px;
                }}
                .wheels-{key} {{
                    display: flex;
                    gap: 5px;
                    justify-content: center;
                }}
                .wheel-{key} {{
                    background: #1a3a4a;
                    border-radius: 4px;
                    height: 120px;
                    overflow-y: auto;
                    width: 50px;
                    scrollbar-width: thin;
                }}
                .wheel-{key}::-webkit-scrollbar {{
                    width: 4px;
                }}
                .wheel-{key} div {{
                    padding: 8px 4px;
                    text-align: center;
                    cursor: pointer;
                    font-size: 14px;
                }}
                .wheel-{key} div:hover {{
                    background: #2a4a5a;
                }}
                .wheel-{key} div.selected {{
                    background: #e91e63;
                    border-radius: 4px;
                }}
                .ampm-{key} {{
                    display: flex;
                    flex-direction: column;
                    gap: 2px;
                }}
                .ampm-{key} div {{
                    padding: 8px 12px;
                    background: #1a3a4a;
                    border-radius: 4px;
                    cursor: pointer;
                    font-size: 12px;
                }}
                .ampm-{key} div.selected {{
                    background: #e91e63;
                }}
            </style>
            <div class="time-picker-{key}">
                <div class="time-display-{key}">
                    <span id="display-{key}">{default_hour:02d}:{default_min:02d}:00 {default_ampm}</span>
                </div>
                <div class="wheels-{key}">
                    <div class="wheel-{key}" id="hours-{key}">
                        {"".join(f'<div onclick="selectHour{key}({h})" id="h{key}-{h}" class="{"selected" if h == default_hour else ""}">{h}</div>' for h in range(1, 13))}
                    </div>
                    <div class="wheel-{key}" id="mins-{key}">
                        {"".join(f'<div onclick="selectMin{key}({m})" id="m{key}-{m}" class="{"selected" if m == default_min else ""}">{m:02d}</div>' for m in [0, 15, 30, 45])}
                    </div>
                    <div class="ampm-{key}">
                        <div onclick="selectAmPm{key}('AM')" id="am-{key}" class="{"selected" if default_ampm == "AM" else ""}">AM</div>
                        <div onclick="selectAmPm{key}('PM')" id="pm-{key}" class="{"selected" if default_ampm == "PM" else ""}">PM</div>
                    </div>
                </div>
            </div>
            <script>
                var hour{key} = {default_hour}, min{key} = {default_min}, ampm{key} = "{default_ampm}";
                function updateDisplay{key}() {{
                    document.getElementById("display-{key}").innerText =
                        hour{key}.toString().padStart(2,"0") + ":" + min{key}.toString().padStart(2,"0") + ":00 " + ampm{key};
                    window.parent.postMessage({{type: "time-{key}", hour: hour{key}, min: min{key}, ampm: ampm{key}}}, "*");
                }}
                function selectHour{key}(h) {{
                    document.querySelectorAll("#hours-{key} div").forEach(d => d.classList.remove("selected"));
                    document.getElementById("h{key}-" + h).classList.add("selected");
                    hour{key} = h;
                    updateDisplay{key}();
                }}
                function selectMin{key}(m) {{
                    document.querySelectorAll("#mins-{key} div").forEach(d => d.classList.remove("selected"));
                    document.getElementById("m{key}-" + m).classList.add("selected");
                    min{key} = m;
                    updateDisplay{key}();
                }}
                function selectAmPm{key}(ap) {{
                    document.getElementById("am-{key}").classList.remove("selected");
                    document.getElementById("pm-{key}").classList.remove("selected");
                    document.getElementById(ap.toLowerCase() + "-{key}").classList.add("selected");
                    ampm{key} = ap;
                    updateDisplay{key}();
                }}
            </script>
            '''

        # Current hour in 12-hour format for defaults
        now_hour_12 = now.hour % 12 or 12
        now_is_pm = now.hour >= 12

        st.sidebar.markdown("**Start**")
        start_date = st.sidebar.date_input("Date", value=today, max_value=today, key="start_date")
        col1, col2 = st.sidebar.columns([2, 1])
        with col1:
            start_hour = st.selectbox("Hour", range(1, 13), index=11, key="start_hr")
        with col2:
            start_min = st.selectbox("Min", [0, 15, 30, 45], index=0, key="start_min", format_func=lambda x: f":{x:02d}")
        start_ampm = st.sidebar.radio("", ["AM", "PM"], index=0, key="start_ampm", horizontal=True, label_visibility="collapsed")

        st.sidebar.markdown("**End**")
        end_date = st.sidebar.date_input("Date", value=today, max_value=today, key="end_date")
        col3, col4 = st.sidebar.columns([2, 1])
        with col3:
            end_hour = st.selectbox("Hour", range(1, 13), index=now_hour_12 - 1, key="end_hr")
        with col4:
            end_min = st.selectbox("Min", [0, 15, 30, 45], index=0, key="end_min", format_func=lambda x: f":{x:02d}")
        end_ampm = st.sidebar.radio("", ["AM", "PM"], index=1 if now_is_pm else 0, key="end_ampm", horizontal=True, label_visibility="collapsed")

        # Convert 12-hour to 24-hour
        start_hour_24 = start_hour % 12 + (12 if start_ampm == "PM" else 0)
        end_hour_24 = end_hour % 12 + (12 if end_ampm == "PM" else 0)
        start_time = dt_time(start_hour_24, start_min)
        end_time = dt_time(end_hour_24, end_min)

        # Combine date and time into datetime objects
        start_dt = datetime.combine(start_date, start_time, tzinfo=PST)
        end_dt = datetime.combine(end_date, end_time, tzinfo=PST)

    # Validate date range (only needed for custom mode)
    if time_mode == "Custom Range" and start_dt >= end_dt:
        st.warning("Start date/time must be before end date/time")
        return

    # Debug: show the date range being queried
    st.session_state.setdefault('debug_log', []).append(
        f"[query] Range: {start_dt.strftime('%Y-%m-%d %I:%M %p')} → {end_dt.strftime('%Y-%m-%d %I:%M %p')}"
    )

    # Fetch data from Samsara
    with st.spinner("Fetching data..."):
        times, temps = get_temperature_history(start_dt, end_dt)
        door_events = get_door_history(start_dt, end_dt)
        current_temp = get_current_temperature()
        door_closed = get_current_door_status()

    if times:
        st.success(f"Connected to Samsara - {len(times)} readings")

        # Display chart
        fig = create_chart(times, temps, door_events, min_threshold, max_threshold)
        st.plotly_chart(fig, use_container_width=True)

        # Current stats
        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("Current Temp", f"{current_temp}°F" if current_temp else "N/A")
        col2.metric("Min Temp", f"{min(temps)}°F" if temps else "N/A")
        col3.metric("Max Temp", f"{max(temps)}°F" if temps else "N/A")
        col4.metric("Door Status", "Closed" if door_closed else "Open")

        # Time outside range (each reading is ~1 minute apart)
        out_of_range = sum(1 for t in temps if t < min_threshold or t > max_threshold)
        col5.metric("Out of Range", f"{out_of_range} min")
    else:
        st.error("Could not fetch data from Samsara API")

    # Debug panel
    with st.expander("🔧 Debug Log (API Calls)"):
        debug_log = st.session_state.get('debug_log', [])
        if debug_log:
            # Show last 20 entries
            for entry in debug_log[-20:]:
                if "ERROR" in entry or "529" in entry or "4" in entry.split("→")[-1][:1]:
                    st.error(entry)
                else:
                    st.text(entry)
            if st.button("Clear Log"):
                st.session_state['debug_log'] = []
                st.rerun()
        else:
            st.text("No API calls logged yet.")


if __name__ == "__main__":
    main()
