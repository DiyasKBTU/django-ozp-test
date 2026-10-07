# Информатика тест платформасы (ПББ)

Информатика пәні бойынша педагогтердің білімін бағалау (ПББ) тестін нақты форматта жаттықтыруға арналған Django платформасы: 50 сұрақ, 125 минут. Толық техникалық тапсырма — [TZ.md](TZ.md).

## Жергілікті іске қосу (Windows)

Python 3.12 немесе одан жаңа нұсқасы қажет.

```powershell
# 1. Виртуалды орта және кітапханалар
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt

# 2. Баптаулар: .env.example файлын .env деп көшіру (DEBUG=True қалдырыңыз)
copy .env.example .env

# 3. Деректер қоры, тақырыптар және демо сұрақтар
.venv\Scripts\python manage.py migrate
.venv\Scripts\python manage.py load_topics
.venv\Scripts\python manage.py load_demo

# 4. Әкімші жасау және серверді іске қосу
.venv\Scripts\python manage.py createsuperuser
.venv\Scripts\python manage.py runserver
```

Сайт: http://127.0.0.1:8000/ , басқару панелі: http://127.0.0.1:8000/admin/

Оқытушы беттері (`is_staff` қолданушыға): сұрақтар — http://127.0.0.1:8000/teacher/questions/ , контексттер — `/teacher/contexts/`, банк толуы — `/teacher/bank/`, нәтижелер және CSV — `/teacher/results/`.

Студент беттері: кабинет — `/dashboard/`, тақырыптық жаттығу (бір тақырыптан 10 сұрақ, таймерсіз, дұрыс жауап бірден көрсетіледі) — `/practice/`.

Linux/macOS-та `.venv\Scripts\python` орнына `.venv/bin/python` жазыңыз.

## Оқытушыны қосу

Сайттағы тіркелу беті тек студенттерге арналған. Оқытушыны тек әкімші (`createsuperuser` арқылы жасалған қолданушы) басқару панелінде қосады:

1. http://127.0.0.1:8000/admin/ → «Пайдаланушылар» → «Қосу».
2. Логин, құпия сөз, аты-жөні; **«Қызметкер мәртебесі»** (`is_staff`) белгісі.
3. Сол беттегі «Профиль» бөлімінде оқытушының **пәндерін** таңдау → «Сақтау».

Пәні жоқ оқытушы `/teacher/...` беттерінде «Сізге пән тағайындалмаған» хабарламасын көреді. Бар қолданушыны оқытушы ету үшін оның бетінде дәл осы белгі мен пәндерді қойса жеткілікті.

Оқытушы басқару панелінде тек **өз пәндерінің** тест сессиялары мен топтарын көреді, жасайды және өзгертеді (бөлек рұқсат тағайындау керек емес). Қолданушыларды басқару, жазбаларды өшіру — тек әкімшіге.

## Пәндер

Пәндер, тақырыптар мен тақырыпшалар `apps/quiz/data/subjects.json` файлында (TZ.md, 10-бөлім). Жүктеу:

```powershell
.venv\Scripts\python manage.py load_subjects                     # барлық пән
.venv\Scripts\python manage.py load_subjects --only mathematics  # бір пән
```

Команданы қайта іске қосуға болады (жазбалар жаңартылады). `load_topics` — бұрынғы команда, `load_subjects --only informatics` деген сөз. Тест уақыты пәннен алынады: информатика мен математика — 125 минут, көркем еңбек — 80 минут.

## Демо сұрақтар

`load_demo` командасы тексеруге арналған сұрақтарды (`is_demo=True`) жүктейді: әр тіл үшін әр тақырыпшаға 6 үлгі сұрақ, Python коды бар бірнеше нақты сұрақ және 4 контекст × 5 сұрақ.

**Нақты пайдалануға дейін демо сұрақтарды міндетті түрде өшіріңіз:**

```powershell
.venv\Scripts\python manage.py load_demo --delete
```

## Мерзімі өткен тесттер

Тест уақыты біткенде (пәннің уақыты — 80 / 125 минут — немесе сессияның жабылуы) әрекет кез келген бетте ашылған сәтте өзі аяқталады. Студент бетті қайта ашпаса да нәтиже дұрыс көрінуі үшін серверде cron арқылы (мысалы, 5 минут сайын) мына команданы іске қосуға болады:

```powershell
.venv\Scripts\python manage.py finish_expired
```

## Аударма (қазақша / орысша)

Интерфейстің бастапқы мәтіні — қазақша, орысша аудармасы — `locale/ru/LC_MESSAGES/django.po`. Дайын `.mo` файлдары git-те бар, сондықтан жай іске қосу үшін ештеңе қажет емес.

