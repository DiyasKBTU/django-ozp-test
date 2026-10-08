# Инструкция: pbbtest.oaiu.kz (установка, обновление, эксплуатация)

Полное руководство на русском для нашего сервера. Короткая казахская версия для чистого VPS — [DEPLOY.md](DEPLOY.md).

| Что | Значение |
| --- | --- |
| Сайт | https://pbbtest.oaiu.kz |
| Сервер | `185.129.48.252` — **тот же, где уже работают `oaiu.kz` и `ai.oaiu.kz`** |
| DNS | A-запись `pbbtest.oaiu.kz → 185.129.48.252` уже есть ✅ |
| Репозиторий | https://github.com/DiyasKBTU/django-ozp-test (публичный) |
| Папка проекта / системный пользователь | `/srv/ozp-test` / `ozp` |
| База PostgreSQL / её пользователь | `ozp_test` / `ozp` |
| Сервис systemd (Gunicorn) | `ozp-test`, слушает `127.0.0.1:8001` |
| Бэкапы | `/var/backups/ozp-test` (14 дней) |

Схема: браузер → **Nginx** (HTTPS, статика, картинки) → **Gunicorn** (Django) → **PostgreSQL**.

> **Главное правило для этого сервера:** на нём уже живут другие сайты. Ничего чужого не удаляем и не перезапускаем: **не** удаляйте `/etc/nginx/sites-enabled/default` и другие конфиги, **не** меняйте часовой пояс сервера, **не** включайте `ufw`, если он сейчас выключен (можно потерять SSH). Все команды ниже добавляют только своё.

Проверено заранее на чистых Ubuntu 24.04 и Debian 12 (2 ядра / 2 ГБ): установка по этой инструкции, 308 автотестов (Python 3.11–3.13), сквозной сценарий админ → преподаватель → студент, нагрузка 300 студентов (16 800 запросов, 0 ошибок), бэкап → восстановление, перезагрузка.

---

## Содержание

