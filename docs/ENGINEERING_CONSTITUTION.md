# WORLD ENGINE — технический стандарт и Stage 8

Дата фиксации: 2026-09-22. Основа аудита: `main` на `eda771f6c556143636200a6b92e66b7cdb573c01`. Документ задаёт направление дальнейшей разработки Codex. Примеры путей и выводы о коде проверены в указанной ревизии; показатели готовности и сведения о deployed SHA из предыдущего аудита являются оценками, а не результатом сегодняшнего production замера.

## Цель и текущая оценка

Цепочка продукта: **источники → свидетельства → нормализованные события → состояние мира → эффекты → восприятие и решения акторов → взаимодействия → каскады → сценарии → вероятностные прогнозы → проверка на реальности → объяснение**. Авторитетный результат создаёт воспроизводимая модель состояния, а не LLM или интерфейс.

| Измерение | Предыдущая экспертная оценка | Как читать |
| --- | ---: | --- |
| Архитектурный прототип | 65–70% | Есть широкий набор интегрированных модулей |
| Сквозной MVP | 60–65% | Есть путь от данных до UI, с оговорками ниже |
| Полная исходная концепция | около 47% (диапазон 45–50%) | Субъективная доля решённой задачи, не метрика CI |
| Научно валидированное прогнозирование | 20–25% | Вероятности ещё не доказывают predictive power |
| Production readiness | 35–40% | Требуются изоляция, безопасность и release discipline |
| Массовый рынок 100k–1M MAU | 20–25% | Требуются tenancy, квоты, стоимость и нагрузочные испытания |

### Проверенные ограничения ревизии

- `backend/app/scenario_engine.py` содержит пустой `generate()`, а публичный маршрут в `main.py` вызывает отсутствующий `run()`. Маршрут counterfactual считать нерабочим.
- `backend/app/stage5_service.py` содержит заглушку `run()`, а маршруты запрашивают `summary()` и `graph.export()`. Knowledge Graph через этот сервис не завершён.
- `backend/app/engines.py` возвращает пустые `Result({})` для economic, social, conflict и energy. Другие модули моделируют отдельные эффекты, но полноценные доменные модели этим не заменены.
- `/api/world/state` и `/api/events` используют отдельный `WorldRuntime` с четырьмя заранее заданными акторами; симуляция хранится в БД. Это две расходящиеся модели мира.
- `run_simulation()` вызывает `sync_world_state_to_db()` в snapshot phase. Она меняет общие `ActorModel` и отношения также при обычной пользовательской симуляции. Изоляция пользовательских ветвей — первый приоритет.
- Forecasting, стратегические коэффициенты и IR lenses пока эвристические. Нужны историческая проверка, калибровка и сравнение с простыми моделями.
- Предыдущий аудит сообщал о рассинхронизации production API и worker относительно `main` на десятки коммитов. Перед исправлением нужно заново запросить release SHA каждого процесса; не трактовать старые цифры 37/57 как текущее состояние.

**Следующий этап: Stage 8 — Core Integrity & Production Architecture v2.** Не расширять существенно публичный набор функций до восстановления инвариантов состояния, изоляции и воспроизводимости. При этом разрешён компактный и честно обозначенный учебный механизм во frontend; он не должен писать в canonical state. Затем Stage 9 — World Model Depth, Stage 10 — Forecast Science, Stage 11 — Mass Scale.

## Обязательные инварианты архитектуры

1. **Общий мир и ветви.** Тяжёлое обновление глобального мира выполняется централизованно. У каждого пользовательского сценария отдельная `SimulationBranch` с `simulation_id`, `parent_state_hash`, `base_tick`, `base_world_version`, `mode`, `seed`, `model_versions` и `created_at`. Базовый снимок плюс copy-on-write изменения; пользовательская ветвь никогда не мутирует `ActorModel` или живой мир. Только авторизованный live orchestrator продвигает canonical state. `/api/world/state` читает этот источник истины.
2. **Повторяемость.** Одинаковые evidence, data cutoff, версии данных/онтологии/моделей, исходный hash и seed дают одинаковый hash результата. Хранить фактически применённый seed, не фиктивный default. `RunManifest`: commit SHA, исходный и родительский hashes, версии данных/онтологии/моделей, seed, cutoff, время. При недетерминированном внешнем вызове фиксировать его ответ или результат нормализации.
3. **Событие не равно публикации.** Цепочка: Source → RawEvidence → normalization → entity linking → clustering → corroboration → classification → Event Store → state effect. У события: ID, тип и версия онтологии, акторы, география, время события и сообщения, confidence, статус `FACT`/`CLAIM`/`HYPOTHESIS`, source IDs, число независимых источников, quality, novelty, significance, ссылки на исходные свидетельства. Уровни значимости: `NOISE`, `TACTICAL`, `STRATEGIC`, `STRUCTURAL`; дорогой расчёт запускать выборочно.
4. **Происхождение эффекта.** Для изменения показателя сохранять трассу поле ← effect ← event ← evidence ← source. Агрегация не должна обрывать трассу. UI показывает свежесть, uncertainty, confidence, provenance, версию модели и горизонт; вероятность не оформлять как факт.
5. **Изолированные вычисления.** Доменные движки получают typed state/events/relationships/tick context/model version и возвращают `Effects[]`; в БД пишет orchestrator. LLM помогает извлекать и связывать события, классифицировать, предлагать гипотезы и объяснять; его выходы проходят schema validation, получают confidence/provenance и не меняют World State напрямую.

