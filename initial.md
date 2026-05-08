Вот как это будет устроено. Без магии, только файлы и чёткие границы ответственности.

### 📐 Архитектура
```
tts_pipeline/
├── main.py                 # Логика: API, ретраи, декодирование, сохранение, логирование
├── config/
│   ├── settings.json       # Ключ, модель, базовый URL, параметры ретраев
│   └── chapters/
│       ├── ch1.json        # Кусок 1: текст, голос, метаданные
│       ├── ch2.json
│       ├── ch3.json
│       └── ch4.json
└── output/                 # Сгенерированные .wav (создаётся автоматически)
```

**Принцип:** `main.py` ничего не знает о содержимом текста. Он просто читает папку `chapters/`, берёт каждый JSON, шлёт в API, забирает ответ, пишет файл. Хочешь добавить 5-й кусок? Просто положи `ch5.json`. Хочешь сменить модель? Правь один ключ в `settings.json`.

---

### 📄 1. `config/settings.json`
```json
{
  "api_key": "sk-or-v1-xxxxxxxxxxxxxxxxxxxxxxxx",
  "base_url": "https://openrouter.ai/api/v1",
  "model": "google/gemini-3.1-flash-tts-preview",
  "output_dir": "./output",
  "retry_attempts": 3,
  "retry_delay_sec": 5,
  "http_referer": "https://github.com/your-username/tts-pipeline",
  "app_title": "Gemini TTS Pipeline"
}
```
*Примечание:* `HTTP-Referer` и `X-Title` обязательны для OpenRouter. Без них 401/403.

---

### 📄 2. `config/chapters/ch1.json` (остальные по той же схеме)
```json
{
  "id": "ch1",
  "title": "Сырая прогулка и Архив глюков",
  "voice": "Algenib",
  "text": "[slow] Рыбный ряд в пять утра пах гнилью, кровью и жизнью — что, в общем-то, одно и то же. Маркус Торн стоял у лотка с сельдью, закрыв глаза и позволяя городу врубаться в него без наркоза. Это называлось «сырой прогулкой» — ритуал защиты, а не удовольствия. Слишком долго в архиве, над картами и нитями, — и рассудок начинает думать, что мир помещается в схему. Это была болезнь необратимой чистоты. Единственным лекарством оставался хаос.\n\n[dry] Смёрзшаяся рыба, ругань грузчиков, звук лопнувшего ведра, чужая ладонь, случайно задевшая плечо. Кто-то кашлял — долго, с привкусом серьёзного. Запах махорки мешался с гарью из пекарни за углом. Торн стоял в центре всего этого и дышал.\n\n[building intensity] В подвале здания окружного суда на Кривом переулке, за дверью с латунной табличкой «Бюро исторических связей» (буква «е» в слове «Бюро» была криво выбита — брак литейщика, сохранявшийся вот уже двенадцать лет), помещалась его настоящая работа. Официально — архивариус. Неофициально — диагност. «Хирург связей», как он записывал себя в тетрадях, которых никто не видел.\n\n[softly] В жестяной коробке на полке хранился «архив глюков». Торн перебирал его каждую неделю, как чётки, только инверсно: не ради покоя, а ради беспокойства. Вот ржавый гвоздь — выпал из подковы городового Степанова в 1891-м, заставил его свернуть к кузнецу, и именно там нашёлся вор, которого искали три месяца. Страница отчёта с неверным диагнозом 1892 года: врач спутал холеру с тифом, объявил ложный карантин, закрыл квартал — и тем самым случайно сохранил торговые связи, которые иначе бы разорвались в кризис девяносто третьего. Кусок кирпича с тремя царапинами: их оставил мальчик Антон Рябов в 1854-м перед отправкой на войну, с которой не вернулся; его вдова вышла за вдовца, их сын в 1889-м вытащил тонущего ребёнка из реки, умея плавать, потому что... нить уходила в темноту и не заканчивалась нигде.\n\n[resigned] Каждый месяц Торн сжигал карту. Строил паутину три недели — и поджигал угол в жаровне. «Костёр»: баланс между созданием системы и отказом ей поклоняться. Карта, которую не сжигаешь, превращается в догму — начинаешь на неё молиться вместо того, чтобы думать. Он знал это потому, что боялся его своим главным страхом: стать закрытой системой, идеальной логической петлёй, отрезанной от живого хаотичного мира. Без периодического костра страх становился реальностью."
}
```
*(Остальные `ch2.json`...`ch4.json` заполняешь аналогично, меняя `id`, `title`, `voice` и вставляя текст с тегами из предыдущего ответа.)*

---

### 🐍 3. `main.py` (логика)
```python
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
        # OpenRouter/Gemini структура
        choice = resp["choices"][0]["message"]
        
        # Ищем аудио: inline_data (base64) или audio_url
        if "parts" in choice:
            part = choice["parts"][0]
            if "inline_data" in part:
                audio_b64 = part["inline_data"]["data"]
            elif "audio_url" in part:
                # Если ссылка - качаем
                logger.info("📥 Скачиваем аудио по ссылке...")
                audio_b64 = base64.b64encode(requests.get(part["audio_url"]).content).decode()
            else:
                raise ValueError("В ответе нет inline_data или audio_url")
        else:
            raise ValueError("Неожиданная структура ответа API")

        usage = resp.get("usage", {})
        in_tok = usage.get("prompt_tokens", 0)
        out_tok = usage.get("completion_tokens", 0)
        # Тариф OpenRouter: $1/1M вход, $20/1M выход
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

if __name__ == "__main__":
    TTSPipeline().run()
```

---

### 🛠 Как запускать и что учесть
1. `pip install requests`
2. Положи файлы по структуре выше.
3. Вставь свой `api_key` в `config/settings.json`.
4. `python main.py`
5. Скрипт сам отсортирует файлы по алфавиту (`ch1.json` → `ch4.json`), отправит, сохранит `output/ch1.wav` и т.д.

**Нюансы, которые не лечатся кодом:**
- `completion_tokens` в ответе OpenRouter для TTS — это **аудио-токены**. Они считаются иначе, чем текстовые. Формула `out_tok * 20 / 1M` даст ballpark, но точная цена зависит от длительности и семплрейта. Реальный чек увидишь в дашборде OpenRouter.
- Если модель вернёт текст вместо аудио (бывает при рандомных 500-х или перегрузе), скрипт упадёт на `_extract_audio_and_usage`. Это фича, а не баг — лучше сломаться явно, чем молча сохранить битый файл.
- Для мульти-спикера в одном куске: замени `voice` в JSON на список, а в `_build_payload` собери `MultiSpeakerVoiceConfig`. Но для этого текста хватит одиночных голосов с тегами — модель сама переключает интонацию.

Если нужно добавить параллельную отправку (async) или склейку `.wav` с кроссфейдами — пиши. Сейчас сделано так, чтобы ты мог править тексты/голоса без залезания в код.
