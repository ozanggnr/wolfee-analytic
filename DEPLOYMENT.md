# Wolfee Market Deployment Guide

## ✅ Step 1: GitHub Repository (COMPLETE)

Your code is now on GitHub at: https://github.com/ozanggnr/analytic-frontend

---

## ✅ Step 2: Render Backend Deployment (COMPLETE)

Your backend is live at: **https://wolfee-backend.onrender.com**

### Render Configuration Summary:
- **Name**: wolfee-backend
- **Repository**: https://github.com/ozanggnr/analytic-backend
- **Branch**: main
- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `uvicorn main:app --host 0.0.0.0 --port 8080`
- **Health Check Path**: `/healthz` ✓

> [!NOTE]
> Your current Render settings are correct! The backend uses port 8080 which Render automatically assigns.

### Render Settings Explanation:
- **Root Directory**: Leave empty (uses repository root)
- **Build Command**: Already set correctly
- **Pre-Deploy Command**: Leave empty (not needed)
- **Health Check**: Set to `/healthz` - This prevents the 405 errors you saw
- **Auto-Deploy**: Keep ON for automatic updates when you push to GitHub

---

## 🚀 Step 3: Cloudflare Pages Frontend Deployment

Your frontend is configured to use the Render backend. Now deploy to Cloudflare Pages:

### Option A: Using Cloudflare Dashboard (Recommended)

1. **Go to Cloudflare Pages**:
   - Visit https://dash.cloudflare.com/
   - Click "Workers & Pages" in the left sidebar
   - Click "Create application" → "Pages" → "Connect to Git"

2. **Connect GitHub Repository**:
   - Select your GitHub account
   - Choose repository: **analytic-frontend**
   - Click "Begin setup"

3. **Configure Build Settings**:
   ```
   Project name: wolfee-market (or any name you prefer)
   Production branch: main
   
   Build settings:
   ├─ Framework preset: None
   ├─ Build command: (leave empty)
   ├─ Build output directory: frontend
   └─ Root directory: (leave empty or set to "frontend")
   ```

4. **Advanced Settings (Optional)**:
   - No environment variables needed
   - Leave all other settings as default

5. **Click "Save and Deploy"**

6. **Wait for deployment** (should take 30-60 seconds)

### Option B: Using Wrangler CLI

If you prefer command line:

```bash
# Navigate to frontend directory
cd c:/Users/ozang/OneDrive/Desktop/wolfeemarket/wolfee/frontend

# Login to Cloudflare (if not already)
npx wrangler login

# Deploy
npx wrangler pages deploy . --project-name=wolfee-market
```

---

## 📋 Post-Deployment Checklist

After Cloudflare deployment completes:

### 1. Test Your Live Application
- [ ] Visit your Cloudflare Pages URL (will be shown after deployment)
- [ ] Check that the app loads without errors
- [ ] Open browser console (F12) and verify no CORS errors
- [ ] Test stock search functionality
- [ ] Verify data loads from Render backend

### 2. Test Backend API Endpoints
Visit these URLs to verify backend is working:
- ✅ https://wolfee-backend.onrender.com/ - Should show welcome message
- ✅ https://wolfee-backend.onrender.com/healthz - Should show `{"status": "healthy"}`
- ✅ https://wolfee-backend.onrender.com/docs - FastAPI documentation
- ✅ https://wolfee-backend.onrender.com/api/market-data/quick - Should return stock data

### 3. Common Issues & Solutions

**Issue**: CORS errors in browser console
- **Solution**: Already handled! Your backend has CORS enabled for all origins

**Issue**: 502 Bad Gateway or timeout errors
- **Solution**: Render free tier may take 50+ seconds to start if idle. Wait and retry.

**Issue**: Stock data not loading
- **Solution**: Check browser console for errors. Verify backend URL in `config.js`

**Issue**: Charts not displaying
- **Solution**: Ensure the chart JS library is loaded. Check browser console.

---

## 🔄 Future Updates

After deployment, to update your app:

### Update Frontend:
1. Make changes locally
2. `git add .`
3. `git commit -m "Update frontend"`
4. `git push origin main`
5. Cloudflare Pages auto-deploys (if configured)

### Update Backend:
1. Make changes in backend repo
2. `git add .`  
3. `git commit -m "Update backend"`
4. `git push origin main`
5. Render auto-deploys

---

## 📱 Your Live URLs

Once Cloudflare deployment completes:

- **Frontend**: `https://wolfee-market.pages.dev` (or your custom name)
- **Backend**: `https://wolfee-backend.onrender.com`
- **API Docs**: `https://wolfee-backend.onrender.com/docs`

---

## 🎉 Next Steps

1. Deploy frontend to Cloudflare Pages (instructions above)
2. Test the live application
3. (Optional) Add custom domain to Cloudflare Pages
4. (Optional) Upgrade Render to paid tier for better performance
