#!/usr/bin/env python3
import base64
import binascii
import json
import logging
import time
from pathlib import Path

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-5s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("TTS_PIPELINE")


class TTSPipeline:
    def __init__(
        self,
        config_path: str = "config/settings.json",
        chapters_dir: str = "config/chapters",
    ):
        module_root = Path(__file__).resolve().parent

        requested_config = Path(config_path)
        self.config_path = requested_config if requested_config.is_absolute() else module_root / requested_config
        self.settings = self._load_json(self.config_path)

        requested_chapters = Path(chapters_dir)
        self.chapters_dir = requested_chapters if requested_chapters.is_absolute() else module_root / requested_chapters

        requested_output = Path(self.settings.get("output_dir", "output"))
        self.output_dir = requested_output if requested_output.is_absolute() else module_root / requested_output
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.api_key = self.settings.get("api_key")
        if not self.api_key:
            raise ValueError(f"api_key не задан в конфиге: {self.config_path}")

        self.base_url = self.settings.get("base_url", "https://openrouter.ai/api/v1")
        self.model = self.settings.get("model", "google/gemini-3.1-flash-tts-preview")

    @staticmethod
    def _load_json(path: Path) -> dict:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def _build_payload(self, text: str, voice: str) -> dict:
        return {
            "model": self.model,
            "messages": [{"role": "user", "content": text}],
            "response_modalities": ["AUDIO"],
            "speech_config": {
                "voice_config": {"prebuilt_voice_config": {"voice_name": voice}}
            },
        }

    def _send_request(self, payload: dict) -> dict:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": self.settings.get("http_referer", "https://localhost"),
            "X-Title": self.settings.get("app_title", "TTS Pipeline"),
        }
        retries = self.settings.get("retry_attempts", 3)
        delay = self.settings.get("retry_delay_sec", 5)

        for attempt in range(1, retries + 1):
            try:
                resp = requests.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=300,
                )
                resp.raise_for_status()
                return resp.json()
            except requests.exceptions.RequestException as e:
                logger.warning("Попытка %d/%d упала: %s", attempt, retries, e)
                if attempt < retries:
                    time.sleep(delay * attempt)
                else:
                    raise RuntimeError(f"Все попытки отправки payload завершены с ошибкой: {e}") from e

    def _extract_audio_and_usage(self, resp: dict):
        choices = resp.get("choices", [])
        if not choices:
            raise ValueError("В ответе API отсутствует поле 'choices'")

        message = choices[0].get("message", {})
        audio_data = message.get("audio", {})

        if isinstance(audio_data, dict) and "data" in audio_data:
            audio_b64 = audio_data["data"]
        elif isinstance(audio_data, str):
            audio_b64 = audio_data
        else:
            content = message.get("content", [])
            if isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and "audio" in part:
                        audio_info = part["audio"]
                        if isinstance(audio_info, dict) and "data" in audio_info:
                            audio_b64 = audio_info["data"]
                            break
                        if isinstance(audio_info, str):
                            audio_b64 = audio_info
                            break
                else:
                    raise ValueError("В ответе API не найдено аудио данных ни в одном из форматов")
            else:
                raise ValueError("Неожиданная структура ответа API: audio не найден")

        usage = resp.get("usage", {})
        in_tok = usage.get("prompt_tokens", 0)
        out_tok = usage.get("completion_tokens", 0)
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

            text = ch_data.get("text")
            voice = ch_data.get("voice")
            if not text or not voice:
                logger.error("❌ Пропускаю %s: отсутствует text или voice", ch_file.name)
                continue

            payload = self._build_payload(text, voice)
            resp = self._send_request(payload)
            audio_b64, in_tok, out_tok, cost = self._extract_audio_and_usage(resp)

            try:
                audio_bytes = base64.b64decode(audio_b64)
            except (ValueError, binascii.Error) as e:
                logger.error("❌ %s: не удалось декодировать base64 аудио: %s", ch_file.name, e)
                continue

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
