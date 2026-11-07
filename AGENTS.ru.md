# Разработка Ejix

[English](AGENTS.md)

Ejix — Fusion add-in для извлечения объёмов по профилям и граням, с параметрическим Eject Feature.

## Общие правила 4FusionLab

- Общие стандарты: https://github.com/4FusionLab/.github/blob/main/AGENTS.md; модель совместного CI: https://github.com/4FusionLab/.github/blob/main/RELEASE_PLATFORM.md.
- Общайся с пользователем и составляй планы на русском; названия команд, код и пользовательский интерфейс Fusion — на английском. Сохраняй независимые README.md и README.ru.md, если это есть в проекте.
- Перед изменениями изучай текущий код и `git status`; сохраняй несвязанные изменения. Используй Conventional Commits; небольшие PR с тестами предпочтительны, но прямой push в `main` разрешён существующей политикой.
- Не меняй UUID Fusion manifest, IDs команд, поддержку ОС и структуру дистрибутива без отдельной задачи и миграционного плана. Никаких секретов, личных CAD-файлов, токенов или несанкционированных внешних сервисов в репозитории.
- Где есть распространяемый runtime, релиз запускает только push/merge в `main`, затронувший `.github/release-paths.txt`. CI проверяет код, GitVersion.Tool 6.8.2 вычисляет версию, GitHub автоматически создаёт тег и Release. **Никогда не создавай или не передвигай релизные теги вручную** и не перезаписывай опубликованные ZIP.
- README, docs, тесты, настройки CI и `AGENTS.md` сами по себе не должны запускать релиз. Общие Actions подключай по **неизменяемому commit SHA** из `4FusionLab/.github`, не по `@main`.
- Unit-тесты и проверка ZIP — не то же самое, что живые испытания Autodesk Fusion. Для API/UX фиксируй, что действительно тестировалось и на какой ОС.

## Границы продукта и API

- Источник поведения: `README.md`, `README.ru.md`, `docs/GUIDE.md` и `docs/VALIDATION.md`. Проверяй `Ejix/engine.py` как независимое ядро, `Ejix/fusion_adapter.py` и `Ejix/feature.py` — только в контексте Autodesk Fusion.
- Поддерживай существующие Extent/Direction, несколько профилей, вычитание исходных тел, Preview и очистку временных объектов при Cancel. Не оставляй изменения модели до подтверждения пользователя.
- `Custom Feature API` от Autodesk имеет Preview-ограничения; не обещай производственную совместимость без новой нативной проверки. Сохраняй `release/acceptance.json` и `release/limitations.md`; для изменённого runtime без актуальной CAD-приёмки release должен оставаться prerelease.
- Перед изменением Fusion API сверяй официальные определения Autodesk; не выдумывай методы. Объекты Fusion и event handlers живут ограниченное время; обрабатывай отмену и исчезновение объектов.

## Проверка

- `python -m unittest discover -s tests -v`
- `python scripts/check_project.py`
- `python scripts/build.py --kind addin --channel release --version X.Y.Z` (только локальная проверка пакета, без публикации)
- Для интерактивных изменений — отдельный несохранённый CAD-документ, без вмешательства в активную модель пользователя; соблюдай `docs/VALIDATION.md`.
- Сохраняй лицензионные SPDX-заголовки и существующие ограничения по macOS/Windows.
