## AI-Powered Technical Analysis Dashboard (Gemini 2.0 with Agent & Tavily)

# Libraries
import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import os
import json
from datetime import datetime, timedelta
from phi.agent import Agent
from phi.model.google import Gemini
from phi.tools.tavily import TavilyTools
import tempfile

# Configure API keys securely
os.environ['TAVILY_API_KEY'] = st.secrets['TAVILY_API_KEY']
os.environ['GOOGLE_API_KEY'] = st.secrets['GOOGLE_API_KEY']

# Initialize AI Agent
@st.cache_resource
def get_agent():
    return Agent(
        model=Gemini(id="gemini-2.0-flash-exp"),
        system_prompt="You are a stock market analyst specializing in technical analysis.",
        instructions="Analyze the provided stock data and offer insights using technical indicators.",
        tools=[TavilyTools(api_key=os.getenv("TAVILY_API_KEY"))],
        markdown=True,
    )

agent = get_agent()

# Streamlit UI setup
st.set_page_config(layout="wide")
st.title("AI-Powered Technical Stock Analysis Dashboard")
st.sidebar.header("Configuration")

tickers_input = st.sidebar.text_input("Enter Stock Tickers (comma-separated):", "AAPL,MSFT,GOOG")
tickers = [ticker.strip().upper() for ticker in tickers_input.split(",") if ticker.strip()]

end_date_default = datetime.today()
start_date_default = end_date_default - timedelta(days=365)
start_date = st.sidebar.date_input("Start Date", value=start_date_default)
end_date = st.sidebar.date_input("End Date", value=end_date_default)

st.sidebar.subheader("Technical Indicators")
indicators = st.sidebar.multiselect(
    "Select Indicators:",
    ["20-Day SMA", "20-Day EMA", "20-Day Bollinger Bands", "VWAP"],
    default=["20-Day SMA"]
)

if st.sidebar.button("Fetch Data"):
    stock_data = {}
    for ticker in tickers:
        data = yf.download(ticker, start=start_date, end=end_date)
        if not data.empty:
            stock_data[ticker] = data
        else:
            st.warning(f"No data found for {ticker}.")
    st.session_state["stock_data"] = stock_data
    st.success("Stock data loaded successfully.")

if "stock_data" in st.session_state and st.session_state["stock_data"]:

    def analyze_ticker(ticker, data):
        fig = go.Figure(data=[
            go.Candlestick(
                x=data.index, open=data['Open'], high=data['High'],
                low=data['Low'], close=data['Close'], name="Candlestick"
            )
        ])

        def add_indicator(indicator):
            if indicator == "20-Day SMA":
                fig.add_trace(go.Scatter(x=data.index, y=data['Close'].rolling(window=20).mean(), mode='lines', name='SMA (20)'))
            elif indicator == "20-Day EMA":
                fig.add_trace(go.Scatter(x=data.index, y=data['Close'].ewm(span=20).mean(), mode='lines', name='EMA (20)'))
            elif indicator == "20-Day Bollinger Bands":
                sma = data['Close'].rolling(window=20).mean()
                std = data['Close'].rolling(window=20).std()
                fig.add_trace(go.Scatter(x=data.index, y=sma + 2 * std, mode='lines', name='BB Upper'))
                fig.add_trace(go.Scatter(x=data.index, y=sma - 2 * std, mode='lines', name='BB Lower'))
            elif indicator == "VWAP":
                data['VWAP'] = (data['Close'] * data['Volume']).cumsum() / data['Volume'].cumsum()
                fig.add_trace(go.Scatter(x=data.index, y=data['VWAP'], mode='lines', name='VWAP'))
        
        for ind in indicators:
            add_indicator(ind)
        fig.update_layout(xaxis_rangeslider_visible=False)

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmpfile:
            fig.write_image(tmpfile.name)
            tmpfile_path = tmpfile.name
        with open(tmpfile_path, "rb") as f:
            image_bytes = f.read()
        os.remove(tmpfile_path)

        response = agent.run(
            f"Analyze the stock chart for {ticker} based on technical indicators and provide insights.",
            images=[image_bytes]
        )

        try:
            result = json.loads(response.content)
        except json.JSONDecodeError:
            result = {"action": "Error", "justification": "Could not parse AI response."}

        return fig, result

    tab_names = ["Overall Summary"] + list(st.session_state["stock_data"].keys())
    tabs = st.tabs(tab_names)
    overall_results = []

    for i, ticker in enumerate(st.session_state["stock_data"]):
        data = st.session_state["stock_data"][ticker]
        fig, result = analyze_ticker(ticker, data)
        overall_results.append({"Stock": ticker, "Recommendation": result.get("action", "N/A")})
        
        with tabs[i + 1]:
            st.subheader(f"Analysis for {ticker}")
            st.plotly_chart(fig)
            st.write("**Detailed Justification:**")
            st.write(result.get("justification", "No justification provided."))

    with tabs[0]:
        st.subheader("Overall Structured Recommendations")
        df_summary = pd.DataFrame(overall_results)
        st.table(df_summary)
else:
    st.info("Please fetch stock data using the sidebar.")
