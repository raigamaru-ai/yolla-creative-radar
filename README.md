# Yolla Creative Radar

Каждую пятницу пайплайн собирает рекламу конкурентов (Boss Revolution, Rebtel, Libon, CallTuv, Africallshop, Talk360) из Facebook и TikTok Ad Library за прошедшие 7 дней. Он разбирает, что в ней работает, и кладёт в Google Drive готовые сценарии и промпты для Kling, Seedance и MiniMax.

## Как устроено

| Модуль | Кто делает | Результат в папке недели на Drive |
|---|---|---|
| 1. Сбор креативов и метрик | `python -m radar prep` → Apify | `00 Таблица креативов` (Google Sheet) |
| 2. Скачивание | тот же `prep`: видео, ключевые кадры, транскрипт | `01 Креативы конкурентов/`, `02 Кадры-референсы/` |
| 3. Анализ: что сработало | Claude по [SKILL.md](.claude/skills/weekly-creative-radar/SKILL.md) | раздел документа |
| 4. Сценарии, промпты, референсы | Claude + `python -m radar publish` | `Yolla — сценарии и промпты — <дата>` (Google Doc) |

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
   - переменные `APIFY_TOKEN` и `GOOGLE_OAUTH_TOKEN_JSON` (всё содержимое `google-oauth-token.json`);
   - сетевой доступ: Full или allowlist `api.apify.com`, `*.googleapis.com`, `*.fbcdn.net`, `*.tiktokcdn.com`, `*.tiktokcdn-eu.com`, `huggingface.co` (модель транскрипции), `pypi.org`, `files.pythonhosted.org`.
5. **Бриф:** заполните [prompts/yolla_brief.md](prompts/yolla_brief.md): офферы, цвета, приоритетные гео.

Проверка: `python -m radar doctor`.

## Доступ для команды
- **Результаты:** папка `Yolla Creative Radar` открыта по ссылке (или расшарьте её конкретным людям в Drive). Внутри — папки недель, таблицы и документы.
- **Ручной запуск:** любой участник с Claude Code клонирует репозиторий и пишет `/weekly-creative-radar`. Это нужно, например, чтобы пересобрать неделю: «запусти радар за 2026-11-27».
- **Правки** (конкуренты, веса, правила промптов) вносятся через `config.yaml` и `prompts/*.md` в репозитории.

## Локальный тест без ключей
```bash
python -m radar prep --date 2026-11-27 --no-drive --fixtures tests/fixtures
```
