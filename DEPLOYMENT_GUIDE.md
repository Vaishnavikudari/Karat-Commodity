# KARAT — Deployment Guide

This guide explains how to deploy the **KARAT** prototype to the cloud so anyone can access it over the public internet with HTTPS.

Because the FastAPI backend (`backend/api/main.py`) already mounts and serves the static frontend (`index.html`, `app.js`, `app.css`), **you only need to deploy a single unified service**.

---

## Option 1: Render.com (Recommended — 100% Free & Simplest)

Render provides free hosting for Python web apps with automatic HTTPS and continuous deployment from GitHub.

### Step-by-Step Instructions:
1. **Push your code to GitHub**:
   ```bash
   git init
   git add .
   git commit -m "Initial Karat commit"
   git remote add origin https://github.com/<your-username>/karat.git
   git push -u origin main
   ```
2. **Create an account on Render**:
   - Go to [https://render.com](https://render.com) and sign up (or log in with GitHub).
3. **Create a New Web Service**:
   - Click **"New +"** -> **"Web Service"**.
   - Connect your GitHub repository `karat`.
4. **Configure Settings**:
   - **Name**: `karat-gold` (or any name you prefer)
   - **Region**: Singapore or Frankfurt (or nearest)
   - **Branch**: `main`
   - **Runtime**: `Python 3`
   - **Build Command**: `pip install .`
   - **Start Command**: `uvicorn backend.api.main:app --host 0.0.0.0 --port $PORT`
   - **Plan**: Select **Free**
5. **Click "Create Web Service"**:
   - Render will build and deploy the app in 2–3 minutes.
   - Your live URL will be: `https://karat-gold.onrender.com`

---

## Option 2: Railway.app (Fastest Alternative)

Railway automatically detects either `requirements.txt` or the `Dockerfile`.

1. Go to [https://railway.app](https://railway.app) and sign in with GitHub.
2. Click **"New Project"** -> **"Deploy from GitHub repo"**.
3. Select your `karat` repository.
4. Railway will automatically build the Dockerfile and deploy.
5. In the service settings under **"Networking"**, click **"Generate Domain"** to get your public URL (e.g. `https://karat-production.up.railway.app`).

---

## Option 3: Instant Live Sharing via Cloudflare Tunnel (Zero Setup Needed)

If you just need a public link to share immediately from your laptop or during a demo:

You can use the bundled `cloudflared.exe` tunnel:
```powershell
# In the project directory:
.\cloudflared.exe tunnel --url http://localhost:8080
```
This gives you a free, public HTTPS URL immediately (e.g., `https://....trycloudflare.com`) that routes traffic directly to your running prototype.

*(Note: Ensure `python -m uvicorn backend.api.main:app --reload --port 8000` is also running).*

---

## Option 4: Deploying on a VPS / Docker Container

If deploying to AWS EC2, DigitalOcean, or an Ubuntu server:

1. **Build the Docker container**:
   ```bash
   docker build -t karat .
   ```
2. **Run the container**:
   ```bash
   docker run -d -p 8000:8000 --name karat-app karat
   ```
3. Visit `http://<your-server-ip>:8000`.

---

## Verification Checklist After Deployment

After deploying, verify:
- [ ] Visit `/` -> Renders 3D hero stage & "Experience KARAT".
- [ ] Click "Experience KARAT" -> Enters analytics dashboard.
- [ ] Overview tab displays "No opportunity right now" answer card.
- [ ] Switching to Spread Lab, Backtest, Calendar, Data & Method tabs shows each respective component.
- [ ] Chatbot (gold icon in bottom right) answers prompts without errors.
