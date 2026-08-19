import os
import psycopg2
from flask import Flask, request, jsonify
from datetime import datetime, timezone

app = Flask(__name__)


def get_conn():
    return psycopg2.connect(
        host=os.environ["DB_HOST"],
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        port=os.environ.get("DB_PORT", 5432),
    )


def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS records (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL
        )
    """)
    conn.commit()
    cur.close()
    conn.close()


@app.route("/api/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/api/records", methods=["GET"])
def list_records():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, name, created_at FROM records ORDER BY id DESC")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify([{"id": r[0], "name": r[1], "created_at": r[2].isoformat()} for r in rows])


@app.route("/api/records", methods=["POST"])
def create_record():
    data = request.get_json()
    name = data.get("name")
    if not name:
        return jsonify({"error": "name is required"}), 400
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO records (name, created_at) VALUES (%s, %s) RETURNING id",
        (name, datetime.now(timezone.utc)),
    )
    new_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"id": new_id, "name": name}), 201


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000)

# private ip: 172.31.19.113
