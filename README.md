# World AI Size Map

Отдельный FastAPI-сервис для Render: OpenStreetMap + поиск стран/мест + перенос границ с сохранением реального размера + MongoDB + Groq + Cloudflare FLUX.

## Render
Build command: `pip install -r requirements.txt`
Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`

## Environment Variables
- `MONGODB_URI`
- `GROQ_API_KEY`
- `CLOUDFLARE_ACCOUNT_ID`
- `CLOUDFLARE_API_TOKEN`
- `CLOUDFLARE_MODEL` (optional; default `@cf/black-forest-labs/flux-1-schnell`)

База MongoDB выбирается прямо в коде: `world_ai_size_map`.

## Что уже есть
- OpenStreetMap / Leaflet
- поиск через Nominatim с GeoJSON-границами
- добавление нескольких объектов
- удаление одного объекта / очистка всех
- перетаскивание геометрии с широтной коррекцией масштаба (TrueSize-style)
- MongoDB-сохранение состояния браузерной сессии
- Groq prompt для Cloudflare
- Cloudflare FLUX image generation
- переключатель AI-изображений
- простой AI Globe с подписью

## Важно
Nominatim имеет ограничения на частоту запросов; поэтому поиск выполняется только по кнопке или Enter, а не автокомплитом на каждый символ.
