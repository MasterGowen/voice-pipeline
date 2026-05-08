# TTS Pipeline

Генерация аудио из текста через OpenRouter/Gemini TTS API.

## Установка через pipx

```bash
pipx install .
```

Или из текущей директории:

```bash
pipx install git+https://github.com/MasterGowen/tts-pipeline.git
```

## Использование

После установки команда доступна как `tts-pipeline`:

```bash
tts-pipeline
```

Или напрямую через Python:

```bash
python -m tts_pipeline.main
```

## Конфигурация

1. Создайте файл `config/settings.json` с вашим API ключом:

```json
{
  "api_key": "sk-or-v1-your-api-key",
  "base_url": "https://openrouter.ai/api/v1",
  "model": "google/gemini-3.1-flash-tts-preview",
  "output_dir": "./output",
  "retry_attempts": 3,
  "retry_delay_sec": 5
}
```

2. Разместите JSON-файлы с текстом в папке `config/chapters/`:

```json
{
  "text": "Текст для озвучивания",
  "voice": "Kore"
}
```

## Разработка

```bash
pip install -e ".[dev]"
```

## Лицензия

MIT
