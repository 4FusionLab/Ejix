# Проверки

[English](VALIDATION.md) · **Русский**

Автоматические проверки охватывают настройки, управление геометрическими операциями, границы Fusion API, состав пакетов, ссылки документации и метаданные релиза. CI выполняет их на Linux, macOS и Windows; Autodesk Fusion в CI не запускается.

```sh
python -m unittest discover -s tests -v
python -m compileall -q Ejix scripts tests
python scripts/check_project.py
python scripts/build.py --kind addin --channel release
```

Нативные проверки Fusion включают геометрию, предпросмотр, создание и редактирование Eject Feature, пересчёт и повторное открытие F3D. Проверки на macOS охватывают отдельные и объединённые области, разделение исходного тела и результаты в телах и компонентах. Нативная приёмка Fusion на Windows не завершена.

Проверка стабильного выпуска использует `release/acceptance.json`, чтобы связать результаты проверки платформ и API с контрольной суммой исходного runtime. Autodesk относит Custom Feature API к Preview; вопрос его распространения должен быть решён для прохождения этой проверки.
