<p align="center">
  <img src="docs/assets/ejix-icon.png" alt="Ejix от 4FusionLab" width="200">
</p>

<h1 align="center">Ejix для Autodesk Fusion</h1>
<p align="center"><strong>Одна команда. Отдельное тело.</strong><br>Извлекайте объём по профилю или плоской грани из одного или нескольких твёрдых тел.</p>

<p align="center">
  <a href="https://github.com/4FusionLab/Ejix/actions/workflows/ci.yml"><img src="https://github.com/4FusionLab/Ejix/actions/workflows/ci.yml/badge.svg" alt="Проверки сборки"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-GPL--3.0-blue" alt="Лицензия GPL-3.0"></a>
</p>

<p align="center"><a href="https://github.com/4FusionLab/Ejix/releases"><strong>Скачать</strong></a> · <a href="README.md">English</a> · <a href="https://github.com/4FusionLab/Ejix/issues/new/choose">Сообщить о проблеме</a></p>

## Извлеките нужную форму

Выберите замкнутые профили эскиза или плоские грани и задайте протяжённость. Ejix найдёт пересекаемые тела, покажет извлекаемый объём и создаст результат как тело или компонент. Можно выбрать, вычитать ли результат из каждого исходного тела.

- **Несколько профилей:** области на одной или разных плоскостях.
- **Separate Bodies:** отдельные результаты в порядке выбора; пересечение остаётся первому профилю.
- **Combine Connected:** пересекающиеся и касающиеся области одного исходного тела объединяются до вычитания. Несвязанные области остаются отдельными.
- **Протяжённость:** Distance, To Object или All; одно направление, два направления или Symmetric.
- **Таймлайн:** редактируемая Eject Feature или группа штатных операций Fusion.

По умолчанию выбраны Eject Feature, New Body, Preview и Subtract from Objects. Тела находятся автоматически; ненужные можно исключить.

## Ejix в Fusion

Золотая подсветка показывает извлекаемые объёмы. На следующих изображениях показаны исходное тело после вычитания и два результата — отдельно для наглядности.

![Превью Ejix: два объёма подсвечены внутри тела](docs/images/eject-preview.png)

![Исходное тело после извлечения двух областей](docs/images/eject-cut.png)

![Два извлечённых тела в исходных положениях](docs/images/eject-parts.png)

## Быстрый старт

1. Скачайте архив дополнения из [Releases](https://github.com/4FusionLab/Ejix/releases) и распакуйте его в постоянную папку.
2. В Fusion откройте **Utilities → Scripts and Add-Ins**, добавьте папку `Ejix` с файлами `Ejix.py` и `Ejix.manifest` и запустите дополнение.
3. В **Design → Solid → Modify** выберите **Eject**. Укажите замкнутые профили или плоские грани.
4. Задайте расстояние или другую протяжённость, проверьте подсветку и список тел, выберите параметры результата.
5. Нажмите **OK** для извлечения. **Cancel** отменяет команду.

[Установка и обновление](docs/INSTALLATION.ru.md) · [Руководство](docs/GUIDE.ru.md)

## Совместимость и ограничения

Ejix работает в рабочей области Design в Autodesk Fusion при включённой **Capture Design History**. Профили и участвующие тела должны принадлежать одному компоненту и экземпляру. To Object поддерживает плоские грани и конструкционные плоскости. Извлечение через разные компоненты, Taper Angle и полное вычитание тела не поддерживаются; полностью охваченное тело пропускается при включённом вычитании.

Eject Feature использует [Custom Feature API](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/CustomFeatures_UM.htm), который Autodesk относит к Preview и не рекомендует использовать в распространяемых производственных программах. Будущие изменения Fusion могут повлиять на такие фичи. Исходные профили, тип результата, способ обработки профилей и вычитание фиксируются при создании. Если изменение протяжённости меняет состав пересечений профилей и тел, пересоздайте фичу. Для повторного открытия моделей с Eject Feature сохраняйте установленную совместимую версию Ejix.

Нативные проверки Fusion на macOS частичные; полная интерактивная приёмка не завершена. Нативная приёмка Fusion на Windows не проводилась. Задание Windows в CI выполняет тесты и сборку без запуска Fusion.

[Все ограничения](docs/GUIDE.ru.md#ограничения) · [Поддержка](SUPPORT.ru.md)

## Документация и поддержка

[Руководство](docs/GUIDE.ru.md) · [Установка](docs/INSTALLATION.ru.md) · [История изменений](CHANGELOG.ru.md) · [Участие в разработке](CONTRIBUTING.ru.md) · [Безопасность](SECURITY.ru.md) · [Правила сообщества](CODE_OF_CONDUCT.ru.md)

## Семейство 4FusionLab

Ejix извлекает объёмы. [Perfora](https://github.com/4FusionLab/Perfora) создаёт перфорации, а [Selectra](https://github.com/4FusionLab/Selectra) помогает находить похожую геометрию.

[GPL-3.0-only](LICENSE). Самостоятельный проект **4FusionLab**, не связанный с Autodesk и не одобренный ею. Autodesk и Fusion — товарные знаки Autodesk, Inc.
