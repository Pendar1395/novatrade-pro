# NovaTrade Pro + NVProp (demo)

## Features
- Register/login with SQLite and Werkzeug password hashing
- Responsive Persian RTL interface
- Demo-only simulated trades and history
- NVProp evaluation challenge: $10,000 start, 8% profit target, $1,000 total loss limit
- New challenge restart

## Android / Termux
1. Download and extract the ZIP to `Download`.
2. In Termux run `termux-setup-storage` and allow storage access.
3. Run:
   ```bash
   pkg update
   pkg install python unzip
   cd ~/storage/downloads
   unzip NovaTrade_Complete.zip -d novatrade-files
   cd novatrade-files/novatrade_complete
   pip install -r requirements.txt
   cp .env.example .env
   ```
4. Optional: edit `.env` and replace `FLASK_SECRET_KEY` with a long random value.
5. Run `python app.py`.
6. Open `http://127.0.0.1:5000` in the phone browser.

Keep Termux running while using the site. Ctrl+C stops the server.

## Windows
Install Python 3, extract ZIP, open terminal in this folder, run `py -m pip install -r requirements.txt`, then `py app.py`. Open `http://127.0.0.1:5000`.

## Important
This is a learning prototype. Trade outcomes are randomized; it does not connect to an exchange or execute real orders. The daily-loss limit is displayed for education but is not calculated from exchange market data. Do not use real passwords or real funds. Before public deployment, add CSRF protection, rate limiting, secure cookie configuration, HTTPS, and proper risk controls.