1. [Первая установка](#1-первая-установка)
2. [Подготовка и проведение реального теста](#2-подготовка-и-проведение-реального-теста)
3. [Нагрузочный тест перед первым экзаменом](#3-нагрузочный-тест-перед-первым-экзаменом)
4. [Обновление кода](#4-обновление-кода)
5. [Откат на прошлую версию](#5-откат-на-прошлую-версию)
6. [Бэкапы: проверить, скачать, восстановить](#6-бэкапы-проверить-скачать-восстановить)
7. [Новый предмет или изменение тем](#7-новый-предмет-или-изменение-тем)
8. [Пароли и пользователи](#8-пароли-и-пользователи)
9. [Если что-то сломалось](#9-если-что-то-сломалось)
10. [Шпаргалка команд](#10-шпаргалка-команд)
11. [Локальная копия на компьютере](#11-локальная-копия-на-компьютере)

---

## 1. Первая установка

Подключитесь к серверу пользователем с `sudo`: `ssh ВАШ_ПОЛЬЗОВАТЕЛЬ@185.129.48.252`.

### 1.1. Осмотр сервера (ничего не меняет)

```bash
head -2 /etc/os-release              # Debian 12 / Ubuntu 22.04+ — подходят
python3 --version                    # нужен 3.11 или новее
nginx -v
psql --version 2>/dev/null || echo "PostgreSQL не установлен"
ls /etc/nginx/sites-enabled/         # чужие сайты — не трогаем
sudo ss -ltnp | grep -E ':8001 |:5432 ' || echo "порт 8001 свободен"
free -h; nproc; df -h /
timedatectl | grep "Time zone"       # запомните: UTC или Asia/Almaty (нужно для cron)
sudo ufw status                      # если inactive — так и оставляем
```

Если порт `8001` уже занят, выберите свободный (например, `8011`) и замените `8001` в двух файлах на шаге 1.6: `/etc/systemd/system/ozp-test.service` и `/etc/nginx/sites-available/ozp-test`.

### 1.2. Пакеты

Ставятся только недостающие; уже установленные (nginx, postgresql) не ломаются. Полный `apt upgrade` на общем сервере не делаем — это решает администратор сервера.

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-dev git postgresql nginx gettext certbot python3-certbot-nginx
```

### 1.3. База данных

Пароль генерируем из букв и цифр (символы `@ : / #` ломают строку `DATABASE_URL`):

```bash
DB_PASS=$(openssl rand -hex 24); echo "$DB_PASS"     # СОХРАНИТЕ — понадобится в .env
sudo -u postgres psql -c "CREATE USER ozp WITH PASSWORD '$DB_PASS';"
sudo -u postgres psql -c "CREATE DATABASE ozp_test OWNER ozp ENCODING 'UTF8';"
```

Другие базы на сервере это не затрагивает.

### 1.4. Код и виртуальное окружение

```bash
sudo adduser --system --group --no-create-home --home /srv/ozp-test ozp
sudo mkdir /srv/ozp-test
sudo chown ozp:ozp /srv/ozp-test
sudo -u ozp git clone https://github.com/DiyasKBTU/django-ozp-test.git /srv/ozp-test
cd /srv/ozp-test
sudo -u ozp python3 -m venv .venv
sudo -u ozp .venv/bin/pip install --no-cache-dir -r requirements.txt
```

### 1.5. Файл `.env` (секреты)

```bash
cd /srv/ozp-test
sudo -u ozp .venv/bin/python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
sudo -u ozp cp .env.example .env
sudo -u ozp nano .env
sudo chmod 600 .env
```

Содержимое (подставьте ключ из первой команды и пароль из 1.3):

```ini
SECRET_KEY=СГЕНЕРИРОВАННЫЙ_КЛЮЧ
DEBUG=False
ALLOWED_HOSTS=pbbtest.oaiu.kz
DATABASE_URL=postgres://ozp:ПАРОЛЬ_ИЗ_1.3@localhost:5432/ozp_test
CSRF_TRUSTED_ORIGINS=https://pbbtest.oaiu.kz
SECURE_HSTS_SECONDS=0
```

`.env` не попадает в git. Никому не пересылайте его и не коммитьте.

### 1.6. Таблицы, статика, предметы, администратор

```bash
cd /srv/ozp-test
sudo -u ozp .venv/bin/python manage.py migrate                      # создаёт таблицы
sudo -u ozp .venv/bin/python manage.py collectstatic --noinput      # CSS/JS для Nginx
sudo -u ozp .venv/bin/python manage.py compilemessages --ignore=.venv
sudo -u ozp .venv/bin/python manage.py load_subjects                # 4 предмета, темы, подтемы
sudo -u ozp .venv/bin/python manage.py createsuperuser              # ваш логин администратора
sudo -u ozp mkdir -p media                                          # загружаемые картинки
```

**`load_demo` на сервере не запускаем** — это демо-вопросы для разработки.

### 1.7. Gunicorn (служба сайта)

```bash
cd /srv/ozp-test
sudo cp deploy/gunicorn.service /etc/systemd/system/ozp-test.service
sudo systemctl daemon-reload
sudo systemctl enable --now ozp-test
sudo systemctl status ozp-test --no-pager     # active (running)
curl -sI -H "Host: pbbtest.oaiu.kz" http://127.0.0.1:8001/ | head -1   # 301 — это нормально (Django просит HTTPS)
```

3 воркера ≈ 70 МБ памяти каждый. На тестах 3 воркера на 2 ядрах выдержали 300 одновременных студентов.

### 1.8. Nginx — добавляем свой сайт, чужие не трогаем

```bash
cd /srv/ozp-test
sudo cp deploy/nginx.conf /etc/nginx/sites-available/ozp-test
sudo ln -s /etc/nginx/sites-available/ozp-test /etc/nginx/sites-enabled/
sudo chmod 755 /srv/ozp-test                 # Nginx должен читать staticfiles и media
sudo nginx -t && sudo systemctl reload nginx # reload, не restart: другие сайты не прерываются
```

Если `nginx -t` пишет ошибку — **не делайте reload**, удалите ссылку `sudo rm /etc/nginx/sites-enabled/ozp-test` и разберитесь (раздел 9).

### 1.9. HTTPS (Let's Encrypt)

```bash
sudo certbot --nginx -d pbbtest.oaiu.kz     # email, согласие с условиями; certbot меняет только наш server-блок
sudo certbot renew --dry-run                # продление работает
systemctl list-timers | grep certbot        # таймер автопродления есть
```

Откройте https://pbbtest.oaiu.kz — должна открыться главная страница с замком. Затем включите HSTS:

```bash
cd /srv/ozp-test
sudo -u ozp sed -i 's/^SECURE_HSTS_SECONDS=0/SECURE_HSTS_SECONDS=31536000/' .env
sudo systemctl restart ozp-test
sudo -u ozp .venv/bin/python manage.py check --deploy
```

`check --deploy` покажет 2 предупреждения — `W005` (поддомены) и `W021` (preload). **Это правильно, не включайте их:** иначе HSTS распространится на все поддомены `oaiu.kz`.

### 1.10. Бэкап и регулярные задачи

```bash
cd /srv/ozp-test
sudo cp deploy/backup.sh /usr/local/bin/ozp-backup.sh
sudo chmod +x /usr/local/bin/ozp-backup.sh
sudo /usr/local/bin/ozp-backup.sh            # проверка: «бэкап дайын: …»
sudo crontab -e
```

Строка для root (время — по часовому поясу **сервера**, см. 1.1):

```cron
# Бэкап в 03:30 по Алматы. Сервер в UTC → 22:30 UTC; сервер в Asia/Almaty → замените на «30 3 * * *»
30 22 * * * /usr/local/bin/ozp-backup.sh >> /var/log/ozp-backup.log 2>&1
```

Завершение просроченных тестов каждые 5 минут (`sudo crontab -u ozp -e`):

```cron
*/5 * * * * cd /srv/ozp-test && .venv/bin/python manage.py finish_expired > /dev/null
```

### 1.11. Финальная проверка

```bash
curl -sI http://pbbtest.oaiu.kz/ | head -1                                  # 301 (на https)
curl -sI https://pbbtest.oaiu.kz/ | grep -iE "^HTTP|strict-transport"       # 200 + HSTS
curl -sI https://pbbtest.oaiu.kz/static/js/timer.js | head -1               # 200 (статика)
curl -sI https://oaiu.kz/ | head -1; curl -sI https://ai.oaiu.kz/ | head -1 # соседние сайты живы
sudo systemctl is-active ozp-test nginx postgresql cron
```

В браузере:

- [ ] Вход в https://pbbtest.oaiu.kz/admin/ вашим логином.
- [ ] Переключатель KK / RU меняет язык.
- [ ] Преподаватель загружает вопрос с картинкой — картинка видна (`/media/`).
- [ ] В вопросе по математике `\(\frac{1}{2}\)` показывается формулой.
- [ ] На следующий день в `/var/backups/ozp-test` появился новый `db-*.sql.gz`.

---

## 2. Подготовка и проведение реального теста

**1. Преподаватели** (делает администратор): https://pbbtest.oaiu.kz/admin/ → «Пайдаланушылар» → «Қосу» → логин, пароль, имя → галочка **«Қызметкер мәртебесі»** (is_staff) → в блоке «Профиль» выбрать **предметы** преподавателя → «Сақтау». Регистрация на сайте — только для студентов.

**2. Группы**: админка → раздел «Қолданушылар мен топтар» → «Топтар» → «Қосу» (не путать с системными «Groups»): название (например `МАТ-21`), предмет, **язык обучения** (kk / ru). Язык группы = язык теста её студентов, студент его не выбирает.

**3. Банк вопросов** (преподаватель, https://pbbtest.oaiu.kz/teacher/questions/):

- один вариант теста = **50 вопросов**: 20 подтем × 2 одиночных вопроса + 2 контекста × 5 вопросов; уровни A / B / C = 13 / 30 / 7;
- минимум банка **для каждого языка отдельно**: 6 вопросов на каждую подтему и 4 контекста (по 5 вопросов);
- у вопроса 4 варианта, один правильный; вариант — текст и/или картинка (jpg/png/webp до 2 МБ);
- формулы (математика): `\( ... \)` в строке, `\[ ... \]` отдельной строкой;
- заполненность: `/teacher/bank/`, пример собранного варианта: `/teacher/bank/sample/?lang=kk` (или `ru`). Пока банк неполный, тест по предмету не начнётся.

**4. Сессия** (админка → раздел «Тест» → «Тест сессиялары» → «Қосу»): название, предмет, время открытия и закрытия (**по Алматы**), группы, когда показывать ответы («сразу после теста» или «после закрытия сессии»), «белсенді». Длительность берётся из предмета: информатика и математика — 125 минут, художественный труд — 80.

**5. Студенты** регистрируются заранее: https://pbbtest.oaiu.kz/accounts/register/ — имя, фамилия, **группа**, логин, пароль. Вход в систему медленный по задумке (защита паролей, ~0,5 с), поэтому 1000 человек, входящих в одну минуту, выстроятся в очередь. Пусть входят за 10–15 минут до открытия.

**6. Во время теста** можно смотреть журнал: `sudo journalctl -u ozp-test -f`. Таймер и сроки проверяет сервер. Выйти из аккаунта во время теста нельзя. Если студент закрыл вкладку, тест завершится сам по истечении времени.

**7. Результаты**: `/teacher/results/` (фильтр по сессии и группе) и выгрузка CSV.

---

## 3. Нагрузочный тест перед первым экзаменом

Рекомендуется один раз перед первым массовым тестом. Делайте **ночью**: нагрузка ложится на весь сервер, включая соседние сайты. Банк предмета должен быть полным.

**На сервере** — тестовые аккаунты и закрытая от реальных студентов сессия:

```bash
cd /srv/ozp-test
sudo -u ozp .venv/bin/python manage.py loadtest_data --count 300 --subject mathematics
# → LOADTEST_SESSION_ID=… LOADTEST_ACCOUNTS=300
```

**На своём компьютере** (PowerShell, в папке проекта):

```powershell
python -m venv .venv-loadtest
.venv-loadtest\Scripts\python -m pip install -r loadtest/requirements.txt
$env:LOADTEST_SESSION_ID = "ID_ИЗ_ВЫВОДА"
$env:LOADTEST_ACCOUNTS = "300"
.venv-loadtest\Scripts\locust -f loadtest/locustfile.py --host https://pbbtest.oaiu.kz --headless -u 300 -r 5 --run-time 30m --html loadtest-report.html
```

Смотрите на `# fails`: должно быть 0. Отчёт сохранится в `loadtest-report.html`.

**Обязательно удалите тестовые аккаунты** — их пароль опубликован в README:

```bash
sudo -u ozp .venv/bin/python manage.py loadtest_data --delete
```

---

## 4. Обновление кода

**На компьютере**: изменили код → `.venv\Scripts\python manage.py test` → коммит → `git push origin main`.

**На сервере** (лучше вне времени тестов):

```bash
sudo /usr/local/bin/ozp-backup.sh            # бэкап перед обновлением
cd /srv/ozp-test
sudo -u ozp git pull
sudo -u ozp .venv/bin/pip install --no-cache-dir -r requirements.txt
sudo -u ozp .venv/bin/python manage.py migrate
sudo -u ozp .venv/bin/python manage.py collectstatic --noinput
sudo -u ozp .venv/bin/python manage.py compilemessages --ignore=.venv
sudo systemctl restart ozp-test
sudo systemctl is-active ozp-test && curl -sI https://pbbtest.oaiu.kz/ | head -1
```

Если менялся `apps/quiz/data/subjects.json` — ещё `sudo -u ozp .venv/bin/python manage.py load_subjects`. Если менялись `deploy/nginx.conf` или `deploy/gunicorn.service`, скопируйте их заново (шаги 1.7–1.8). **Внимание:** certbot дописал HTTPS в установленный nginx-конфиг, поэтому после копирования nginx-конфига снова выполните `sudo certbot --nginx -d pbbtest.oaiu.kz` (на вопрос certbot выберите «Attempt to reinstall this existing certificate»).

---

## 5. Откат на прошлую версию

```bash
cd /srv/ozp-test
sudo -u ozp git log --oneline -10            # найти рабочий коммит или тег (v2.0.0 …)
sudo -u ozp git checkout КОММИТ_ИЛИ_ТЕГ
sudo systemctl restart ozp-test
```

Если в неудачном обновлении были новые миграции, база уже изменена — восстановите бэкап, сделанный перед обновлением (раздел 6). Вернуться на свежую версию: `sudo -u ozp git checkout main && sudo -u ozp git pull`.

---

## 6. Бэкапы: проверить, скачать, восстановить

**Проверить:** `sudo ls -lh /var/backups/ozp-test/` и `sudo tail /var/log/ozp-backup.log`. Бэкап = `db-ДАТА.sql.gz` (база) + `media-ДАТА.tar.gz` (картинки). Хранятся 14 дней. Дата в имени — по часам сервера.

**Скачать к себе** (копия вне сервера — на случай поломки диска):

```bash
# на сервере: копия, доступная вашему пользователю
sudo cp /var/backups/ozp-test/db-2026-10-15.sql.gz /var/backups/ozp-test/media-2026-10-15.tar.gz ~/ && sudo chown $USER ~/*-2026-10-15.*
```

```powershell
# на компьютере
scp ВАШ_ПОЛЬЗОВАТЕЛЬ@185.129.48.252:~/db-2026-10-15.sql.gz .
scp ВАШ_ПОЛЬЗОВАТЕЛЬ@185.129.48.252:~/media-2026-10-15.tar.gz .
```

Потом удалите копии из домашней папки на сервере: `rm ~/*-2026-10-15.*`.

**Восстановить** (сайт будет недоступен 1–2 минуты; дату подставьте свою; пароль БД — в `.env`: `sudo grep DATABASE_URL /srv/ozp-test/.env`):

```bash
sudo systemctl stop ozp-test
sudo -u postgres psql -c "DROP DATABASE ozp_test;"
sudo -u postgres psql -c "CREATE DATABASE ozp_test OWNER ozp ENCODING 'UTF8';"
gunzip -c /var/backups/ozp-test/db-2026-10-15.sql.gz \
    | psql "postgres://ozp:ПАРОЛЬ_БД@localhost:5432/ozp_test"
sudo rm -rf /srv/ozp-test/media
sudo tar -xzf /var/backups/ozp-test/media-2026-10-15.tar.gz -C /srv/ozp-test
sudo chown -R ozp:ozp /srv/ozp-test/media
sudo systemctl start ozp-test
```

Порядок проверен: после восстановления количество пользователей, вопросов, попыток и ответов совпало 1:1.

---

## 7. Новый предмет или изменение тем

Код менять не нужно. Предметы, темы и подтемы лежат в `apps/quiz/data/subjects.json`: ровно 20 подтем с номерами 1–20 и непустыми названиями. Длительность (`duration_minutes`) и формулы (`uses_formulas`) задаются там же.

1. Изменить `subjects.json` на компьютере, проверить локально: `.venv\Scripts\python manage.py load_subjects --only КОД_ПРЕДМЕТА`.
2. Коммит → `git push origin main`.
3. На сервере — обновление (раздел 4), затем `sudo -u ozp .venv/bin/python manage.py load_subjects`.

Команду можно запускать повторно — записи обновляются. При ошибке в файле она ничего не записывает.

---

## 8. Пароли и пользователи

| Задача | Как |
| --- | --- |
| Студент забыл пароль | админка → пользователь → под полем «Пароль» кнопка/ссылка смены пароля → новый пароль |
| Сменить пароль из консоли | `cd /srv/ozp-test && sudo -u ozp .venv/bin/python manage.py changepassword ЛОГИН` |
| Ещё один администратор | `sudo -u ozp .venv/bin/python manage.py createsuperuser` |
| Сделать преподавателем | в пользователе: галочка is_staff + предметы в «Профиль» |
| Сменить пароль БД | `sudo -u postgres psql -c "ALTER USER ozp WITH PASSWORD 'НОВЫЙ';"` → обновить `DATABASE_URL` в `.env` → `sudo systemctl restart ozp-test` |

---

## 9. Если что-то сломалось

Первым делом — журналы:

```bash
sudo journalctl -u ozp-test -n 100 --no-pager    # Django / Gunicorn
sudo tail -n 50 /var/log/nginx/error.log         # Nginx
```

| Симптом | Причина и решение |
| --- | --- |
| **502 Bad Gateway** | Gunicorn не работает: `sudo systemctl status ozp-test`, журнал выше. Обычно ошибка в `.env` (опечатка, нет `SECRET_KEY`) или недоступна база (`sudo systemctl status postgresql`). |
| **400 Bad Request** | Домен не в `ALLOWED_HOSTS` в `.env`. |
| **403 «CSRF verification failed»** | `CSRF_TRUSTED_ORIGINS=https://pbbtest.oaiu.kz` в `.env`. Открывайте сайт по https. |
| Открылся другой сайт / ошибка сертификата `ai.oaiu.kz` | Нет сертификата для pbbtest — выполните шаг 1.9. Проверка: `sudo nginx -T \| grep -n "server_name"`. |
| **ERR_TOO_MANY_REDIRECTS** | В nginx-конфиге потерялась строка `proxy_set_header X-Forwarded-Proto $scheme;`. |
| Страница без стилей | `collectstatic` (раздел 4) и `sudo chmod 755 /srv/ozp-test`. |
| **413** при загрузке картинки | Больше `client_max_body_size 12M` в nginx-конфиге. Картинки — до 2 МБ каждая. |
| Ошибка при загрузке картинки | Права: `sudo chown -R ozp:ozp /srv/ozp-test/media`. |
| «Сізге пән тағайындалмаған» | У преподавателя нет предметов: админка → пользователь → «Профиль» → предметы. |
| Студент не видит сессию | Группа студента не в сессии, предмет сессии ≠ предмету группы, сессия не «белсенді» или ещё не открылась. |
| Тест не начинается: «Банкте … сұрақтар жеткіліксіз» | Неполный банк для языка группы: `/teacher/bank/`. |
| Сертификат истёк | `sudo certbot renew` и `systemctl list-timers \| grep certbot`. |
| `git pull`: «local changes would be overwritten» | Кто-то правил файлы на сервере: `sudo -u ozp git status`, `sudo -u ozp git diff`. Правки переносите в репозиторий, на сервере — `sudo -u ozp git checkout -- ФАЙЛ`. |

---

## 10. Шпаргалка команд

```bash
cd /srv/ozp-test
sudo systemctl restart ozp-test                  # перезапуск сайта (после изменений .env / кода)
sudo systemctl status ozp-test --no-pager        # состояние
sudo journalctl -u ozp-test -f                   # журнал в реальном времени
sudo nginx -t && sudo systemctl reload nginx     # применить изменения nginx
sudo -u ozp .venv/bin/python manage.py shell     # консоль Django
sudo -u ozp .venv/bin/python manage.py finish_expired   # завершить просроченные тесты вручную
sudo /usr/local/bin/ozp-backup.sh                # бэкап сейчас
```

---

## 11. Локальная копия на компьютере

Копия: `D:\Projects\OZP\django-ozp-test`, база — PostgreSQL в Docker-контейнере `ozp-postgres` (данные в томе `ozp-pgdata`), в ней демо-вопросы. Логин локального админа — в `D:\Projects\OZP\local-admin.txt`.

```powershell
docker start ozp-postgres                         # после перезагрузки компьютера
cd D:\Projects\OZP\django-ozp-test
.venv\Scripts\python manage.py runserver          # http://127.0.0.1:8000
.venv\Scripts\python manage.py test               # 308 тестов
git push origin main                              # отправить изменения на GitHub (DiyasKBTU)
```

Старый репозиторий `nureketech/django-ozp-test` подключён как `upstream`, только для чтения: `git fetch upstream`.
