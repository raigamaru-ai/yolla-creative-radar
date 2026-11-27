# Как писать промпты для видео- и имиджмоделей

## Главные правила (решение команды, 27.11.2026)

1. **Один ролик — один промпт.** Видео 10–20 с не делим на 5-секундные отрезки и не пишем отдельный промпт на каждый шот. Пишем один цельный промпт на весь ролик. Смена планов описывается внутри него по таймкодам: `0-3s: … 3-8s: … 8-15s: …` (multi-shot внутри одной генерации).
2. **Звук генерирует модель.** Если в сценарии есть войсовер, диктор или говорящий в кадре персонаж, реплики дословно пишутся в промпт, с указанием, кто говорит, на каком языке, с каким акцентом и интонацией. Пример: `The mother says in Nigerian-accented English, warm and emotional: "I hear you so clearly, my son!"` или `Voiceover (male, friendly, Spanish, Cuban accent): "Llama a Cuba desde $0.04 el minuto."`. Добавляй фоновый звук и музыку: `Sound: soft afrobeat music, room ambience`. Отдельная озвучка на монтаже не предполагается.
3. **Субтитры и текст на экране генерирует модель.** Если в сценарии есть субтитры или надписи, точный текст, шрифт, место и момент появления пишутся в промпт. Пример: `Burned-in subtitles at the bottom, bold white sans-serif with teal outline, synced to speech: "Mom doesn't have WhatsApp?"` или `At 12s a large on-screen text appears in the center: "from $0.04 per minute"`. Текст держи коротким (до 6–7 слов на экран), цифры и цены пиши ровно как в брифе.
4. **Длина ролика — до 15 с.** Это максимум, который держат Kling 3.0 и Seedance за одну генерацию. Ролик 16–20 с пиши так же одним промптом и помечай `⚠️ нужна модель с роликами > 15 с (Kling 4.0 — до 30 с)`. Если какая-то модель не умеет нужную длину, звук или текст, дай для неё сокращённую версию и помечай, чего в ней нет.

## Структура промпта ролика

```
[Format: vertical 9:16, 15 seconds, photorealistic, shot on smartphone / cinematic]
[Character(s): внешность, возраст, одежда, где находятся — одинаково на весь ролик]
0-3s: [хук — действие, камера, реплика/звук, текст на экране]
3-9s: [развитие — действие, камера, реплика, субтитры]
9-15s: [развязка и CTA — действие, реплика, финальный текст на экране]
Sound: [музыка, фон, характер голоса]
Style: [свет, цвет: teal and white palette, accents #4BCFD0]
Avoid: [blurry, distorted hands, extra fingers, misspelled text, competitor logos, orange accents]
```

Что ещё важно:
- Камеру называй явно: static, slow push-in, handheld, tracking, close-up / medium / wide.
- Лица и руки крупным планом — зона риска. Лучше medium shot или естественные движения.
- Для UGC-стиля: `shot on smartphone, handheld, natural window light, authentic, unpolished`.
- Описание героя должно быть одинаковым на весь промпт: тогда модель держит персонажа между сменами плана.
- Логотип Yolla и реальный экран приложения модель не нарисует правильно. Для них оставь место (`clean area in the last 2 seconds for logo end card`) и помечай `[вставить логотип / запись экрана Yolla]`.

## Kling (3.0)
- Один промпт до ~2500 символов, длительность 3–15 с, multi-shot внутри ролика, нативный звук и речь (`audio: native`), форматы 16:9 / 9:16 / 1:1.
- Отдельного negative prompt нет: пиши `Avoid: …` в конце промпта.
- Темп задавай словами: `slowly`, `gently`, `suddenly`.

## Seedance (ByteDance)
- Сильная сторона — язык камеры, мультишоты и пластика людей. Подходит для эмоциональных семейных сцен.
- Смены планов: `Shot 1: … [cut to] Shot 2: …` с таймкодами, по одному действию на план.
- Принимает референс-изображения (персонаж, стиль): `keep the character from reference image`.
- Звук, речь и текст на экране пиши так же, как в Kling. Если версия модели их не поддерживает, это нужно пометить.

## MiniMax (Hailuo)
- Сильная сторона — естественное движение людей и эмоции на лице.
- Камера — командами в квадратных скобках: `[Push in]`, `[Pull out]`, `[Pan left]`, `[Tracking shot]`, `[Static shot]`, `[Zoom in]`.
- Промпт — связный абзац с последовательностью во времени: `First…, then…, finally…`.
- Длительность обычно 6–10 с: для ролика 15 с давай сжатую версию на ≤ 10 с и помечай это. Если версия не генерирует звук или текст, это тоже нужно пометить.

## Статичные креативы (баннеры)

Модели для статики: Kling Image, Midjourney, Imagen, Seedream. Промпт:

```
[Format: square 1:1 / vertical 9:16 / 4:5 social ad]
[Сцена: кто, где, эмоция, композиция]
Text on image: headline "…" (верх, bold sans-serif, dark teal #1C6E6F), price badge "from $0.04 per minute" (teal #4BCFD0 rounded badge, white text), CTA button "Download Yolla" (низ)
Style: [photo / flat illustration / 3D], teal and white palette, clean, lots of white space
Avoid: misspelled text, extra text, competitor logos, orange
```

- Текст пиши в промпт дословно, в кавычках: современные модели рисуют короткий текст сами.
- Логотип — `[вставить yolla-logo-*.svg]`, место под него нужно оставить.
- Делай 2–3 варианта текста (A/B) к одной картинке.

> Модели быстро обновляются. Если в Kling, Seedance или MiniMax появились новые возможности или синтаксис, обновите этот файл: Claude берёт правила отсюда.
