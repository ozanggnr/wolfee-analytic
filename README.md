# Wolfee Analytics

Wolfee Analytics is a sophisticated financial data analysis platform designed to provide real-time insights, comprehensive market tracking, and intelligent stock evaluation for both BIST (Borsa Istanbul) and Global markets.

The system bridges the gap between raw market data and actionable financial intelligence, offering a unified dashboard for tracking stocks, commodities, and market trends.

## 🚀 Key Features

### 1. Comprehensive Market Tracking
-   **Dual Market Coverage**: Seamlessly tracks top liquid stocks from both **BIST 100** (Turkish Market) and **Global Markets** (US Tech, Pharma, Energy, etc.).
-   **Live & Cached Data**: Utilizes a smart hybrid caching system to deliver instant "Quick View" data while updating full market statistics in the background.
-   **Commodities Monitoring**: Real-time tracking of essential commodities like Gold, Silver, Copper, and Crude Oil.

### 2. Intelligent Technical Analysis
-   **Automated Indicators**: Automatically calculates key technical indicators for every stock:
    -   **RSI (Relative Strength Index)**: Identifies Overbought/Oversold conditions.
    -   **SMA (Simple Moving Averages)**: Tracks 20-day trends.
    -   **Volatility Analysis**: categorization of price movement risks.
-   **Opportunity Scanner**: A built-in logic engine that scans the market for favorable conditions (e.g., Oversold + Uptrend) and highlights potential buy opportunities.
-   **AI-Driven Insights**: Generates dynamic market summaries and "Day's Insight" based on aggregate market performance.

### 3. Data Visualization & Reporting
-   **Interactive Dashboard**: A responsive, card-based UI that provides at-a-glance metrics (Price, Change %, Volume, High/Low).
-   **Dynamic Charting**: Integrated interactive charts for visualizing historical price performance over 1M, 1Y, and 5Y periods.
-   **Professional Reporting**:
    -   **Market Export**: Generates detailed Excel reports (Daily, Weekly, Monthly) with full technical breakdowns.
    -   **Portfolio Export**: Allows users to select specific stocks and export a snapshot report matching professional market standards.

## 🛠 Technical Architecture

Wolfee Analytics runs on a modern, high-performance architecture designed for speed and reliability.

### Backend Core (Python & FastAPI)
The backbone of the system is a robust **FastAPI** application that serves as the central data aggregator.
-   **Multi-Source Data Router**: A resilient scraping engine that fetches data from multiple financial providers, automatically failing over between sources (e.g., Yahoo Finance, Google Finance, Finnhub) to ensure data continuity.
-   **Background Task Processing**: Utilizes asynchronous background workers to fetch and process heavy datasets without freezing the user interface.
-   **Smart Caching**: Implements time-based caching (TTL) to instantly serve frequent requests while keeping data fresh.

### Frontend Experience
A lightweight, high-performance interface built for clarity and speed.
-   **Dynamic Search & Filtering**: Client-side filtering allowing instant access to any stock.
-   **Responsive Design**: Optimized for both desktop and mobile viewing.
-   **Asynchronous Loading**: Features a progressive loading system that displays critical data immediately (`Quick Load`) while populating deeper analytics incrementally.

### Data Integrity & Safety
-   **Rate Limit Protection**: Advanced throttling and delay mechanisms to respect third-party API limits.
-   **Error Resilience**: graceful error handling for missing charts or delisted assets, ensuring the platform remains stable even during partial data outages.

---
*Wolfee Analytics is built for analysts, traders, and finance enthusiasts who require reliable, aggregated market data at their fingertips.*