## Stage 8: работы по приоритетам и критерии приёмки

| Приоритет | Изменение | Минимальная проверка |
| --- | --- | --- |
| P0-A | Один DB-backed canonical World State; `WorldRuntime` сделать read-only adapter или удалить | Состояние API совпадает с версией live-world в БД после тика |
| P0-B | Изолировать обычный run, game и counterfactual через ветви и copy-on-write | Любой пользовательский запуск сохраняет hash и строки canonical state |
| P0-C | Реализовать `ScenarioEngine`: baseline, assumptions, horizon, seed, branch, сравнение, uncertainty, drivers, hash/cache | API и integration tests действительно возвращают ветви; baseline не мутирует |
| P0-D | Реализовать temporal Knowledge Graph вместо `Stage5Service` stub | Node/edge API и integration tests отражают сохранённые связи |
| P0-E | Реальные economic/trade/energy/social/conflict effects | Доменный вход даёт ограниченный typed effect; engine не пишет в БД |
| P0-F | RunManifest, действительный seed, версии и hashes | Replay одинакового ввода совпадает, цепочка parent hashes валидна |
| P0-G | Idempotent, конкурентно безопасный ingestion и durable event publication | Повтор evidence/event не меняет state дважды, failover продолжает очередь |
| P0-H | Проверять release SHA API, worker и migration job | Все роли показывают один проверенный SHA и revision |
| P0-I | Auth, права и rate limit для mutation endpoints | Анонимный пользователь не может менять мир или инициировать дорогой run |

Temporal graph v1: nodes `Actor`, `Country`, `Organization`, `Event`, `Crisis`, `Commodity`, `Market`, `Sector`, `Infrastructure`, `Location`; edges diplomatic, military, trade, energy, financial, alliance, hostility, dependency, participation, causes, affects, located_in. Edge содержит тип, вес, confidence, valid_from/to, provenance и model version.

Доменные ограничения: торговые доли и ресурсы не выходят за реальные пределы, энергоснабжение учитывает мощности, население и экономические показатели изменяются с реалистичными ограничениями скорости. Для доступных физических величин использовать явные единицы, а не только индексы 0–1.

## Данные, исполнение и причинная модель

- **Ingestion:** retry с exponential backoff, timeouts, circuit breaker, dead-letter queue, source health, idempotency keys и distributed locks. Claim задач в очереди должен быть concurrency safe; одного локального lock недостаточно.
- **Durable bus:** state-changing event сначала транзакционно фиксируется в PostgreSQL outbox, потом передаётся через durable stream (на ранней стадии допустим Redis Streams). Redis Pub/Sub сохраняется для доставки UI, но не служит журналом изменений.
- **Phases:** `SimulationOrchestrator` вызывает typed Ingest, StateUpdate, Perception, Decision, Interaction, Action, Cascade, Forecast и Snapshot phases. Разбивать разросшийся `simulation.py` по мере изменения соответствующих функций. Каждая phase имеет тесты и телеметрию.
- **Cascade v2:** типизированное причинное ребро хранит механизм, коэффициент, лаг, confidence, нелинейность, порог и версию модели. Примеры: oil supply → price → inflation → domestic pressure; trade disruption → output. Не распространять одинаковую delta по всем отношениям механически.
- **Actors:** states, ministries, central banks, military and international organizations, corporations and non-state actors; capabilities, constraints, preferences, beliefs, information quality, memory, risk tolerance, strategy, resources. IR theories держать как конкурирующие explanatory lenses, а не «единую истину». Deterrence, bargaining, signaling, security dilemma, repeated games, coalitions, commitment и brinkmanship версионировать и проверять на канонических случаях.
- **Temporal storage:** `valid_from`, `valid_to`, `observed_at`, `recorded_at`; PostgreSQL для транзакций, Redis для locks/cache/realtime, object storage для evidence и больших snapshots. Долгая история — checkpoints плюс deltas/events в cold storage; compaction не удаляет audit trail.

