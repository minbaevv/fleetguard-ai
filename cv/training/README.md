# Данные и веса модели

Каталог для скриптов подготовки датасета, обучения и оценки. Датасеты и веса в git не коммитятся
(`datasets/` и `cv/weights/` в `.gitignore`).

## Подготовка датасета

`prepare_dataset.py` принимает COCO-разметку с полигонами и раскладывает её в формат YOLO-seg:

```bash
python cv/training/prepare_dataset.py \
  --images datasets/car-damage/images \
  --annotations datasets/car-damage/annotations/instances.json \
  --out datasets/car-damage-yolo
```

Скрипт:

- проверяет каждый файл через Pillow: битые, пустые и отсутствующие изображения попадают в отчёт;
- переводит абсолютные пиксельные полигоны в нормализованные координаты `0..1`, обрезает выход за
  границы кадра и отбрасывает вырожденные полигоны;
- поддерживает шесть классов: `dent`, `scratch`, `crack`, `glass_shatter`, `lamp_broken`,
  `tire_flat`;
- делит изображения на `train` / `val` / `test` = 70 / 15 / 15 детерминированно по `--seed`
  (по умолчанию 42);
- пишет `prepare_report.json` со счётчиками, пропусками и причинами.

RLE-маски не поддерживаются: для них нужен COCO polygon. Если названия категорий в источнике
отличаются, передайте `--class-map mapping.json` вида
`{"broken headlight": "lamp_broken"}`. Безымянные категории и чужие `image_id` пропускаются.

Выходная структура:

```
dataset.yaml
images/{train,val,test}/...
labels/{train,val,test}/...   # один polygon на строку: class x1 y1 x2 y2 ...
prepare_report.json
```

Изображение без валидных полигонов остаётся в датасете с пустым `.txt` (негативный пример) и
считается в `negative_images`. С `--strict` скрипт возвращает код 1, если были пропуски; без флага
он завершается успешно и оставляет разбор в отчёте. Непустой `--out` перезаписывается только с
`--force`, посторонние файлы в каталоге сохраняются.

Проверки: `cd cv && pytest`, `ruff check .`, `ruff format --check .`.

## Обучение

`train.py` проверяет датасет и запускает дообучение `yolo11n-seg` по конфигу
`configs/yolo11n-seg.yaml`: 100 эпох, 640 px, batch 16, seed 42.

Сначала сухой прогон — без GPU и без Ultralytics:

```bash
python cv/training/train.py --data datasets/car-damage-yolo --dry-run
```

Реальное обучение на Colab/Kaggle с GPU:

```bash
pip install -r cv/requirements-train.txt
python cv/training/train.py --data datasets/car-damage-yolo
```

Параметры переопределяются флагами `--model`, `--epochs`, `--imgsz`, `--batch`, `--seed`,
`--device`, `--project`, `--name`. Результаты складываются в
`cv/runs/yolo11n-seg-baseline/`: `weights/best.pt`, `metrics.md`, `metrics.json`.

`metrics.md` содержит mAP50 и mAP50-95 по маскам и precision/recall по каждому классу. Оценка идёт
только на `val`; test-сплит не используется. Перед запуском проверяется `dataset.yaml`: классы
`0..N-1`, полигоны в `0..1`, у каждого изображения есть `.txt`, лишних меток нет.

### Статус Д2

Реальный прогон не выполнен: CarDD выдаётся по заявке и письму авторам, поэтому измеренных
метрик пока нет. Скрипт и тесты готовы. После получения датасета нужно выполнить команду выше и
опубликовать ссылку и sha256 `best.pt` в разделе «Правила».

## Правила

- Веса (`*.pt`, `*.pth`, `*.onnx`) в git не коммитятся.
- Ссылка на скачивание и контрольная сумма весов публикуются здесь после обучения.
- Разбиение train / val / test = 70 / 15 / 15; test не используется для подбора порогов.
- Перед публикацией проверьте лицензию датасета: открытые наборы повреждений часто разрешены
  только для исследований.
