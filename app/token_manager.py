from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".env"
TOKEN_URL = "https://api.mercadolibre.com/oauth/token"
_REFRESH_LOCK = threading.Lock()


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Variável obrigatória ausente no .env: {name}")
    return value


def _save_env_values(updates: dict[str, str]) -> None:
    """Atualiza todas as credenciais em uma única substituição do arquivo."""
    if not ENV_FILE.exists():
        raise RuntimeError(f"Arquivo .env não encontrado em {ENV_FILE}")

    lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    pending = dict(updates)
    updated_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        key = stripped.split("=", maxsplit=1)[0] if "=" in stripped else None
        if key in pending and not stripped.startswith("#"):
            updated_lines.append(f"{key}={pending.pop(key)}")
        else:
            updated_lines.append(line)

    if pending:
        if updated_lines and updated_lines[-1]:
            updated_lines.append("")
        updated_lines.extend(f"{key}={value}" for key, value in pending.items())

    temporary_file = ENV_FILE.with_name(".env.tmp")
    temporary_file.write_text(
        "\n".join(updated_lines) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary_file, ENV_FILE)


def _token_expiring() -> bool:
    raw_expiration = os.getenv("MELI_TOKEN_EXPIRES_AT", "").strip()
    if not raw_expiration:
        return False
    try:
        return time.time() >= float(raw_expiration) - 60
    except ValueError:
        return False


def refresh_tokens() -> str:
    """Renova e persiste access token, refresh token e validade."""
    with _REFRESH_LOCK:
        if not _token_expiring():
            current_token = os.getenv("MELI_ACCESS_TOKEN", "").strip()
            if current_token:
                return current_token

        response = requests.post(
            TOKEN_URL,
            headers={
                "accept": "application/json",
                "content-type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "refresh_token",
                "client_id": _required_env("MELI_CLIENT_ID"),
                "client_secret": _required_env("MELI_CLIENT_SECRET"),
                "refresh_token": _required_env("MELI_REFRESH_TOKEN"),
            },
            timeout=20,
        )

        try:
            payload: dict[str, Any] = response.json()
        except ValueError:
            payload = {}

        if not response.ok:
            error = (
                payload.get("error_description")
                or payload.get("message")
                or payload.get("error")
                or "resposta inválida"
            )
            raise RuntimeError(
                f"Não foi possível renovar o token (HTTP {response.status_code}): "
                f"{error}. Faça uma nova autorização se o refresh token expirou "
                "ou já foi utilizado."
            )

        access_token = str(payload.get("access_token") or "").strip()
        refresh_token = str(payload.get("refresh_token") or "").strip()
        expires_in = int(payload.get("expires_in") or 21600)

        if not access_token or not refresh_token:
            raise RuntimeError(
                "A renovação não retornou access_token e refresh_token válidos."
            )

        expires_at = str(int(time.time()) + expires_in)
        updates = {
            "MELI_ACCESS_TOKEN": access_token,
            "MELI_REFRESH_TOKEN": refresh_token,
            "MELI_TOKEN_EXPIRES_AT": expires_at,
        }
        _save_env_values(updates)
        os.environ.update(updates)
        return access_token


def meli_request(
    method: str,
    url: str,
    **kwargs: Any,
) -> requests.Response:
    """Executa uma chamada autenticada e repete uma vez após renovar o token."""
    headers = dict(kwargs.pop("headers", {}) or {})
    timeout = kwargs.pop("timeout", 20)

    if _token_expiring():
        refresh_tokens()

    headers["Authorization"] = f"Bearer {_required_env('MELI_ACCESS_TOKEN')}"
    response = requests.request(
        method,
        url,
        headers=headers,
        timeout=timeout,
        **kwargs,
    )

    if response.status_code != 401:
        return response

    # Tokens antigos podem não ter MELI_TOKEN_EXPIRES_AT. Força a renovação
    # após o primeiro 401 e repete a chamada somente uma vez.
    os.environ["MELI_TOKEN_EXPIRES_AT"] = "0"
    access_token = refresh_tokens()
    headers["Authorization"] = f"Bearer {access_token}"
    return requests.request(
        method,
        url,
        headers=headers,
        timeout=timeout,
        **kwargs,
    )
