# Как писать промпты для видеомоделей

Общие правила для всех моделей:
- Один шот = одно действие, 5–10 секунд, формат 9:16.
- Порядок в промпте: **субъект → действие → окружение → камера → свет и стиль → настроение**.
- Камеру называем явно: static, slow push-in, handheld, tracking, close-up / medium / wide.
- Текст на экране модели рисуют плохо: его добавляем на монтаже, в промпт не пишем.
- Лица и руки крупным планом — зона риска. Лучше medium shot или естественные движения.
- Для UGC-стиля: «shot on smartphone, handheld, natural window light, authentic, unpolished».
- Для серии шотов с одним героем: один стартовый кадр (image-to-video) и одинаковое описание героя во всех промптах.

## Kling
- Хорошо работает image-to-video со стартовым кадром, есть режим start/end frame.
- Структура: `[Subject + appearance], [action], [setting]. Camera: [movement]. Lighting: [..]. Style: [..].`
- Поддерживает negative prompt: `blurry, distorted hands, extra fingers, text, watermark, logo`.
- Длительность 5 или 10 с. Темп задавай словами: «slowly», «gently», «suddenly».

## Seedance (ByteDance)
- Сильная сторона — язык камеры и мультишоты внутри одной генерации.
- Мультишот: опиши шоты по порядку через `Shot 1: … Shot 2: …` или `[cut to]`, по одному действию на шот.
- Принимает референс-изображения (персонаж, стиль). Указывай, что взять из референса: «keep the character from reference image».
- Хорошо держит реалистичную пластику людей: подходит для эмоциональных семейных сцен.

## MiniMax (Hailuo)
- Сильная сторона — естественное движение людей и эмоции на лице.
- Движение камеры задаётся командами в квадратных скобках внутри текста: `[Push in]`, `[Pull out]`, `[Pan left]`, `[Tracking shot]`, `[Static shot]`, `[Zoom in]`.
- Промпт — связный абзац с последовательностью событий во времени: «First…, then…, finally…».
- Длительность 6–10 с.

## Шаблон стартового кадра (image prompt)
`Vertical 9:16 photo, [subject], [setting], [lighting], shot on iPhone, shallow depth of field, authentic, no text`

> Модели быстро обновляются. Если в Kling, Seedance или MiniMax появились новые возможности или синтаксис, обновите этот файл: Claude берёт правила отсюда.
