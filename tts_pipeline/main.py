#!/usr/bin/env python3
import json
import os
import base64
import time
import logging
import requests
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-5s | %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("TTS_PIPELINE")

class TTSPipeline:
    def __init__(self, config_path: str = "config/settings.json", chapters_dir: str = "config/chapters"):
        self.settings = self._load_json(config_path)
        self.chapters_dir = Path(chapters_dir)
        self.output_dir = Path(self.settings.get("output_dir", "./output"))
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.api_key = self.settings["api_key"]
        self.base_url = self.settings.get("base_url", "https://openrouter.ai/api/v1")
        self.model = self.settings.get("model", "google/gemini-3.1-flash-tts-preview")

    @staticmethod
    def _load_json(path: str) -> dict:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _build_payload(self, text: str, voice: str) -> dict:
        return {
            "model": self.model,
            "messages": [{"role": "user", "content": text}],
            "response_modalities": ["AUDIO"],
            "speech_config": {
                "voice_config": {
                    "prebuilt_voice_config": {"voice_name": voice}
                }
            }
        }

    def _send_request(self, payload: dict) -> dict:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": self.settings.get("http_referer", "https://localhost"),
            "X-Title": self.settings.get("app_title", "TTS Pipeline")
        }
        retries = self.settings.get("retry_attempts", 3)
        delay = self.settings.get("retry_delay_sec", 5)

        for attempt in range(1, retries + 1):
            try:
                resp = requests.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=300
                )
                resp.raise_for_status()
                return resp.json()
            except requests.exceptions.RequestException as e:
                logger.warning(f"Попытка {attempt}/{retries} упала: {e}")
                if attempt < retries:
                    time.sleep(delay * attempt)
                else:
                    raise RuntimeError(f"Все попытки отправки для payload завершены с ошибкой: {e}") from e

    def _extract_audio_and_usage(self, resp: dict):
        # OpenRouter/Gemini структура ответа для TTS
        choice = resp.get("choices", [])
        if not choice:
            raise ValueError("В ответе API отсутствует поле 'choices'")
        
        message = choice[0].get("message", {})
        
        # Проверяем наличие audio в message
        audio_data = message.get("audio", {})
        
        if isinstance(audio_data, dict) and "data" in audio_data:
            # Формат: {"audio": {"data": "<base64>", "transcript": "...", "expires_at": "..."}}
            audio_b64 = audio_data["data"]
        elif isinstance(audio_data, str):
            # Если аудио сразу строкой (редко, но бывает)
            audio_b64 = audio_data
        else:
            # Пробуем альтернативный формат через content array
            content = message.get("content", [])
            if isinstance(content, list):
                for part in content:
                    if isinstance(part, dict):
                        if "audio" in part:
                            audio_info = part["audio"]
                            if isinstance(audio_info, dict) and "data" in audio_info:
                                audio_b64 = audio_info["data"]
                                break
                            elif isinstance(audio_info, str):
                                audio_b64 = audio_info
                                break
                else:
                    raise ValueError("В ответе API не найдено аудио данных ни в одном из форматов")
            else:
                raise ValueError("Неожиданная структура ответа API: audio не найден")

        usage = resp.get("usage", {})
        in_tok = usage.get("prompt_tokens", 0)
        out_tok = usage.get("completion_tokens", 0)
        
        # Для TTS completion_tokens - это аудио токены, цена ориентировочная
        # OpenRouter тариф для Gemini TTS может отличаться, это ballpark оценка
        cost = (in_tok * 1.0 + out_tok * 20.0) / 1_000_000
        
        return audio_b64, in_tok, out_tok, round(cost, 4)

    def run(self):
        chapter_files = sorted(self.chapters_dir.glob("*.json"))
        if not chapter_files:
            logger.error("❌ В папке %s не найдено JSON-файлов.", self.chapters_dir)
            return

        logger.info("📦 Найдено %d частей. Запуск конвейера...", len(chapter_files))
        total_cost = 0.0

        for ch_file in chapter_files:
            logger.info("▶️ Обрабатываю: %s", ch_file.name)
            ch_data = self._load_json(ch_file)
            
            payload = self._build_payload(ch_data["text"], ch_data["voice"])
            resp = self._send_request(payload)
            audio_b64, in_tok, out_tok, cost = self._extract_audio_and_usage(resp)

            audio_bytes = base64.b64decode(audio_b64)
            out_path = self.output_dir / f"{ch_file.stem}.wav"
            out_path.write_bytes(audio_bytes)

            logger.info("✅ %s | In: %d | Out: %d | Cost: ~$%.4f", out_path.name, in_tok, out_tok, cost)
            total_cost += cost

        logger.info("🏁 Готово. Суммарная оценка: ~$%.4f", total_cost)


def main_entry():
    """Точка входа для консольной команды tts-pipeline."""
    TTSPipeline().run()


if __name__ == "__main__":
    main_entry()
