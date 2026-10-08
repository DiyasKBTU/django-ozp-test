# Инструкция: pbbtest.oaiu.kz (установка, обновление, эксплуатация)

Полное руководство на русском для нашего сервера. Короткая казахская версия для чистого VPS — [DEPLOY.md](DEPLOY.md).

| Что | Значение |
| --- | --- |
| Сайт | https://pbbtest.oaiu.kz |
| Сервер | `cloud-001`: Ubuntu 24.04, 1 ядро, 1 ГБ RAM; **уже работает телеграм-бот** (`127.0.0.1:8001`, сайт nginx `django-telegrambot-university`) |
| DNS | `pbbtest.oaiu.kz` должен указывать на IP `cloud-001` (проверка — шаг 0) |
| Репозиторий | https://github.com/DiyasKBTU/django-ozp-test (публичный) |
| Папка проекта / системный пользователь | `/srv/ozp-test` / `ozp` |
| База PostgreSQL / её пользователь | `ozp_test` / `ozp` |
| Сервис systemd (Gunicorn) | `ozp-test`, 2 воркера, слушает `127.0.0.1:8002` |
| Бэкапы | `/var/backups/ozp-test` (14 дней) |

Схема: браузер → **Nginx** (HTTPS, статика, картинки) → **Gunicorn** (Django) → **PostgreSQL**.

> **Главное правило для этого сервера:** на нём уже работает бот. Ничего чужого не удаляем и не перезапускаем: **не** трогайте конфиг `django-telegrambot-university`, порт 8001 и базу бота, **не** меняйте часовой пояс сервера, **не** включайте `ufw` (сейчас inactive — можно потерять SSH). Все команды ниже добавляют только своё.

Проверено заранее: установка по этой инструкции — на копии `cloud-001` (Ubuntu 24.04, 1 ядро / 1 ГБ, бот на 8001 с сайтом в nginx и заданием в cron — после установки работают как прежде); на чистых Ubuntu 24.04 и Debian 12 (2 ядра / 2 ГБ) — 308 автотестов (Python 3.11–3.13), сквозной сценарий админ → преподаватель → студент, нагрузка 300 студентов (16 800 запросов, 0 ошибок), бэкап → восстановление, перезагрузка.

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

Все команды — **на сервере, от root** (`ssh root@IP_СЕРВЕРА`). Если вы вошли не root, добавляйте `sudo` перед командами без `sudo -u`. Шаги 2–4 выполняйте **в одной SSH-сессии**: пароль базы хранится в переменной `$DB_PASS` до шага 4.

Папку вручную создавать не нужно — `/srv/ozp-test` создаётся на шаге 3. Все конфиги проекта (`gunicorn.service`, `nginx.conf`, `backup.sh`) уже указывают на этот путь.

### Шаг 0. Проверки (ничего не меняют)

```bash
curl -4 -s ifconfig.me; echo                      # IP этого сервера
getent hosts pbbtest.oaiu.kz                      # куда сейчас указывает поддомен
ss -ltnp | grep ':8002 ' || echo "8002 свободен"
grep -rn "pbbtest" /etc/nginx/ || echo "pbbtest в nginx не занят"
```

- **Если IP сервера ≠ IP поддомена** — попросите того, кто управляет DNS `oaiu.kz`, сделать A-запись `pbbtest.oaiu.kz → IP сервера`. Шаги 1–6 можно делать сразу, шаг 7 (HTTPS) — после смены DNS.
- **Если 8002 занят** — после шага 6 замените порт в `/etc/systemd/system/ozp-test.service` и `/etc/nginx/sites-available/ozp-test` (например, на 8003), затем `systemctl daemon-reload && systemctl restart ozp-test && systemctl reload nginx`.

### Шаг 1. Пакеты

nginx и PostgreSQL уже установлены и обслуживают бота — их не переустанавливаем, ставим только недостающее:

