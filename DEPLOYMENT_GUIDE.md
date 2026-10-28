# KARAT — Production Deployment Guide

## Official Live Production Deployment
The live instance of **KARAT** is deployed and running at:
**[https://karat-commodity-t6ym.onrender.com](https://karat-commodity-t6ym.onrender.com)**

- **Interactive API Documentation:** [https://karat-commodity-t6ym.onrender.com/docs](https://karat-commodity-t6ym.onrender.com/docs)
- **API Health Check:** [https://karat-commodity-t6ym.onrender.com/health](https://karat-commodity-t6ym.onrender.com/health)

Because the FastAPI backend (`backend/api/main.py`) mounts and serves the static frontend (`index.html`, `app.js`, `app.css`), it runs as a **single unified service** with zero extra reverse proxies required.

---

## Live Hosting Configuration (Render.com)

The application is deployed on Render via GitHub CI/CD:

- **Repository**: `https://github.com/Vaishnavikudari/Karat-Commodity`
- **Branch**: `main`
- **Runtime**: `Python 3`
- **Build Command**: `pip install .`
- **Start Command**: `uvicorn backend.api.main:app --host 0.0.0.0 --port $PORT`
- **Live Endpoint**: `https://karat-commodity-t6ym.onrender.com`

Whenever commits are pushed to `origin/main`, Render automatically triggers a new build and deploys the latest version with zero downtime.

---

## Local Testing & Development

To test locally with the exact same production settings:

```bash
# 1. Install dependencies
pip install -e .

# 2. Run the unified app
python -m uvicorn backend.api.main:app --host 0.0.0.0 --port 8000
```

---

## Deployment Verification Checklist

After deployment, verify that:
- [x] Visiting `/` renders the 3D stage and allows entering the dashboard.
- [x] Overview tab shows live normalised contracts and active signal card.
- [x] Backtest tab executes walk-forward simulation and CSV export works seamlessly.
- [x] Raw Audit tab provides direct downloads for Clean Bhavcopy CSV, Normalised Prices CSV, Spreads CSV, and Quality Report JSON.
- [x] AI Assistant chatbot responds without error.