## Прогнозы и научная проверка

Forecast отделён от simulation и содержит ID, issued_at, data_cutoff, target, horizon, distribution, interval, drivers, model version, world hash, due_at и evaluation status. Минимум горизонты 1/7/30 тиков с последующим переходом к явному календарному времени. Сценарии baseline, alternative, stress, counterfactual хранят weight, triggers, trajectory, uncertainty и объяснение; не обещают наступление события.

Historical Replay Framework даёт модели только информацию, известную на дату T, и проверяет будущее без leakage. Для каждого домена и горизонта сравнивать Brier Score, Log Loss, calibration error, precision/recall и покрытие интервалов по моделям, странам и регионам. Baselines: base rate, persistence, simple trend, naive calibrated/random. Champion/challenger выбирается по историческим результатам; сложная модель без улучшения baseline не получает статуса подтверждённого улучшения. Нужны наборы исторических кризисов и заранее объявленные правила оценки.

## Эксплуатация и масштаб

- **API и безопасность:** типизированные Pydantic request/response и `/api/v1` для новых production интерфейсов; версии при несовместимых изменениях. Authentication, authorization, workspaces, роли и API keys; квоты и rate limits на run, sync-now, сценарии, AI и WebSocket. Request size/connection limits, secrets manager, dependency/SAST/container scanning и audit logs без токенов.
- **Realtime:** compact deltas, sequence, simulation ID, tick, event type и state hash; resume/reconnect и bounded queues. Coalesce старые низкоприоритетные сообщения, если клиент отстаёт.
- **Observability:** latency источников и БД/Redis, failures, throughput, dedup ratio, tick latency, queue depth, количество/оценка прогнозов, WebSocket clients, AI calls/cost, cache hit rate. Correlation ID связывает fetch → normalization → persist → tick → effect → forecast → socket. Нет silent `except Exception: pass`; ошибки отражаются в логах, метриках и degraded health.
- **Database:** внешние ключи, уникальные ограничения для idempotent writes и индексы по реальным запросам. Миграции тестировать fresh → head и previous production → head с rolling compatibility.
- **CI/release:** compile, ruff, type checking, unit/integration tests, Postgres migration, frontend typecheck/build, Docker build, API/WebSocket smoke. `npm ci` при lockfile. Deploy только прошедшего checks commit; API, worker, migrations из одного release SHA; `/api/version` возвращает SHA и версии схемы/моделей/онтологии/frontend.
- **Нагрузка и стоимость:** repeatable нагрузочные тесты чтения, runs, predictions, sockets и ingestion. Shared global low-resolution simulation; high-resolution и Monte Carlo только для hotspots. `ScenarioHash` включает world hash, assumptions, horizon, model versions и seed policy; identical requests используют общий cache. AI Router выбирает модель по задаче и стоимости, отправляет только нужный контекст, отслеживает cost per tick/scenario/user/request и budget guards. Горизонтальное масштабирование после измерений.
- **Объяснение:** для крупного прогноза показывать событие, причину изменения состояния, свидетельства, модели и assumptions, а также возможные опровергающие данные.

## Definition of Done для Codex

Реальная логика; unit tests и integration tests для связей между модулями; зелёные обязательные CI checks; детерминизм и изоляция live state; observable errors; обновлённая документация; bounded state и проверенная стоимость/производительность. Нельзя выдавать `pass`, пустой результат, случайные фиктивные данные или placeholder за готовый production маршрут. Эксперименты помечаются и закрываются feature flag.

**Регрессионные инварианты:** одинаковый state/seed → одинаковый hash; branch не меняет live world или baseline; дубликат evidence/event применён однажды; leader election и failover не дублируют тики; parent hash chain валидна; WebSocket tick summaries упорядочены.

## Frontend в промежуточной версии

Пока Stage 8 не завершён, frontend может показывать **учебный механизм** с условной экономикой, давлением и стабильностью. При выборе события он должен сразу показывать предварительный расчёт, а после применения — результат и причинное объяснение. Такой механизм должен работать без API, не сохранять состояние в canonical world и явно обозначаться как демонстрация, а не прогноз. После P0-A/B/C его можно связать с настоящей изолированной ветвью. Этот раздел задаёт требование к будущему интерфейсу, а не объявляет его реализованным.
