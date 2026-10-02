# YouTube AI Outreach Agent (DeepSeek)

Автономный ИИ-агент (ReAct) для анализа каналов YouTube, выявления точек роста / упущенной монетизации и генерации персонализированных Cold Outreach сообщений.

## 🚀 Возможности
- **Автономный агент (DeepSeek Function Calling)**: Сам запрашивает данные канала через YouTube Data API, изучает последние видео, описания, монетизацию и комментарии зрителей.
- **Поиск каналов по нишам**: Встроенный поиск каналов по ключевым словам/нише с отображением подписчиков, просмотров и видео.
- **Персонализированный Cold DM**: Формирует четкое, целевое предложение без шаблонных заглушек вроде `[Name]`.
- **Сохранение отчетов**: Автоматически сохраняет аудит и готовый Cold DM в папку `reports/channels/YYYY-MM-DD/`.
- **Удобный GUI**: Современный темный интерфейс на Tkinter с живым логом мыслей агента.

---

## 🛠️ Установка и запуск

1. Установите зависимости:
```powershell
pip install -r requirements.txt
```

2. Запустите графический интерфейс (GUI):
- Двойным кликом по `start_gui.bat`, либо в терминале:
```powershell
python app_gui.py
```

3. Либо запустите консольного агента (CLI):
```powershell
set YOUTUBE_API_KEY=your_google_youtube_key
set DEEPSEEK_API_KEY=your_deepseek_key
python agent.py @handle_or_url
```

---

## 🔑 Ключи API
- **YouTube Data API v3**: Получается в [Google Cloud Console](https://console.cloud.google.com/).
- **DeepSeek API Key**: Получается на [platform.deepseek.com](https://platform.deepseek.com/) (модель `deepseek-chat`).

Ключи сохраняются локально в файлы `api_key.local.txt` и `deepseek_key.local.txt` (добавлены в `.gitignore`).

---

## 🧪 Тестирование

Запуск тестов:
```powershell
python test_agent.py
```