```bash
apt update
apt install -y python3-venv git gettext certbot python3-certbot-nginx
```

### Шаг 2. База данных

```bash
DB_PASS=$(openssl rand -hex 24)
sudo -u postgres psql -c "CREATE USER ozp WITH PASSWORD '$DB_PASS';"
sudo -u postgres psql -c "CREATE DATABASE ozp_test OWNER ozp ENCODING 'UTF8';"
```

Отдельная база и отдельный пользователь — база бота не затрагивается.

### Шаг 3. Системный пользователь, папка, код

```bash
adduser --system --group --no-create-home --home /srv/ozp-test ozp
mkdir /srv/ozp-test
chown ozp:ozp /srv/ozp-test
sudo -u ozp git clone https://github.com/DiyasKBTU/django-ozp-test.git /srv/ozp-test
cd /srv/ozp-test
sudo -u ozp python3 -m venv .venv
sudo -u ozp .venv/bin/pip install --no-cache-dir -r requirements.txt
```

Сообщение `adduser: The home dir /srv/ozp-test you specified can't be accessed` — нормально, папка создаётся следующей командой.

### Шаг 4. Файл `.env` (секреты создаются автоматически)

```bash
cd /srv/ozp-test
SECRET=$(sudo -u ozp .venv/bin/python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())")
sudo -u ozp tee .env > /dev/null <<EOF
SECRET_KEY=$SECRET
DEBUG=False
ALLOWED_HOSTS=pbbtest.oaiu.kz
DATABASE_URL=postgres://ozp:$DB_PASS@localhost:5432/ozp_test
CSRF_TRUSTED_ORIGINS=https://pbbtest.oaiu.kz
SECURE_HSTS_SECONDS=0
EOF
chmod 600 .env
grep -c "postgres://ozp:[0-9a-f]\{48\}@" .env     # должно вывести 1
```

Если вывело `0` — переменная `$DB_PASS` потерялась (новая SSH-сессия). Задайте новый пароль: `DB_PASS=$(openssl rand -hex 24); sudo -u postgres psql -c "ALTER USER ozp WITH PASSWORD '$DB_PASS';"` и повторите шаг 4.

`.env` не попадает в git; пароль базы потом можно посмотреть: `grep DATABASE_URL /srv/ozp-test/.env`.

### Шаг 5. Таблицы, статика, предметы, администратор

```bash
cd /srv/ozp-test
sudo -u ozp .venv/bin/python manage.py migrate
sudo -u ozp .venv/bin/python manage.py collectstatic --noinput
sudo -u ozp .venv/bin/python manage.py compilemessages --ignore=.venv
sudo -u ozp .venv/bin/python manage.py load_subjects
sudo -u ozp .venv/bin/python manage.py createsuperuser      # ваш логин и пароль администратора
sudo -u ozp mkdir -p media
```

**`load_demo` на сервере не запускаем** — это демо-вопросы для разработки.

### Шаг 6. Gunicorn и Nginx

```bash
cd /srv/ozp-test
cp deploy/gunicorn.service /etc/systemd/system/ozp-test.service
systemctl daemon-reload
systemctl enable --now ozp-test
systemctl is-active ozp-test                                            # active
curl -sI -H "Host: pbbtest.oaiu.kz" http://127.0.0.1:8002/ | head -1     # 301 — нормально, Django просит HTTPS

cp deploy/nginx.conf /etc/nginx/sites-available/ozp-test
ln -s /etc/nginx/sites-available/ozp-test /etc/nginx/sites-enabled/
chmod 755 /srv/ozp-test
nginx -t && systemctl reload nginx
```

`reload`, а не `restart`: сайт бота не прерывается. Если `nginx -t` выдал ошибку — **не делайте reload**: `rm /etc/nginx/sites-enabled/ozp-test` и разберите текст ошибки.

