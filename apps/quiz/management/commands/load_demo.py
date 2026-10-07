"""
Тексеруге арналған демо сұрақтарды жүктейді (барлығы is_demo=True).

Әр тіл (kk, ru) үшін:
- әр тақырыпшаға 6 үлгі сұрақ (деңгейлері A, A, B, B, B, C);
- Python коды бар 6 нақты сұрақ (13–16 тақырыпшалар);
- 4 контекст × 5 сұрақ (біреуі — Python программасы бар нақты контекст).

Іске қосу:
    python manage.py load_demo            # демо деректерді жүктеу
    python manage.py load_demo --delete   # демо деректерді толық өшіру

Нақты пайдалануға дейін `load_demo --delete` міндетті түрде орындалады.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.quiz.constants import SUBTOPICS_COUNT
from apps.quiz.models import Answer, Attempt, Context, Question, Subtopic

LANGUAGES = ["kk", "ru"]

# Бір тақырыпшадағы үлгі сұрақтардың деңгейлері
SINGLE_LEVELS = ["A", "A", "B", "B", "B", "C"]

# Үлгі контексттегі 5 сұрақтың деңгейлері
CONTEXT_LEVELS = ["A", "B", "B", "B", "C"]

# Үлгі мәтіндер
TEMPLATE_TEXT = {
    "kk": "[ДЕМО] {subtopic:02d}-тақырыпша, {level} деңгей, №{index} сұрақ. Дұрыс жауапты таңдаңыз.",
    "ru": "[ДЕМО] Подтема {subtopic:02d}, уровень {level}, вопрос №{index}. Выберите правильный ответ.",
}
TEMPLATE_ANSWER = {
    "kk": "Демо жауап {letter}",
    "ru": "Демо ответ {letter}",
}


# ---------- Python коды бар нақты сұрақтар ----------
# Әр жауап тізімінде бірінші нұсқа — дұрыс (тест кезінде реті араластырылады)

REAL_QUESTIONS = [
    {
        "subtopic": 13,
        "level": "A",
        "text": {
            "kk": "x жұп сан болғанда «Yes» шығаратын код қайсы?",
            "ru": "Какой код выводит «Yes», когда x — чётное число?",
        },
        "code": "",
        "answers": [
            'if x % 2 == 0:\n    print("Yes")',
            'if x % 2 == 1:\n    print("Yes")',
            'if x / 2 == 0:\n    print("Yes")',
            'if x // 2 == 0:\n    print("Yes")',
        ],
    },
    {
        "subtopic": 13,
        "level": "B",
        "text": {
            "kk": "Программа нені шығарады?",
            "ru": "Что выведет программа?",
        },
        "code": (
            "x = 7\n"
            "if x > 5:\n"
            "    if x % 2 == 0:\n"
            '        print("A")\n'
            "    else:\n"
            '        print("B")\n'
            "else:\n"
            '    print("C")'
        ),
        "answers": ["B", "A", "C", "AB"],
    },
    {
        "subtopic": 14,
        "level": "A",
        "text": {
            "kk": "Программа нені шығарады?",
            "ru": "Что выведет программа?",
        },
        "code": "s = 0\nfor i in range(1, 5):\n    s += i\nprint(s)",
        "answers": ["10", "15", "4", "6"],
    },
    {
        "subtopic": 14,
        "level": "B",
        "text": {
            "kk": "Цикл аяқталғаннан кейін count айнымалысының мәні қандай?",
            "ru": "Какое значение будет у переменной count после завершения цикла?",
        },
        "code": "n = 100\ncount = 0\nwhile n > 1:\n    n = n // 2\n    count += 1\nprint(count)",
        "answers": ["6", "7", "5", "50"],
    },
    {
        "subtopic": 15,
        "level": "B",
        "text": {
            "kk": "Программа нені шығарады?",
            "ru": "Что выведет программа?",
        },
        "code": "a = [5, 2, 8, 1]\na.sort(reverse=True)\nprint(a[1])",
        "answers": ["5", "2", "8", "1"],
    },
    {
        "subtopic": 16,
        "level": "C",
        "text": {
            "kk": "f(7) функциясы қандай мән қайтарады?",
            "ru": "Какое значение вернёт функция f(7)?",
        },
        "code": (
            "def f(n):\n"
            "    if n <= 1:\n"
            "        return 1\n"
            "    return n * f(n - 2)\n"
            "\n"
            "print(f(7))"
        ),
        "answers": ["105", "5040", "15", "35"],
    },
]


# ---------- Контексттер ----------

# Python программасы бар нақты контекст және оның 5 сұрағы
REAL_CONTEXT = {
    "title": {
        "kk": "[ДЕМО] Жұп сандардың қосындысы",
        "ru": "[ДЕМО] Сумма чётных чисел",
    },
    "text": {
        "kk": "Төмендегі Python программасын оқып, сұрақтарға жауап беріңіз.",
        "ru": "Прочитайте программу на Python и ответьте на вопросы.",
    },
    "code": (
        "numbers = [3, 8, 1, 6, 4]\n"
        "total = 0\n"
        "for n in numbers:\n"
        "    if n % 2 == 0:\n"
        "        total += n\n"
        "print(total)"
    ),
    "questions": [
        {
            "subtopic": 14,
            "level": "A",
            "text": {
                "kk": "Программа нені шығарады?",
                "ru": "Что выведет программа?",
            },
            "answers": ["18", "22", "4", "8"],
        },
        {
            "subtopic": 14,
            "level": "B",
            "text": {
                "kk": "for циклі неше рет орындалады?",
                "ru": "Сколько раз выполнится цикл for?",
            },
            "answers": ["5", "3", "4", "6"],
        },
        {
            "subtopic": 13,
            "level": "B",
            "text": {
                "kk": "«n % 2 == 0» шартын «n % 2 == 1» деп ауыстырса, программа нені шығарады?",
                "ru": "Что выведет программа, если условие «n % 2 == 0» заменить на «n % 2 == 1»?",
            },
            "answers": ["4", "18", "3", "0"],
        },
        {
            "subtopic": 15,
            "level": "B",
            "text": {
                "kk": "numbers айнымалысының типі қандай?",
                "ru": "Какой тип у переменной numbers?",
            },
            "answers": ["list", "tuple", "dict", "set"],
        },
        {
            "subtopic": 14,
            "level": "C",
            "text": {
                "kk": "Циклдің үшінші қадамынан кейін total мәні қандай?",
                "ru": "Чему равно total после третьего шага цикла?",
            },
            "answers": ["8", "9", "12", "0"],
        },
    ],
}

# Үлгі контексттер: атауы, мәтіні және сұрақтарының тақырыпшалары
TEMPLATE_CONTEXTS = [
    {
        "title": {
            "kk": "[ДЕМО] Дүкеннің сатылым кестесі",
            "ru": "[ДЕМО] Таблица продаж магазина",
        },
        "text": {
            "kk": "Тауар | Саны | Бағасы\nДәптер | 120 | 150\nҚалам | 300 | 80\nКітап | 45 | 2500",
            "ru": "Товар | Количество | Цена\nТетрадь | 120 | 150\nРучка | 300 | 80\nКнига | 45 | 2500",
        },
        "subtopics": [9, 10, 10, 9, 10],
    },
    {
        "title": {
            "kk": "[ДЕМО] Кітапхананың мәліметтер қоры",
            "ru": "[ДЕМО] База данных библиотеки",
        },
        "text": {
            "kk": "Books(id, title, author, year) және Readers(id, name, book_id) кестелері берілген.",
            "ru": "Даны таблицы Books(id, title, author, year) и Readers(id, name, book_id).",
        },
        "subtopics": [11, 11, 12, 12, 11],
    },
    {
        "title": {
            "kk": "[ДЕМО] Мектептің компьютерлік желісі",
            "ru": "[ДЕМО] Компьютерная сеть школы",
        },
        "text": {
            "kk": "Мектепте 3 компьютер сыныбы бар, олар бір коммутатор арқылы Wi-Fi роутерге қосылған.",
            "ru": "В школе 3 компьютерных класса, подключённых через коммутатор к Wi-Fi роутеру.",
        },
        "subtopics": [6, 6, 7, 7, 6],
    },
]


def create_question(subtopic, language, level, text, answers, code="", context=None):
    """Сұрақ пен оның 4 жауабын жасайды; answers тізімінің бірінші элементі — дұрыс."""
    question = Question.objects.create(
        subtopic=subtopic,
        context=context,
        language=language,
        text=text,
        code=code,
        level=level,
        is_demo=True,
    )
    for index, answer_text in enumerate(answers):
        Answer.objects.create(question=question, text=answer_text, is_correct=(index == 0))
    return question


def template_answers(language):
    return [TEMPLATE_ANSWER[language].format(letter=letter) for letter in "ABCD"]


class Command(BaseCommand):
    help = "Демо сұрақтарды жүктейді (--delete — толық өшіреді)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--delete",
            action="store_true",
            help="Барлық демо сұрақтар мен контексттерді өшіру",
        )

    def handle(self, *args, **options):
        if options["delete"]:
            self.delete_demo()
        else:
            self.load_demo()

    @transaction.atomic
    def delete_demo(self):
        # Демо сұрақтар кездескен тест әрекеттері де өшеді (олар тек тексеруге арналған)
        attempt_ids = list(
            Attempt.objects.filter(items__question__is_demo=True)
            .values_list("pk", flat=True)
            .distinct()
        )
        Attempt.objects.filter(pk__in=attempt_ids).delete()

        demo_questions = Question.objects.filter(is_demo=True)
        question_count = demo_questions.count()
        demo_questions.delete()  # жауаптары бірге өшеді (CASCADE)

        # Нақты (демо емес) сұрақ байланған демо контекст өшірілмейді
        demo_contexts = Context.objects.filter(is_demo=True)
        used_contexts = demo_contexts.filter(questions__isnull=False).distinct()
        free_contexts = demo_contexts.exclude(pk__in=used_contexts)
        context_count = free_contexts.count()
        free_contexts.delete()

        self.stdout.write(
            self.style.SUCCESS(
                f"Өшірілді: {question_count} демо сұрақ, {context_count} демо контекст, "
                f"{len(attempt_ids)} тест әрекеті."
            )
        )
        if used_contexts.exists():
            self.stdout.write(
                self.style.WARNING(
                    "Назар аударыңыз: келесі демо контексттерге нақты сұрақтар байланған, "
                    "сондықтан олар өшірілмеді: "
                    + ", ".join(str(context.pk) for context in used_contexts)
                )
            )

    @transaction.atomic
    def load_demo(self):
        subtopics = {subtopic.number: subtopic for subtopic in Subtopic.objects.all()}
        if len(subtopics) != SUBTOPICS_COUNT:
            raise CommandError("Алдымен тақырыптарды жүктеңіз: python manage.py load_topics")

        if Question.objects.filter(is_demo=True).exists():
            self.stdout.write(
                self.style.WARNING(
                    "Демо сұрақтар бұрыннан бар. Қайта жүктеу үшін алдымен "
                    "`python manage.py load_demo --delete` орындаңыз."
                )
            )
            return

        for language in LANGUAGES:
            # 1) Әр тақырыпшаға 6 үлгі сұрақ
            for number, subtopic in subtopics.items():
                for index, level in enumerate(SINGLE_LEVELS, start=1):
                    text = TEMPLATE_TEXT[language].format(
                        subtopic=number, level=level, index=index
                    )
                    create_question(subtopic, language, level, text, template_answers(language))

            # 2) Python коды бар нақты сұрақтар
            for item in REAL_QUESTIONS:
                create_question(
                    subtopics[item["subtopic"]],
                    language,
                    item["level"],
                    item["text"][language],
                    item["answers"],
                    code=item["code"],
                )

            # 3) Python программасы бар нақты контекст
            context = Context.objects.create(
                language=language,
                title=REAL_CONTEXT["title"][language],
                text=REAL_CONTEXT["text"][language],
                code=REAL_CONTEXT["code"],
                is_demo=True,
            )
            for item in REAL_CONTEXT["questions"]:
                create_question(
                    subtopics[item["subtopic"]],
                    language,
                    item["level"],
                    item["text"][language],
                    item["answers"],
                    context=context,
                )

            # 4) Үлгі контексттер
            for template in TEMPLATE_CONTEXTS:
                context = Context.objects.create(
                    language=language,
                    title=template["title"][language],
                    text=template["text"][language],
                    is_demo=True,
                )
                for index, (number, level) in enumerate(
                    zip(template["subtopics"], CONTEXT_LEVELS), start=1
                ):
                    text = TEMPLATE_TEXT[language].format(
                        subtopic=number, level=level, index=index
                    )
                    create_question(
                        subtopics[number],
                        language,
                        level,
                        text,
                        template_answers(language),
                        context=context,
                    )

        question_count = Question.objects.filter(is_demo=True).count()
        context_count = Context.objects.filter(is_demo=True).count()
        self.stdout.write(
            self.style.SUCCESS(
                f"Жүктелді: {question_count} демо сұрақ, {context_count} демо контекст."
            )
        )
