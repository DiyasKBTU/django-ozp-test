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

Оқытушы беттері (`is_staff` қолданушыға): сұрақтар — http://127.0.0.1:8000/teacher/questions/ , контексттер — `/teacher/contexts/`, банк толуы — `/teacher/bank/`.

Linux/macOS-та `.venv\Scripts\python` орнына `.venv/bin/python` жазыңыз.

## Демо сұрақтар

`load_demo` командасы тексеруге арналған сұрақтарды (`is_demo=True`) жүктейді: әр тіл үшін әр тақырыпшаға 6 үлгі сұрақ, Python коды бар бірнеше нақты сұрақ және 4 контекст × 5 сұрақ.

**Нақты пайдалануға дейін демо сұрақтарды міндетті түрде өшіріңіз:**

```powershell
.venv\Scripts\python manage.py load_demo --delete
```

## Мерзімі өткен тесттер

Тест уақыты біткенде (125 минут немесе сессияның жабылуы) әрекет кез келген бетте ашылған сәтте өзі аяқталады. Студент бетті қайта ашпаса да нәтиже дұрыс көрінуі үшін серверде cron арқылы (мысалы, 5 минут сайын) мына команданы іске қосуға болады:

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
