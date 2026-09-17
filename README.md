# Wolfee Analytics

**Live Demo:** [https://wolfee-analytics.up.railway.app/](https://wolfee-analytics.up.railway.app/)

Wolfee Analytics is a sophisticated financial data analysis platform designed to provide real-time insights, comprehensive market tracking, and intelligent stock evaluation for both BIST (Borsa Istanbul) and Global markets.

The system bridges the gap between raw market data and actionable financial intelligence, offering a unified dashboard for tracking stocks, commodities, Turkish Gold, and Exchange Rates. It now leverages AI to provide daily market insights and deep stock analysis.

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

### 4. Secure Authentication & Portfolio Watchlist
-   **Enterprise-Grade Authentication**:
    -   Password hashing using **bcrypt with cost factor 12** (`rounds=12`) with built-in salting.
    -   Mandatory **Email Verification** before account activation.
    -   Strict **server-side password policy**: minimum 10 characters with common password blocklist validation.
    -   Complete **anti-enumeration protection**: identical generic responses across registration, login, and forgot-password endpoints.
-   **Brute-Force & Bot Defense**:
    -   Per-IP sliding-window rate limiting (10 req/min) on sensitive authentication endpoints.
    -   Per-account lockout with exponential backoff cooldowns: 1 min after 5 failures, 5 min after 6 failures, 15 min after 7+ failures.
    -   CAPTCHA bot protection challenge on registration and dynamically triggered after 3 failed login attempts.
    -   Security audit logs recording failed attempts, source IPs, and timestamps.
-   **Session Security**:
    -   Server-side sessions stored in PostgreSQL `user_sessions` table for instant multi-device revocation.
    -   Stored strictly in `HttpOnly`, `Secure`, `SameSite=Strict` cookies (zero credentials in `localStorage` or `sessionStorage`).
    -   Double-Submit Cookie CSRF protection on all state-changing endpoints (`POST`, `PUT`, `DELETE`).
-   **Portfolio Watchlist & Performance Snapshot**:
    -   Persistent watchlist items mapped to authenticated accounts (`BIST100` and `US` stocks).
    -   Real-time multi-tier market data enrichment from PostgreSQL cache and live provider fallbacks.
    -   **Analytical Summary Card**: Real-time breakdown of Up/Down/Flat ticker counts, highlighted single biggest daily mover, overall portfolio daily % change, and individual ticker movement pills.
    -   60-second TTL server/client cache with live countdown timer and manual instant refresh.

## 🛡️ Infrastructure & Deployment Security Note

> [!IMPORTANT]
> **Application-Level vs. Network-Level Protection**:
> The application-level rate limiting and account lockout mechanisms protect the application from targeted brute-force attacks and credential stuffing. However, **application code cannot solve large-scale volumetric Distributed Denial of Service (DDoS) attacks alone**.
>
> **Production Infrastructure Recommendation**:
> As a required production deployment step, deploy Wolfee Analytics behind a reverse-proxy security edge such as **Cloudflare**:
> 1. **Bot Fight Mode**: Enable Cloudflare Bot Fight Mode to challenge automated scrapers and bad bots before requests reach the origin server.
> 2. **WAF Rate Limiting Rules**: Set an edge rate limit (e.g., max 100 requests per 10 seconds per IP) to absorb L7 HTTP floods at the edge.
> 3. **DDoS Mitigation**: Enable Cloudflare's unmetered HTTP DDoS protection.
> 4. **Proxy Headers**: Ensure your origin server receives and trusts `CF-Connecting-IP` (which Wolfee Analytics automatically prioritizes for IP rate limiting and security audit logs).

---
*Wolfee Analytics is built for analysts, traders, and finance enthusiasts who require reliable, aggregated market data at their fingertips.*
