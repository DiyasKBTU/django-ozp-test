"""
Django-ның дайын құпия сөз тексерулері, тек мәтіндері біздің аудармада.
Django-ның қазақша аудармасында бұл мәтіндер жоқ (ағылшынша шығады),
сондықтан хабарламаларды осында қайта жазамыз; тексеру ережелері өзгермейді.
"""

from django.contrib.auth import password_validation
from django.utils.translation import gettext as _


class MinimumLengthValidator(password_validation.MinimumLengthValidator):
    def get_error_message(self):
        # %(min_length)d мәнін ValidationError өзі қояды
        return _("Құпия сөз тым қысқа: кемінде %(min_length)d таңба болуы керек.")

    def get_help_text(self):
        return _("Кемінде %(min_length)d таңба.") % {"min_length": self.min_length}


class UserAttributeSimilarityValidator(
    password_validation.UserAttributeSimilarityValidator
):
    def get_error_message(self):
        return _("Құпия сөз логинге немесе аты-жөніңізге тым ұқсас.")

    def get_help_text(self):
        return _("Логинге және аты-жөніңізге ұқсамауы керек.")


class CommonPasswordValidator(password_validation.CommonPasswordValidator):
    def get_error_message(self):
        return _("Бұл құпия сөз тым қарапайым әрі жиі қолданылады.")

    def get_help_text(self):
        return _("Тым қарапайым болмауы керек.")


class NumericPasswordValidator(password_validation.NumericPasswordValidator):
    def get_error_message(self):
        return _("Құпия сөз тек сандардан тұрмауы керек.")

    def get_help_text(self):
        return _("Тек сандардан тұрмауы керек.")
