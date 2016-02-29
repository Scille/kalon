from datetime import datetime
from mongoengine import ValidationError
from string import ascii_uppercase, ascii_lowercase, digits, punctuation

from kalon.model_util import BaseController, BaseSolrSearcher, BaseDocument, fields

from sample.tasks.email import default_mail, mail, default_subject
from sample.roles import ROLES


def generate_password(length=12):
    from passlib.utils import generate_password as gen_pwd
    choice = ascii_uppercase + ascii_lowercase + digits + punctuation
    return gen_pwd(length, choice)


class UserController(BaseController):

    def clean(self):
        if not self.document.password:
            raise ValidationError(errors={'mot_de_passe':
                                          'Ce champ est obligatoire'})

    def set_password(self, password):
        """Store the password encrypted (i.e. hashed&salted)"""
        from kalon.auth import encrypt_password
        self.document.password = encrypt_password(password)

    def set_password_and_email(self):
        from kalon.auth import encrypt_password
        clear_pwd = generate_password()
        self.document.password = encrypt_password(clear_pwd)
        # send email
        body = default_mail.format(name=self.document.email, password=clear_pwd)
        mail.send(subject=default_subject, recipient=self.document.email, body=body)

    def close_user(self, fin_validite=None):
        if not self.document.fin_validite:
            self.document.fin_validite = fin_validite or datetime.utcnow()
            return True
        else:
            # user already closed
            return False


class UserSearcher(BaseSolrSearcher):
    FIELDS = ('email', 'role')


class User(BaseDocument):
    meta = {'controller_cls': UserController, 'searcher_cls': UserSearcher}

    email = fields.EmailField(max_length=255, required=True, unique=True)
    role = fields.StringField(choices=list(ROLES.keys()), null=True)
    password = fields.StringField(max_length=255)
    permissions = fields.ListField(fields.StringField(), default=list)
    lastname = fields.StringField(max_length=255)
    firstname = fields.StringField(max_length=255)
