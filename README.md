# FleetGuard AI

ИИ-сервис для таксопарков и проката: водитель фотографирует кузов с четырёх сторон до и после
смены, система находит **новые** повреждения, формирует акт осмотра, а менеджер задаёт вопросы
по данным в чате.

Реализация идёт по плану в [`PLAN.md`](./PLAN.md), правила проекта — в [`AGENTS.md`](./AGENTS.md).

## Стек

- Backend: Python 3.12, FastAPI, SQLAlchemy 2 + Alembic, Pydantic v2, Celery + Redis, PostgreSQL
- Хранилище: MinIO (S3 API)
- CV: OpenCV, Ultralytics YOLO (seg), PyTorch
- LLM: LangChain, structured output, единая точка вызова — `llm/client.py`
- Frontend: Next.js (App Router), TypeScript, Tailwind
- Инфра: Docker Compose, GitHub Actions

## Структура

```
fleetguard-ai/
  AGENTS.md, PLAN.md, README.md
  docker-compose.yml, .env.example
  backend/     FastAPI-приложение, тесты, Dockerfile
  cv/          inference, training, eval-наборы
  llm/         клиент провайдера, схемы, промпты, ассистент, evals
  frontend/    Next.js-приложение
  infra/       prod compose, Caddy, бэкапы
  docs/        архитектура, model card, демо-сценарий
```

## Быстрый старт (Docker)

```bash
cp .env.example .env      # заполнить POSTGRES_PASSWORD, MINIO_*, JWT_SECRET
docker compose up -d --build
curl http://localhost:8000/health
```

Ожидаемый ответ:

```json
{"status":"ok","version":"0.1.0","environment":"development"}
```

Сервисы и порты на хосте:

| Сервис | Адрес | Назначение |
|---|---|---|
| backend | http://localhost:8000, `/docs` | API и Swagger |
| postgres | `localhost:5433` | БД (5433, чтобы не конфликтовать с локальным PostgreSQL) |
| redis | `localhost:6379` | очередь Celery |
| minio | http://localhost:9000, консоль `:9001` | S3-хранилище фото |
| minio-init | — | создаёт бакет `fleetguard` и закрывает анонимный доступ |
| frontend | http://localhost:3000 | Next.js: вход, регистрация, машины |

## Локальная разработка без Docker

Нужен Python 3.12+ (проверено на 3.13) и доступный PostgreSQL.

```bash
py -3 -m venv .venv
.venv\Scripts\activate
pip install -r backend/requirements-dev.txt

cd backend
pytest -q
ruff check . && ruff format --check .
uvicorn app.main:app --reload --port 8000
```

Конфигурация читается из переменных окружения и файла `.env` в корне репозитория; значения по
умолчанию рассчитаны на docker compose. Для локального PostgreSQL укажите свой `DATABASE_URL`.

### Frontend

```bash
cd frontend
npm install
npm run dev        # http://localhost:3000
npm run lint
npm run build
```

Фронтенд проксирует `/api/*` в `BACKEND_URL` (по умолчанию `http://127.0.0.1:8000`), поэтому
backend должен быть запущен. Подробности — в [`frontend/README.md`](./frontend/README.md).

## API (v1)

Базовый путь `/api/v1`. JWT хранится в httpOnly-cookie `access_token`, ошибки приходят в формате
`{"error": {"code": "...", "message": "..."}}`.

| Метод | Путь | Доступ |
|---|---|---|
| POST | `/api/v1/auth/register-org` | создаёт организацию и первого админа, ставит cookie |
| POST | `/api/v1/auth/login` | вход по email и паролю |
| POST | `/api/v1/auth/logout` | очищает cookie |
| GET | `/api/v1/auth/me` | текущий пользователь и организация |
| POST | `/api/v1/users` | только admin: создать менеджера или водителя |
| GET | `/api/v1/vehicles?search=` | список машин организации, поиск по номеру и модели |
| POST | `/api/v1/vehicles` | admin/manager: добавить машину |
| GET | `/api/v1/vehicles/{id}` | карточка машины |
| PATCH | `/api/v1/vehicles/{id}` | admin/manager: изменить машину |
| DELETE | `/api/v1/vehicles/{id}` | admin/manager: удалить машину без истории |
| POST | `/api/v1/inspections` | начать осмотр `before` или `after` (для `after` нужен `pair_id`) |
| POST | `/api/v1/inspections/{id}/photos?side=front` | multipart-загрузка фото: качество, флаги и оценка |
| POST | `/api/v1/inspections/{id}/finish` | завершить осмотр: нужны 4 фото, ответ `202 processing` |
| GET | `/api/v1/inspections/{id}` | статус, фото с подписанными ссылками и повреждения |

Правила осмотров: осмотр «до» получает новый `pair_id`; осмотр «после» принимается только с
`pair_id` завершённого осмотра «до» той же машины, и только один на пару. Финиш требует все четыре
стороны — `front`, `back`, `left`, `right`.

Загрузка фото принимает JPEG, PNG и WebP до 10 МБ (`MAX_UPLOAD_BYTES`) и отвечает:

```json
{"photo_id": "…", "side": "front", "width": 1200, "height": 900,
 "quality": {"ok": false, "flags": ["blurry"], "score": 0.506}}
```

Повторная съёмка той же стороны заменяет фото и удаляет старый объект из хранилища. Ответ с
`ok=false` — не отказ: фото сохранено, а фронтенд решает, просить ли переснять.

## CI

[`.github/workflows/ci.yml`](./.github/workflows/ci.yml) запускается на каждый push и pull request:

- **backend** (Python 3.12): `ruff check`, `ruff format --check`, `pytest`;
- **frontend** (Node 22): `npm ci`, `npm run lint`, `npm run build`.

## Хранилище