Мәтін өзгерсе немесе жаңасы қосылса, GNU gettext керек (Windows: `winget install mlocati.GetText`, Ubuntu: `sudo apt install gettext`):

```powershell
# 1. Жаңа жолдарды .po файлдарына жинау
.venv\Scripts\python manage.py makemessages -l kk -l ru --ignore=.venv
# 2. locale/ru/LC_MESSAGES/django.po ішінде бос msgstr "" жолдарын аудару
# 3. .mo файлдарын жасау (оларды да commit жасаңыз)
.venv\Scripts\python manage.py compilemessages --ignore=.venv
```

## Тесттер

```powershell
.venv\Scripts\python manage.py test
```

## Жүктеме тесті (Locust)

[loadtest/locustfile.py](loadtest/locustfile.py) нақты студенттің жолын қайталайды: тест аккаунтымен кіреді → ашық сессияда тестті бастайды → 50 сұраққа 5–20 секунд аралықпен жауап береді → тестті аяқтайды. Бір виртуалды студентке — бір аккаунт (бір сессияда бір әрекет болғандықтан), сондықтан 1000 студентке 1000 аккаунт керек.

**Маңызды:** жүктеме тестін серверде (PostgreSQL + Gunicorn) жүргізіңіз. Жергілікті `runserver` + SQLite бір мезгілде жазуды көтермейді: бірнеше студент қатар жауап сақтаса, `database is locked` (HTTP 500) қатесі шығады. Жергілікті ортада тек скрипттің жұмысын 2–3 студентпен (`-u 3 -r 1`) тексеруге болады.

**1. Деректер** (сервердегі жобада; банкте тестке жететін сұрақ болуы керек):

```bash
sudo -u ozp .venv/bin/python manage.py loadtest_data --count 1000
# → Locust үшін: LOADTEST_SESSION_ID=7 LOADTEST_ACCOUNTS=1000
```

Команда `student001`–`student1000` аккаунттарын (`--count` әдепкісі — 100: `student001`–`student100`) және тек солардың «LOADTEST» тобына ашық сессияны жасайды; нақты студенттер бұл сессияны көрмейді. Аккаунттардың құпия сөзі — `loadtest-pass-2026` (`--password` арқылы өзгертуге болады). Қайта іске қосқанда бұрынғы әрекеттер өшіріледі де, сессия қайта ашылады.

**2. Locust** (өз компьютеріңізде, бөлек виртуалды ортада):

```powershell
python -m venv .venv-loadtest
.venv-loadtest\Scripts\python -m pip install -r loadtest/requirements.txt

$env:LOADTEST_SESSION_ID = "7"
$env:LOADTEST_ACCOUNTS = "1000"
# Windows gevent DLL-ін бұғаттаса (DLL load failed): $env:PURE_PYTHON = "1"
.venv-loadtest\Scripts\locust -f loadtest/locustfile.py --host https://test.example.kz --headless -u 1000 -r 5 --run-time 40m --html loadtest-report.html
```

- `-u 1000` — виртуалды студенттер саны (`LOADTEST_ACCOUNTS`-тан аспауы керек), `-r 5` — секундына қанша студент қосылады. Кіру кезінде құпия сөз тексеру процессорды көп жұмсайды, сондықтан студенттерді біртіндеп қосқан дұрыс.
- Бір студенттің тесті шамамен 11 минут (50 × орташа 12,5 с). Барлығы аяқтағанда Locust өзі тоқтайды; `--run-time` — тек сақтық үшін.
- `--headless` жазылмаса, нәтижені браузерде көруге болады: http://localhost:8089 .
- Басқа баптаулар: `LOADTEST_PASSWORD`, `LOADTEST_LANGUAGE` (`kk` / `ru`), `LOADTEST_MIN_WAIT`, `LOADTEST_MAX_WAIT` (секунд).
- Locust-ты бір процесте іске қосыңыз (`--processes` жоқ): аккаунттар ретімен беріледі.

**3. Тазалау** (міндетті — аккаунттардың құпия сөзі белгілі):

```bash
sudo -u ozp .venv/bin/python manage.py loadtest_data --delete
```

## Серверге орнату

VPS-ке (Ubuntu 24.04: Nginx + Gunicorn + PostgreSQL + HTTPS) қадамдап орнату, бэкап және жаңарту тәртібі — [deploy/DEPLOY.md](deploy/DEPLOY.md). Баптау файлдары: `deploy/nginx.conf`, `deploy/gunicorn.service`, `deploy/backup.sh`.
