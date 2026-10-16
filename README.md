# lokio-apps

Публичный сайт для линейки утилит: страницы приложений и политики
конфиденциальности. Нужен публичным, потому что GitHub Pages на
бесплатном плане работают только в публичных репозиториях. Код самих
приложений живёт в отдельных приватных репозиториях.

Структура:

    index.html        общий список
    style.css         один стиль на всё
    heic/index.html   приложение
    heic/privacy.html политика, EN + RU
    isoba/data.json   данные приложения Isoba, раз в день (.github/workflows/isoba-data.yml,
                      движок — isoba/engine/)

Pages: Settings → Pages → Deploy from a branch → main → / (root).