Фотографии лежат в приватном S3-бакете (`S3_BUCKET`, по умолчанию `fleetguard`); анонимный доступ
закрыт в `minio-init`. Наружу отдаются только подписанные ссылки с коротким сроком
(`S3_PRESIGN_EXPIRE_SECONDS`, по умолчанию 900 секунд, максимум 7 суток).

В Docker backend обращается к MinIO по `http://minio:9000`, а ссылки для браузера подписываются
через `S3_PUBLIC_ENDPOINT_URL=http://localhost:9000` — иначе браузер не резолвит имя `minio`.
Если переменная пуста, используется `S3_ENDPOINT_URL`.

Тесты хранилища работают на `moto`, поэтому MinIO в CI не нужен:
`cd backend && pytest tests/test_storage.py -q`.

## Качество фото

Перед сохранением фото нормализуется: исправляется EXIF-ориентация, прозрачность заливается белым,
картинка перекодируется в JPEG (`PHOTO_JPEG_QUALITY`, по умолчанию 90) — это же убирает метаданные.
Файл кладётся под случайным ключом `photos/{org_id}/{inspection_id}/{uuid}.jpg`.

`backend/app/services/quality.py` считает дисперсию Лапласа (резкость), среднюю яркость и разрешение
и возвращает флаги `blurry`, `too_dark`, `too_bright`, `low_resolution` плюс оценку 0..1.
Пороги задаются в `.env`: `QUALITY_MIN_WIDTH`, `QUALITY_MIN_HEIGHT`, `QUALITY_BLUR_THRESHOLD`,
`QUALITY_MIN_BRIGHTNESS`, `QUALITY_MAX_BRIGHTNESS`. Их стоит откалибровать под камеры парка: на
синтетическом эталоне резкое фото даёт ~150–260, размытие по Гауссу радиусом 2 — ~12.

## Мастер съёмки

`/inspections/new?vehicleId=…` — мастер на четыре шага (`front`, `back`, `left`, `right`) с
подсказкой, как встать к машине. Поток:

1. Выбор машины и кнопка «Начать осмотр» — осмотр создаётся на сервере с `kind=before`.
2. Съёмка через `<input type="file" accept="image/*" capture="environment">`; превью строится
   на клиенте, чтобы не зависеть от сети.
3. Фото сжимается в браузере до 1600 px по длинной стороне (JPEG, качество 0.85) и уходит
   multipart-запросом; сервер отвечает качеством и флагами.
4. При `ok=false` вкладка стороны помечается «переснять», показываются причины и кнопка
   «Переснять». Плохое фото не блокирует финиш: в темноте это привело бы к тупику.
5. «Завершить осмотр» доступен, когда сняты все четыре стороны, и переводит осмотр в
   `processing`.

Черновик хранится в `sessionStorage` (`fleetguard:inspection:{vehicleId}`): после перезагрузки
мастер восстанавливает осмотр через `GET /inspections/{id}`, подставляет подписанные ссылки на
уже загруженные фото и открывает первую неснятую сторону. Запись удаляется после финиша.

EXIF-ориентация исправляется через `createImageBitmap(..., {imageOrientation: "from-image"})`
с запасным путём через `<img>`; превью — data URL, поэтому не нужно освобождать blob-ссылки.

## Страница осмотра

`/inspections/{id}` показывает статус (`draft`, `uploading`, `processing`, `done`, `failed`), машину,
время начала и завершения, счётчики фото и замечаний, а также галерею четырёх сторон. Фото
отдаются по подписанным ссылкам, флаги качества выводятся под кадром.

Пока осмотр в `processing`, страница сама обновляет статус каждые 5 секунд (12 попыток, затем
кнопка «Обновить»). При `failed` показывается `failure_reason`. Чужой или удалённый осмотр даёт
«Осмотр не найден» без раскрытия данных.

## Статус

### Неделя 1. Фундамент

- [x] Д1. Структура репозитория, Docker Compose (postgres, redis, minio), `/health`, README
- [x] Д2. Модели БД и Alembic
- [x] Д3. Авторизация и организации
- [x] Д4. CRUD машин
- [x] Д5. Скелет фронтенда: вход, регистрация организации, список машин с поиском и добавлением
- [x] Д6. CI: GitHub Actions — ruff, ruff format, pytest, `npm run lint` и `npm run build`
  (зелёный прогон появится после первого push в GitHub)

### Неделя 2. Осмотры и загрузка фото

- [x] Д1. Хранилище: сервис MinIO/S3, загрузка, чтение и подписанные ссылки
- [x] Д2. Осмотры: `POST /inspections`, пары before/after и запрет финиша без 4 фото
- [x] Д3. Загрузка фото: валидация по содержимому, нормализация, `quality.py` с флагами брака
- [x] Д4. Мастер съёмки: 4 шага, подсказки, сжатие в браузере, пересъёмка и черновик
- [x] Д5. Страница осмотра: статусы, галерея фото, автообновление обработки
- [x] Д6. Тесты: граничные случаи жизненного цикла осмотра

## Безопасность

- Все запросы к данным фильтруются по `org_id` из сессии; `org_id` никогда не берётся из тела
  запроса, query-параметров или аргументов LLM.
- Секреты только в `.env` / переменных окружения; `.env` в git не попадает.
- Загрузка файлов: проверка типа по содержимому, лимит 10 МБ, случайные ключи, подписанные ссылки.
- Пароли хэшируются, токены и содержимое фото не логируются.
- Текст с фото, госномера и сообщения пользователей считаются недоверенными данными.

## Лицензии

- Ultralytics YOLO распространяется по AGPL-3.0 — для портфолио допустимо, ограничение указано
  в README и Model Card.
- Лицензии датасетов и шрифтов для PDF проверяются перед публикацией.
