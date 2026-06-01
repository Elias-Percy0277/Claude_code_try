from flask import Flask, jsonify

app = Flask(__name__)

@app.route("/test")
def test():
    return jsonify({"hello": "world"})

@app.route("/api/stats")
def stats():
    return jsonify({"success": True, "data": {"total": 0}})

if __name__ == "__main__":
    print("Flask starting on localhost:5001...")
    app.run(host="localhost", port=5001, debug=False, use_reloader=False)
