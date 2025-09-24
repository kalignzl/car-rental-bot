# app.py
import os, requests
from flask import Flask, request, jsonify

app = Flask(__name__)

@app.get("/")
def health():
    return "OK", 200

@app.post("/webhook/<secret>")
def webhook(secret):
    # optional: check secret == os.environ.get("WEBHOOK_SECRET", "hook")
    update = request.get_json(silent=True) or {}
    # (safe no-op if BOT_TOKEN missing)
    return jsonify(ok=True), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
