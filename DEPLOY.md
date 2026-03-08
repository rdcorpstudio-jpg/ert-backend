# Deploy ERT: Vercel (Frontend) + Railway (Backend + Database)

Step-by-step for beginners. You need: **GitHub account**, **Vercel account**, **Railway account**.

---

## Part 1: Put your code on GitHub

1. Create a **new repository** on GitHub (e.g. `ert-app`). Do **not** add a README so the repo is empty.
2. On your computer, open a terminal in your **project folder** (where you have both ERT-Frontend and ERT-Backend).

   **Option A – Two separate repos (recommended)**  
   - One repo for frontend (e.g. `ert-frontend`).  
   - One repo for backend (e.g. `ert-backend`).  
   Push each folder to its own repo:

   ```bash
   cd ERT-Frontend
   git init
   git add .
   git commit -m "Initial frontend"
   git branch -M main
   git remote add origin https://github.com/YOUR_USERNAME/ert-frontend.git
   git push -u origin main
   ```

   ```bash
   cd ERT-Backend
   git init
   git add .
   git commit -m "Initial backend"
   git branch -M main
   git remote add origin https://github.com/YOUR_USERNAME/ert-backend.git
   git push -u origin main
   ```

   **Option B – One repo with two folders (monorepo)**  
   - One repo with folders `ERT-Frontend` and `ERT-Backend`.  
   - In the **parent folder** that contains both:

   ```bash
   git init
   git add .
   git commit -m "Initial"
   git branch -M main
   git remote add origin https://github.com/YOUR_USERNAME/ert-app.git
   git push -u origin main
   ```

   Use **Option A** below if you have two repos; use **Option B** instructions where we say “monorepo”.

---

## Part 2: Railway – Database (MySQL)

