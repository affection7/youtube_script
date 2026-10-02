# YouTube AI Outreach Agent (DeepSeek)

Python-приложение для анализа YouTube-каналов, поиска возможностей монетизации и генерации персонализированных Cold Outreach сообщений через DeepSeek.

## Возможности

- ReAct-агент с DeepSeek Function Calling.
- Анализ канала, видео, статистики и комментариев аудитории.
- Определение текущей монетизации по матрице.
- Извлечение внешних ссылок и их классификация.
- Risk-флаги для referral farming, token hype и продвижения торговых сигналов.
- Rule-based проверка Cold DM перед сохранением.
- Поиск каналов по нише с кэшированием результатов.
- GUI с полным отчетом, отдельной вкладкой Cold DM, копированием сообщения и фильтрами по подписчикам.
- Текстовые отчеты в `reports/channels/YYYY-MM-DD/`.

## Требования

- Python 3.11 или новее.
- YouTube Data API v3 key.
- DeepSeek API key.

## Установка

```powershell
pip install -r requirements.txt
```

Ключи задаются через переменные окружения. Их нельзя коммитить или записывать в логи.

### Windows PowerShell

```powershell
$env:YOUTUBE_API_KEY = "your_google_youtube_key"
$env:DEEPSEEK_API_KEY = "your_deepseek_key"
```

### Linux/macOS

```bash
export YOUTUBE_API_KEY="your_google_youtube_key"
export DEEPSEEK_API_KEY="your_deepseek_key"
```

Файл `.env` можно использовать как локальное хранилище переменных при загрузке его средствами окружения; приложение не сохраняет ключи на диск. Файл `.env` исключен из Git.

## Запуск GUI

Windows:

```powershell
python app_gui.py
```

или двойным кликом по `start_gui.bat`.

Linux/macOS:

```bash
./start_gui.sh
```

Скрипт автоматически активирует локальный `venv`, если он существует.

## Запуск CLI

```powershell
python agent.py @handle_or_url
```

Также поддерживаются URL каналов и Channel ID. Ссылки на отдельные видео отклоняются.

## Тесты

```powershell
python -m unittest -v
```

Текущий набор содержит 41 тест.

## Структура отчетов

- `analysis_<channel>.txt` — полный текстовый аудит с матрицей монетизации.
- `outreach_dm_<channel>.txt` — проверенный Cold DM.

Сгенерированные отчеты и локальные ключи не добавляются в Git.
