import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import os
import json
import base64
from datetime import datetime, timedelta
from tempfile import NamedTemporaryFile
from phi.agent import Agent
from phi.model.google import Gemini
from phi.tools.tavily import TavilyTools
from constants import SYSTEM_PROMPT, INSTRUCTIONS

# Streamlit Page Config
st.set_page_config(page_title="AI-Powered Technical Stock Analysis Dashboard", layout="wide")

# API Keys (Ensure secure storage in production)
os.environ['TAVILY_API_KEY'] = st.secrets['TAVILY_API_KEY']
os.environ['GOOGLE_API_KEY'] = st.secrets['GOOGLE_API_KEY']

# Initialize AI Agent and store in session state
if "agent" not in st.session_state:
    st.session_state["agent"] = Agent(
        model=Gemini(id="gemini-2.0-flash-exp"),
        system_prompt=SYSTEM_PROMPT,
        instructions=INSTRUCTIONS,
        tools=[TavilyTools(api_key=os.getenv("TAVILY_API_KEY"))],
        markdown=True,
    )
agent = st.session_state["agent"]

# Streamlit UI
st.title("AI-Powered Technical Stock Analysis Dashboard")
st.sidebar.header("Configuration")

# User Input for Stocks
tickers_input = st.sidebar.text_input("Enter Stock Tickers (comma-separated):", "AAPL,MSFT,GOOG")
tickers = [ticker.strip().upper() for ticker in tickers_input.split(",") if ticker.strip()]

# Date Range Selection
end_date_default = datetime.today()
start_date_default = end_date_default - timedelta(days=365)
start_date = st.sidebar.date_input("Start Date", value=start_date_default)
end_date = st.sidebar.date_input("End Date", value=end_date_default)

# Technical Indicators Selection
st.sidebar.subheader("Technical Indicators")
indicators = st.sidebar.multiselect(
    "Select Indicators:",
    ["20-Day SMA", "20-Day EMA", "20-Day Bollinger Bands", "VWAP"],
    default=["20-Day SMA"]
)

# Fetch Data Button
if st.sidebar.button("Fetch Data"):
    stock_data = {}
    for ticker in tickers:
        data = yf.download(ticker, start=start_date, end=end_date)
        if not data.empty:
            stock_data[ticker] = data
        else:
            st.warning(f"No data found for {ticker}.")
    st.session_state["stock_data"] = stock_data
    st.success("Stock data loaded successfully for: " + ", ".join(stock_data.keys()))

# Ensure Data is Available Before Analysis
if "stock_data" in st.session_state and st.session_state["stock_data"]:
    tab_names = ["Overall Summary"] + list(st.session_state["stock_data"].keys())
    tabs = st.tabs(tab_names)
    overall_results = []

    # Analysis Function
    def analyze_ticker(ticker, data):
        fig = go.Figure(data=[go.Candlestick(x=data.index, open=data['Open'], high=data['High'],
                                             low=data['Low'], close=data['Close'], name="Candlestick")])
        
        for ind in indicators:
            if ind == "20-Day SMA":
                fig.add_trace(go.Scatter(x=data.index, y=data['Close'].rolling(window=20).mean(),
                                         mode='lines', name='SMA (20)'))
            elif ind == "20-Day EMA":
                fig.add_trace(go.Scatter(x=data.index, y=data['Close'].ewm(span=20).mean(),
                                         mode='lines', name='EMA (20)'))
            elif ind == "20-Day Bollinger Bands":
                sma = data['Close'].rolling(window=20).mean()
                std = data['Close'].rolling(window=20).std()
                fig.add_trace(go.Scatter(x=data.index, y=sma + 2 * std, mode='lines', name='BB Upper'))
                fig.add_trace(go.Scatter(x=data.index, y=sma - 2 * std, mode='lines', name='BB Lower'))
            elif ind == "VWAP":
                data['VWAP'] = (data['Close'] * data['Volume']).cumsum() / data['Volume'].cumsum()
                fig.add_trace(go.Scatter(x=data.index, y=data['VWAP'], mode='lines', name='VWAP'))
        
        fig.update_layout(xaxis_rangeslider_visible=False)
        
        # Save chart as temp image
        with NamedTemporaryFile(suffix=".png", delete=False) as tmpfile:
            fig.write_image(tmpfile.name)
            tmpfile_path = tmpfile.name
        with open(tmpfile_path, "rb") as f:
            image_bytes = f.read()
        os.remove(tmpfile_path)

        # Convert image bytes to base64 before passing to agent.run()
        image_base64 = base64.b64encode(image_bytes).decode("utf-8")

        # AI Analysis with Tavily-enhanced insights
        with st.spinner(f'Analyzing {ticker}...'):
            response = agent.run(
                f"Analyze the stock chart for {ticker} and provide insights on trends, signals, and patterns.",
                images=[{"mime_type": "image/png", "data": image_base64}]
            )
        
        return fig, response.content

    # Generate Results
    for i, ticker in enumerate(st.session_state["stock_data"]):
        data = st.session_state["stock_data"][ticker]
        fig, analysis = analyze_ticker(ticker, data)
        overall_results.append({"Stock": ticker, "Analysis": analysis})
        
        with tabs[i + 1]:
            st.subheader(f"Analysis for {ticker}")
            st.plotly_chart(fig)
            st.write("**Detailed AI Insights:**")
            st.markdown(analysis)
    
    # Display Summary Table
    with tabs[0]:
        st.subheader("Overall AI-Powered Insights")
        df_summary = pd.DataFrame(overall_results)
        st.table(df_summary)
else:
    st.info("Please fetch stock data using the sidebar.")
