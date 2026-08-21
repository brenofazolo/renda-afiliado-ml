from __future__ import annotations

import hmac
import os
import secrets
from functools import wraps
from typing import Any, Callable

from dotenv import load_dotenv
from flask import Flask, Response, redirect, render_template, request, session, url_for

from .service import collect_opportunities

load_dotenv()


def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = os.getenv("WEB_SECRET_KEY") or secrets.token_hex(32)

    def login_required(view: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(view)
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            if not session.get("authenticated"):
                return redirect(url_for("login", next=request.path))
            return view(*args, **kwargs)

        return wrapped

    @app.template_filter("brl")
    def format_brl(value: float | int | None) -> str:
        if value is None:
            return "n/d"
        formatted = f"{value:,.2f}".replace(",", "#").replace(".", ",").replace("#", ".")
        return f"R$ {formatted}"

    @app.template_filter("duration")
    def format_duration(seconds: float) -> str:
        if seconds < 60:
            return f"{seconds:.2f} s".replace(".", ",")
        minutes, remainder = divmod(seconds, 60)
        return f"{int(minutes)} min {remainder:.2f} s".replace(".", ",")

    @app.route("/login", methods=["GET", "POST"])
    def login() -> str | Response:
        error = None
        if request.method == "POST":
            expected_user = os.getenv("WEB_USERNAME", "")
            expected_password = os.getenv("WEB_PASSWORD", "")
            username = request.form.get("username", "")
            password = request.form.get("password", "")
            if expected_user and expected_password and hmac.compare_digest(username, expected_user) and hmac.compare_digest(password, expected_password):
                session["authenticated"] = True
                return redirect(url_for("index"))
            error = "Usuário ou senha inválidos."
        return render_template("login.html", error=error)

    @app.post("/logout")
    def logout() -> Response:
        session.clear()
        return redirect(url_for("login"))

    @app.route("/", methods=["GET", "POST"])
    @login_required
    def index() -> str:
        query = request.form.get("query", os.getenv("MELI_QUERY", "air fryer")).strip()
        try:
            limit = max(1, min(int(request.form.get("limit", os.getenv("MELI_LIMIT", "20"))), 50))
        except ValueError:
            limit = 20
        report = None
        error = None
        if request.method == "POST":
            if not query:
                error = "Informe um texto para a consulta."
            else:
                try:
                    report = collect_opportunities(query, limit, os.getenv("MELI_SITE_ID", "MLB"))
                except Exception as exc:  # mensagem operacional sem expor traceback no navegador
                    error = str(exc)
        return render_template("index.html", query=query, limit=limit, report=report, error=error)

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host=os.getenv("WEB_HOST", "127.0.0.1"), port=int(os.getenv("WEB_PORT", "5000")))
