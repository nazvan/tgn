# Парсер и модератор телеграм-новостей

Эта программа состоит из двух компонентов:
1. Парсер новостей из телеграм-каналов с использованием Telethon
2. Бот для рецензирования и публикации новостей в целевой канал

## Требования

* Python 3.7+
* Доступ к Telegram API (API ID и API Hash)
* Токен бота Telegram
* Бот должен быть добавлен администратором в целевой канал для публикации

## Установка

1. Клонируйте репозиторий:
```
git clone <url-репозитория>
cd <директория-проекта>
```

2. Установите зависимости:
```
pip install -r requirements.txt
```

3. Создайте файл `.env` на основе шаблона `.env.example`:
```
cp .env.example .env
```

4. Отредактируйте файл `.env`, указав ваши данные:
   - API_ID и API_HASH (получите от https://my.telegram.org/)
   - PHONE_NUMBER (ваш номер телефона)
   - BOT_TOKEN (получите от @BotFather)
   - TARGET_CHANNEL (имя целевого канала для публикации)
   - MODERATOR_IDS (ID пользователей через запятую)
   - SOURCE_CHANNELS (имена каналов для парсинга через запятую)

5. Добавьте вашего бота в целевой канал как администратора (с правами публикации сообщений).

## Аутентификация и использование

1. При первом запуске программы вам потребуется пройти аутентификацию в Telegram для парсера:
```
python main.py
```

2. Вам будет отправлен код авторизации на указанный номер телефона. Введите его в терминале.

3. Если у вас включена двухфакторная аутентификация, вам также потребуется ввести пароль.

4. После успешной аутентификации программа автоматически запустит парсер и бота.

5. Отправьте команду `/start` боту, чтобы начать работу с ним.

## Функции бота

Бот предоставляет следующие команды:

* `/start` - Начало работы с ботом
* `/help` - Показать справку по использованию бота
* `/stats` - Показать статистику модерации

### Мгновенная модерация

При появлении новой новости в отслеживаемых каналах:
1. Бот автоматически отправит ее всем модераторам
2. Модераторы увидят новость с тремя кнопками: "Одобрить и опубликовать", "Редактировать" и "Отклонить"
3. При нажатии на кнопку "Редактировать", бот запросит новый текст для новости
4. После ввода нового текста, бот отправит обновленную новость для повторной модерации
5. При нажатии на кнопку "Одобрить", новость будет опубликована в целевой канал, а кнопка изменится на "Опубликовано"
6. При нажатии на кнопку "Отклонить", новость будет помечена как отклоненная
7. После публикации появится кнопка "Удалить", позволяющая быстро удалить опубликованную новость из канала

## Структура проекта

* `.env` - Файл с конфиденциальными настройками (не включен в репозиторий)
* `.env.example` - Шаблон для создания файла .env
* `config.py` - Конфигурационный файл, загружающий настройки из .env
* `database.py` - Модели базы данных (SQLAlchemy)
* `parser.py` - Парсер новостей из телеграм-каналов
* `bot.py` - Бот для модерации и публикации новостей
* `main.py` - Основной файл для запуска приложения

## Функциональность

### Парсер новостей
* Мониторит указанные каналы
* Сохраняет новые сообщения в базу данных
* Скачивает и сохраняет медиафайлы
* Немедленно отправляет новые новости модераторам через бота

### Бот для модерации
* Мгновенно уведомляет модераторов о новых новостях
* Отправляет новости на рецензию модераторам с кнопками для принятия решения
* Позволяет редактировать текст новостей перед публикацией
* Позволяет одобрять или отклонять новости одним нажатием
* После публикации предоставляет возможность удалить новость из канала
* Автоматически публикует одобренные новости в целевой канал
* Предоставляет статистику по модерации

## Примечание

- Для работы программы требуется создать директорию `media` в корне проекта (она создается автоматически при первом запуске).
- Процесс аутентификации в Telegram требуется только при первом запуске или после удаления файла сессии (`parser_session.session`).
- Бот должен быть добавлен в целевой канал как администратор с правами публикации сообщений.
- Для целевого канала можно указать как username (например, "channel_name" или "@channel_name"), так и ID канала (например, "-1001234567890").
- Файл `.env` содержит конфиденциальные данные и не должен добавляться в систему контроля версий. 