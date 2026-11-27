"""Email for Find-IT.

While no real mail server is set (local PC), emails are printed in the Find-IT
window AND copied into the Test inbox page, so nobody has to read the black window.
Real sending (SMTP) is planned for v3.0.0 when the app is online.
"""
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.core.mail.backends.console import EmailBackend as ConsoleBackend


class ConsoleAndTestInboxBackend(ConsoleBackend):
    def send_messages(self, email_messages):
        count = super().send_messages(email_messages)
        from .models import TestEmail
        User = get_user_model()
        for message in email_messages or []:
            body = message.body
            for recipient in message.to or []:
                user = User.objects.filter(email__iexact=recipient).first()
                TestEmail.objects.create(
                    recipient=user, to=recipient[:500], subject=(message.subject or "")[:255], body=body,
                )
        return count


def test_inbox_enabled():
    return bool(getattr(settings, "FINDIT_TEST_INBOX", False))


def send_findit_email(user, subject, body):
    if not user.email:
        return 0
    return send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=True)
