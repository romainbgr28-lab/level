"""Petit client HTTP pour l'API Mistral (chat completions, mode JSON)."""

import json
import logging
import os

import httpx

logger = logging.getLogger("level.mistral")

MISTRAL_API_URL = "https://api.mistral.ai/v1/chat/completions"
MISTRAL_MODEL = "mistral-small-latest"


class MistralError(Exception):
    """Erreur d'appel ou de réponse Mistral — à traduire en réponse HTTP claire côté API."""


def appeler_mistral_json(prompt: str, timeout: float = 30.0) -> dict:
    """Appelle Mistral en mode JSON et retourne le JSON parsé de la réponse.

    Lève MistralError (jamais silencieuse) si la clé API manque, si l'appel réseau
    échoue, si Mistral répond une erreur HTTP, ou si le contenu renvoyé n'est pas
    un JSON valide.
    """
    api_key = os.environ.get("MISTRAL_API_KEY")
    if not api_key:
        raise MistralError("MISTRAL_API_KEY n'est pas configurée côté serveur.")

    payload = {
        "model": MISTRAL_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"},
        "temperature": 0.4,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        response = httpx.post(MISTRAL_API_URL, json=payload, headers=headers, timeout=timeout)
    except httpx.HTTPError as exc:
        logger.exception("Appel réseau à Mistral échoué")
        raise MistralError(f"Appel réseau à Mistral échoué : {exc}") from exc

    if response.status_code != 200:
        logger.error("Mistral a répondu %s : %s", response.status_code, response.text[:1000])
        raise MistralError(f"Mistral a répondu {response.status_code} : {response.text[:500]}")

    try:
        body = response.json()
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, ValueError) as exc:
        logger.error("Réponse Mistral inattendue : %s", response.text[:1000])
        raise MistralError(f"Réponse Mistral inattendue : {exc}") from exc

    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        logger.error("Mistral n'a pas renvoyé un JSON valide : %s", content[:1000])
        raise MistralError(f"Mistral n'a pas renvoyé un JSON valide : {exc}") from exc