Gunicorn: 2 воркера на `127.0.0.1:8002` (≈ 70 МБ каждый; вместе с базой сайт занимает ≈ 200 МБ памяти).

### Шаг 7. HTTPS (когда поддомен указывает на этот сервер)

```bash
getent hosts pbbtest.oaiu.kz            # должен показать IP из шага 0
certbot --nginx -d pbbtest.oaiu.kz      # email, согласие (Y); certbot меняет только наш server-блок
certbot renew --dry-run                 # автопродление работает
```

Откройте https://pbbtest.oaiu.kz — должна открыться главная с замком. Затем включите HSTS:

```bash
cd /srv/ozp-test
sudo -u ozp sed -i 's/^SECURE_HSTS_SECONDS=0/SECURE_HSTS_SECONDS=31536000/' .env
systemctl restart ozp-test
sudo -u ozp .venv/bin/python manage.py check --deploy
```

`check --deploy` покажет 2 предупреждения — `W005` и `W021`. **Это правильно, не включайте их**: иначе HSTS распространится на все поддомены `oaiu.kz`.

### Шаг 8. Бэкап и cron

```bash
cd /srv/ozp-test
cp deploy/backup.sh /usr/local/bin/ozp-backup.sh
chmod +x /usr/local/bin/ozp-backup.sh
/usr/local/bin/ozp-backup.sh             # «бэкап дайын: …»
(crontab -l 2>/dev/null; echo "30 22 * * * /usr/local/bin/ozp-backup.sh >> /var/log/ozp-backup.log 2>&1") | crontab -
(crontab -u ozp -l 2>/dev/null; echo "*/5 * * * * cd /srv/ozp-test && .venv/bin/python manage.py finish_expired > /dev/null") | crontab -u ozp -
crontab -l; crontab -u ozp -l
```

Строки **добавляются** к существующим заданиям cron (задания бота сохраняются). Сервер в UTC: `22:30 UTC` = `03:30` по Алматы.

### Шаг 9. Проверка

```bash
curl -sI http://pbbtest.oaiu.kz/ | head -1                              # 301 (на https)
curl -sI https://pbbtest.oaiu.kz/ | grep -iE "^HTTP|strict-transport"   # 200 + HSTS
curl -sI https://pbbtest.oaiu.kz/static/js/timer.js | head -1           # 200 (статика)
systemctl is-active ozp-test nginx postgresql cron                     # 4 × active
ss -ltnp | grep -E ':8001 |:8002 '                                      # бот на 8001, наш сайт на 8002
```

В браузере:

- [ ] Вход в https://pbbtest.oaiu.kz/admin/ вашим логином из шага 5.
- [ ] Переключатель KK / RU меняет язык.
- [ ] Преподаватель загружает вопрос с картинкой — картинка видна.
- [ ] В вопросе по математике `\(\frac{1}{2}\)` показывается формулой.
- [ ] Бот работает как раньше.
- [ ] На следующий день в `/var/backups/ozp-test` есть новый `db-*.sql.gz`.

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

Если менялся `apps/quiz/data/subjects.json` — ещё `sudo -u ozp .venv/bin/python manage.py load_subjects`. Если менялись `deploy/nginx.conf` или `deploy/gunicorn.service`, скопируйте их заново (шаг 6). **Внимание:** certbot дописал HTTPS в установленный nginx-конфиг, поэтому после копирования nginx-конфига снова выполните `sudo certbot --nginx -d pbbtest.oaiu.kz` (на вопрос certbot выберите «Attempt to reinstall this existing certificate»).

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
scp root@IP_СЕРВЕРА:~/db-2026-10-15.sql.gz .
scp root@IP_СЕРВЕРА:~/media-2026-10-15.tar.gz .
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
| Открылся другой сайт (бот) / ошибка сертификата | Нет сертификата для pbbtest — выполните шаг 7 (и проверьте DNS, шаг 0). Проверка: `sudo nginx -T \| grep -n "server_name"`. |
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
