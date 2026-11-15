import json
import streamlit as st
from pathlib import Path

st.set_page_config(page_title="ConfidAgent", page_icon="🤖", layout="wide")
st.title("🤖 ConfidAgent Dashboard")

state_path = Path(".confidagent_state.json")
if not state_path.exists():
    st.warning('No run yet. Run `python main.py fix "..." --repo ./demo_repo` first.')
    st.stop()

state = json.loads(state_path.read_text())

# 1. TOP METRICS
col1, col2, col3, col4 = st.columns(4)
tokens_used = state.get('tokens_used', 0)
tokens_baseline = state.get('tokens_baseline', 0)
tokens_saved = tokens_baseline - tokens_used
pct = (tokens_saved / tokens_baseline * 100) if tokens_baseline else 0

col1.metric("Tokens Used", f"{tokens_used:,}")
col2.metric("Naive Baseline", f"{tokens_baseline:,}")
col3.metric("Tokens Saved", f"{tokens_saved:,}", delta=f"{pct:.0f}%")
col4.metric("Cost", f"${state.get('cost_usd', 0):.4f}")

# 2.
st.divider()

# 3. Confidence Scores
st.subheader("🎯 Confidence Scores")
decisions = state.get('decisions', [])
if decisions:
    chart_data = {d.get('name', 'Unknown'): d.get('score', 0) for d in decisions}
    st.bar_chart(chart_data)
else:
    st.info("No decisions recorded")

# 4.
st.divider()

# 5. Tavily Freshness Verification
st.subheader("🌐 Tavily Freshness Verification")
results = state.get('tavily_results', [])
if results:
    for r in results:
        status = r.get('status', 'UNKNOWN')
        icon = '🟢' if status == 'CURRENT' else '🔴' if status == 'STALE' else '🟡'
        st.markdown(f"{icon} **{status}** — {r.get('claim', '')}")
        if r.get('correction'):
            st.caption(f"→ Correction: {r['correction']}")
else:
    st.info("No Tavily results recorded")

# 6.
st.divider()

# 7. Files Modified
st.subheader("📝 Files Modified")
files = state.get('files_modified', [])
if files:
    for f in files:
        st.code(f, language='text')
else:
    st.info("No files modified in this run")

# 8.
st.divider()

# 9. Provider Activity
st.subheader("📊 Provider Activity")
col1, col2 = st.columns(2)
col1.metric("Provider Switches", state.get('provider_switches', 0))
col2.metric("Current Provider", state.get('current_provider', 'unknown'))

# 10.
st.divider()
with st.expander("🔍 Raw state (JSON)"):
    st.json(state)

# Run with: pip install streamlit && streamlit run dashboard.py
# Opens at http://localhost:8501
