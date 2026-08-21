from __future__ import annotations

import hmac
import os
import secrets
from datetime import timedelta
from functools import wraps
from typing import Any, Callable

from dotenv import load_dotenv
from flask import Flask, Response, abort, flash, redirect, render_template, request, session, url_for

from .service import collect_opportunities
from .storage import (
    init_db,
    latest_search_run,
    list_selections,
    recent_queries,
    save_search_run,
    save_selection,
    update_selection,
)

load_dotenv()


def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = os.getenv("WEB_SECRET_KEY") or secrets.token_hex(32)
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.getenv("WEB_HTTPS_ONLY", "false").lower() == "true",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
    )
    init_db()

    @app.context_processor
    def inject_csrf_token() -> dict[str, Any]:
        if "csrf_token" not in session:
            session["csrf_token"] = secrets.token_urlsafe(32)
        return {"csrf_token": session["csrf_token"]}

    @app.before_request
    def protect_posts() -> None:
        if request.method == "POST":
            provided = request.form.get("csrf_token", "")
            expected = session.get("csrf_token", "")
            if not provided or not expected or not hmac.compare_digest(provided, expected):
                abort(400)

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

    @app.template_filter("status_label")
    def status_label(value: str | None) -> str:
        return {
            "selected": "Selecionado",
            "link_created": "Link gerado",
            "published": "Publicado",
            "closed": "Encerrado",
        }.get(value or "", value or "n/d")

    @app.template_filter("date_br")
    def date_br(value: str | None) -> str:
        if not value:
            return "n/d"
        try:
            from datetime import datetime

            return datetime.fromisoformat(value).astimezone().strftime("%d/%m/%Y %H:%M")
        except ValueError:
            return value

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
                session.permanent = True
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
        latest = latest_search_run() if request.method == "GET" else None
        query = request.form.get(
            "query", latest["query"] if latest else os.getenv("MELI_QUERY", "air fryer")
        ).strip()
        try:
            default_limit = latest["limit"] if latest else os.getenv("MELI_LIMIT", "20")
            limit = max(1, min(int(request.form.get("limit", default_limit)), 50))
        except ValueError:
            limit = 20
        report = latest["report"] if latest else None
        error = None
        if request.method == "POST":
            if not query:
                error = "Informe um texto para a consulta."
            else:
                try:
                    report = collect_opportunities(query, limit, os.getenv("MELI_SITE_ID", "MLB"))
                    save_search_run(query, limit, report)
                except Exception as exc:  # mensagem operacional sem expor traceback no navegador
                    error = str(exc)
        configured = os.getenv(
            "WEB_SEARCH_SUGGESTIONS",
            "air fryer,perfume feminino,perfume masculino,smartwatch,ferramentas,beleza,casa e cozinha,eletrônicos",
        )
        suggestions = list(dict.fromkeys(recent_queries() + [value.strip() for value in configured.split(",") if value.strip()]))
        return render_template(
            "index.html",
            query=query,
            limit=limit,
            report=report,
            error=error,
            suggestions=suggestions,
            restored=bool(latest),
        )

    @app.post("/selection/save")
    @login_required
    def selection_save() -> Response:
        product_id = request.form.get("catalog_product_id", "").strip()
        if not product_id:
            abort(400)

        def number(name: str) -> float | None:
            try:
                return float(request.form[name]) if request.form.get(name) else None
            except ValueError:
                return None

        save_selection(
            {
                **request.form,
                "catalog_product_id": product_id,
                "price": number("price"),
                "marketplace_score": number("marketplace_score"),
                "best_seller_position": number("best_seller_position"),
                "official_store_id": number("official_store_id"),
                "affiliate_direct_value": number("affiliate_direct_value"),
                "affiliate_indirect_value": number("affiliate_indirect_value"),
            }
        )
        flash("Produto registrado com sucesso.", "success")
        return redirect(url_for("selections", decision=request.form.get("decision", "approved")))

    @app.get("/selections")
    @login_required
    def selections() -> str:
        decision = request.args.get("decision", "approved")
        if decision not in {"approved", "discarded"}:
            decision = "approved"
        return render_template(
            "selections.html", selections=list_selections(decision), decision=decision
        )

    @app.post("/selections/<int:selection_id>/update")
    @login_required
    def selection_update(selection_id: int) -> Response:
        update_selection(selection_id, dict(request.form))
        flash("Alterações salvas com sucesso.", "success")
        return redirect(url_for("selections"))

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host=os.getenv("WEB_HOST", "127.0.0.1"), port=int(os.getenv("WEB_PORT", "5000")))
