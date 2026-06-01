"""
Flask Web 应用
"""
from flask import Flask, render_template, jsonify, request, redirect, url_for
import asyncio
from datetime import datetime

from config.settings import settings
from core.ai_engine import ai_engine
from core.message_handler import message_handler
from core.personality import style_learning
from storage.database import db
from storage.models import Contact
from utils.logger import logger


def create_app():
    """创建 Flask 应用"""
    app = Flask(__name__,
                template_folder="templates",
                static_folder="static")

    app.config["SECRET_KEY"] = "wechat-custody-secret-key"
    app.config["JSON_AS_ASCII"] = False

    # 注册路由
    from web.routes import bp
    app.register_blueprint(bp)

    # 异步任务运行器
    def run_async(coro):
        """在同步环境中运行异步函数"""
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)

    app.run_async = run_async

    return app


# 创建应用实例
flask_app = create_app()
