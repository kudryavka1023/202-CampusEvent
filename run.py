"""本地启动入口：python run.py 后访问 http://127.0.0.1:5000/demo/login"""
from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