1. Go to [railway.app](https://railway.app) and sign up (e.g. with GitHub).
2. Click **“New Project”**.
3. Click **“Add service”** → **“Database”** → choose **“MySQL”**.
4. Wait until the MySQL service is running. Click the MySQL service.
5. Open the **“Variables”** tab. You’ll see **`MYSQL_URL`** or **`DATABASE_URL`** (Railway may name it either way).
6. Copy the value. It looks like:  
   `mysql://root:PASSWORD@HOST:PORT/railway`  
   For SQLAlchemy we need **`mysql+pymysql://...`**:
   - If it starts with `mysql://`, change it to **`mysql+pymysql://`** and use that as `DATABASE_URL` (see below).
7. **Create the database name** Railway uses (often `railway`). If you want a different database name, you can change it in the MySQL Variables or in the connection string. Keep the URL Railway gives you; we’ll use it in the Backend service.

   **Save this URL** – you’ll paste it into the Backend service as **`DATABASE_URL`**.

---

## Part 3: Railway – Backend (FastAPI)

### 3.1 Create backend service

1. In the **same Railway project**, click **“Add service”** → **“GitHub repo”**.
2. Select your **backend repo** (e.g. `ert-backend`).  
   (If you use a monorepo, select the one repo and we’ll set the root to the backend folder.)
3. Railway will detect the repo and try to build. We’ll configure it in the next steps.

### 3.2 Set root directory (only for monorepo)

- If your backend is in a subfolder (e.g. `ERT-Backend`):
  - Click the backend service → **Settings** → **Root Directory** → set to `ERT-Backend` (or your backend folder name) → Save.

### 3.3 Tell Railway how to run the app

1. Click your **backend service** (not the MySQL one).
2. Go to **Settings** → **Build** / **Deploy**.
3. **Build command** (optional; if you use a requirements file):  
   `pip install -r requirements.txt`  
   If you don’t have `requirements.txt`, create one in the backend root with:

   ```
   fastapi
   uvicorn[standard]
   sqlalchemy
   pymysql
   python-multipart
   python-jose[cryptography]
   passlib[bcrypt]
   openpyxl
   google-auth
   google-auth-oauthlib
   google-api-python-client
   httplib2
   ```

   Then set build command to:  
   `pip install -r requirements.txt`
4. **Start command**:  
   `uvicorn app.main:app --host 0.0.0.0 --port $PORT`  
   (Railway sets `PORT` automatically.)
5. Save.

### 3.4 Add environment variables (Backend service)

1. Click the **backend service** → **Variables** tab.
2. Add:

   | Name            | Value                                                                 |
   |-----------------|-----------------------------------------------------------------------|
   | `DATABASE_URL`  | The MySQL URL from Part 2, but with **`mysql+pymysql://`** at the start. Example: `mysql+pymysql://root:xxx@containers-us-west-xxx.railway.app:6543/railway?charset=utf8mb4` |
   | `CORS_ORIGINS`  | Your Vercel frontend URL, e.g. `https://your-app.vercel.app` (add this after you deploy the frontend; you can add `http://localhost:5173` first for local testing). |

   If Railway gives you **`MYSQL_URL`**, you can set:  
   `DATABASE_URL` = same value with `mysql://` replaced by `mysql+pymysql://`.

3. **JWT secret**: Your auth likely uses a secret. If your app reads it from an env var (e.g. `SECRET_KEY` or `JWT_SECRET`), add that variable here with a long random string.
4. **Google Drive** (if you use it): Add any env vars your backend expects for the service account (e.g. path or JSON). Railway doesn’t store local files between deploys, so use env vars or a mounted volume for credentials.

### 3.5 Deploy and get backend URL

1. Trigger a **Deploy** (e.g. push to GitHub or click “Redeploy”).
2. When the service is running, go to **Settings** → **Networking** → **Generate domain**. You’ll get a URL like `https://your-backend.up.railway.app`.
3. **Copy this URL** – this is your **backend API URL** for the frontend.

### 3.6 Run database migrations on production

1. **Option A – Railway CLI (recommended)**  
   - Install: [Railway CLI](https://docs.railway.app/develop/cli).  
   - In your **backend** folder (or monorepo backend root):

   ```bash
   railway link   # select your project + backend service
   railway run alembic upgrade head
   ```

2. **Option B – Local with production URL**  
   - In backend folder, set `DATABASE_URL` to the same value as on Railway (with `mysql+pymysql://`).  
   - Run: `alembic upgrade head`  
   (Only do this if your IP is allowed to connect to Railway MySQL.)

After this, your backend and DB are live on Railway.

---

## Part 4: Vercel – Frontend

1. Go to [vercel.com](https://vercel.com) and sign up (e.g. with GitHub).
2. Click **“Add New”** → **“Project”**.
3. **Import** your **frontend** repo (e.g. `ert-frontend`).  
   If you use a monorepo, import the one repo and set **Root Directory** to `ERT-Frontend` (or your frontend folder).
4. **Build settings** (Vercel often detects Vite automatically):
   - **Build Command:** `npm run build` or `pnpm build`
   - **Output Directory:** `dist`
   - **Install Command:** `npm install` or `pnpm install`
5. **Environment variables** – add:
   - **Name:** `VITE_API_URL`  
   - **Value:** Your Railway backend URL from Part 3.5, e.g. `https://your-backend.up.railway.app`  
   (No trailing slash.)
6. Click **Deploy**. Wait until the build finishes.
7. Your site will be at `https://your-project.vercel.app` (or your custom domain). This is your **frontend URL**.

---

## Part 5: Connect frontend and backend

1. **CORS**: In Railway → your **backend** service → **Variables**, set:
   - `CORS_ORIGINS` = `https://your-project.vercel.app`  
   (Use the exact Vercel URL from Part 4. You can add multiple origins separated by commas.)
2. **Redeploy** the backend so the new CORS setting is applied.
3. In the frontend, `VITE_API_URL` is already set on Vercel, so the app will call your Railway API. Open the Vercel URL and try logging in.

---

## Part 6: Quick checklist

- [ ] GitHub: frontend and backend repos (or one monorepo) pushed.
- [ ] Railway: MySQL database created; URL copied and changed to `mysql+pymysql://...`.
- [ ] Railway: Backend service from GitHub; build/start commands and `DATABASE_URL`, `CORS_ORIGINS` set; domain generated; migrations run (`alembic upgrade head`).
- [ ] Vercel: Frontend from GitHub; `VITE_API_URL` = Railway backend URL; deploy successful.
- [ ] Backend CORS includes the Vercel frontend URL.
- [ ] Test: open Vercel URL → login → use the app.

---

## Troubleshooting

- **Frontend shows “Failed to load” / network errors**  
  Check `VITE_API_URL` on Vercel (no trailing slash). Check browser Network tab: requests should go to your Railway URL.

- **CORS errors in browser**  
  Add your exact Vercel URL to `CORS_ORIGINS` on Railway (and redeploy). No trailing slash in the origin.

- **Backend 500 / DB errors**  
  Check Railway backend logs. Ensure `DATABASE_URL` uses `mysql+pymysql://` and that you ran `alembic upgrade head` for the Railway database.

- **Railway MySQL URL**  
  If the variable is `MYSQL_URL`, duplicate its value into `DATABASE_URL` and replace `mysql://` with `mysql+pymysql://`.

---

You’re done. Frontend = Vercel, Backend + Database = Railway.
