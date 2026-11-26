# Yolla Creative Radar

Каждую пятницу пайплайн собирает рекламу конкурентов (Boss Revolution, Rebtel, Libon, CallTuv, Africallshop, Talk360) из Facebook и TikTok Ad Library за прошедшие 7 дней. Он разбирает, что в ней работает, и кладёт в Google Drive готовые сценарии и промпты для Kling, Seedance и MiniMax.

## Как устроено

| Модуль | Кто делает | Результат в папке недели на Drive |
|---|---|---|
| 1. Сбор креативов и метрик | `python -m radar prep` → Apify | `00 Таблица креативов` (Google Sheet) |
| 2. Скачивание | тот же `prep`: видео, ключевые кадры, транскрипт | `01 Креативы конкурентов/`, `02 Кадры-референсы/` |
| 3. Анализ: что сработало | Claude по [SKILL.md](.claude/skills/weekly-creative-radar/SKILL.md) | раздел документа |
| 4. Сценарии, промпты, референсы | Claude + `python -m radar publish` | `Yolla — сценарии и промпты — <дата>` (Google Doc) |
| 5. Генерация в Kling | Claude пишет `kling_jobs.json`, `python -m radar generate` | `03 Сгенерировано в Kling/`: видео до 15 с в 720p и статика (9:16, 1:1, 16:9) |
| 6. Отчёт в Telegram | Claude пишет `telegram.md`, `python -m radar notify` | сообщение в группу/чаты: выводы, сценарии, ссылки |

Запуск: облачная задача Claude Code (routine) каждую пятницу в 10:00 по Москве (`0 7 * * 5` UTC). Она клонирует этот репозиторий и выполняет skill `weekly-creative-radar`.

### Какие метрики доступны
- **Facebook Ad Library:** дата старта и окончания, активность, число вариаций креатива (collation), площадки. Охват (EU reach) есть только у показов в ЕС/UK.
- **TikTok Ad Library:** только объявления с показами в ЕС/EEA/UK (требование DSA). Есть даты первого и последнего показа и охват (unique users).
- CTR, расходов и конверсий нет ни там, ни там. Поэтому `score` = охват (если есть) × длительность показа × число вариаций, веса задаются в [config.yaml](config.yaml).

## Настройка (один раз)

1. **Apify:** аккаунт и API-токен (Settings → Integrations). На первом запуске проверьте, что акторы в `config.yaml → apify` возвращают данные. Если какой-то сломался, замените его другим: нормализация терпима к разным именам полей.
2. **Google Drive (личный «Мой диск», через OAuth):**
   - console.cloud.google.com → ваш проект → APIs & Services → Library → включите **Google Drive API**.
   - OAuth consent screen → тип **External** → название `Yolla Creative Radar`, ваш email → сохранить. Затем **Publish app** (In production): иначе токен перестанет работать через 7 дней. Проверка Google не нужна: используется только ограниченный scope `drive.file`, то есть приложение видит лишь созданные им файлы.
   - Credentials → Create credentials → **OAuth client ID** → тип **Desktop app** → скачайте JSON и положите в папку проекта как `client_secret.json`.
   - Выполните `python -m radar auth --share-with-link`. В браузере войдите в Google. На экране «Google не проверил это приложение» нажмите «Дополнительно → Перейти» (это ваше приложение), затем «Разрешить».
   - Команда создаст в «Моём диске» папку `Yolla Creative Radar`, впишет её ID в `config.yaml` и сохранит токен в `google-oauth-token.json`. С флагом `--share-with-link` папку сможет открыть любой, у кого есть ссылка.
   - (Альтернатива для Google Workspace: сервисный аккаунт + Shared Drive, переменная `GOOGLE_SERVICE_ACCOUNT_JSON`.)
3. **GitHub:** приватный репозиторий с этим кодом (облачный запуск клонирует его).
4. **Облачное окружение Claude** (claude.ai/code → Environments):
   - переменные `APIFY_TOKEN`, `GOOGLE_OAUTH_TOKEN_JSON` (всё содержимое `google-oauth-token.json`), `KLING_API_KEY` (kling.ai/dev/api-key; нужен пакет ресурсов для видео и картинок), `TELEGRAM_BOT_TOKEN` и `TELEGRAM_CHAT_IDS` (см. ниже);
   - сетевой доступ: Full или allowlist `api.apify.com`, `*.googleapis.com`, `*.fbcdn.net`, `*.tiktokcdn.com`, `*.tiktokcdn-eu.com`, `huggingface.co` (модель транскрипции), `api.telegram.org`, `api-singapore.klingai.com` и CDN результатов Kling (`*.klingai.com`, `*.kling.ai`), `pypi.org`, `files.pythonhosted.org`.
5. **Kling:** лимиты (число роликов, длительность, потолок units за прогон) — в `config.yaml → kling`. Выключить генерацию: `kling.enabled: false`.
6. **Telegram (отчёт после каждого прогона):**
   - В Telegram откройте @BotFather → `/newbot` → получите токен бота.
   - Получатели: проще всего создать группу (например «Yolla Creative Radar»), добавить туда бота и нужных людей. Можно и в личку: каждый человек должен сам написать боту `/start` (бот не может первым написать человеку).
   - Узнать ID чатов: на своём компьютере `export TELEGRAM_BOT_TOKEN=...` и `python -m radar telegram-chats` (перед этим напишите сообщение в группе или боту). ID группы — отрицательное число.
   - В облачное окружение: `TELEGRAM_BOT_TOKEN` и `TELEGRAM_CHAT_IDS` (ID через запятую, например `-1001234567890,123456789`).
7. **Бриф:** заполните [prompts/yolla_brief.md](prompts/yolla_brief.md): офферы, цвета, приоритетные гео.

Проверка: `python -m radar doctor`.

## Доступ для команды
- **Результаты:** папка `Yolla Creative Radar` открыта по ссылке (или расшарьте её конкретным людям в Drive). Внутри — папки недель, таблицы и документы.
- **Ручной запуск:** любой участник с Claude Code клонирует репозиторий и пишет `/weekly-creative-radar`. Это нужно, например, чтобы пересобрать неделю: «запусти радар за 2026-11-27».
- **Правки** (конкуренты, веса, правила промптов) вносятся через `config.yaml` и `prompts/*.md` в репозитории.

## Локальный тест без ключей
```bash
python -m radar prep --date 2026-11-27 --no-drive --fixtures tests/fixtures
```
