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
    isoba/data.json   данные приложения Isoba (+ history.json), раз в день; коммитит workflow `data`
                      закрытого репо isoba ключом развёртывания «isoba-data». Код движка здесь не лежит.

Pages: Settings → Pages → Deploy from a branch → main → / (root).
