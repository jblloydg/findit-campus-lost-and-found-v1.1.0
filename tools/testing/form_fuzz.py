import os, sys
# Run from the project folder: python tools/testing/form_fuzz.py  (see tools/testing/README.md)
sys.path.insert(0, os.getcwd())
SERVER_CMD = [sys.executable, "manage.py", "runserver", "127.0.0.1:8765", "--noreload"]
CHROME = {"executable_path": os.environ["CHROME_PATH"]} if os.environ.get("CHROME_PATH") else {}
import os, sys, itertools
sys.path.insert(0, os.getcwd())
os.environ["DJANGO_SETTINGS_MODULE"] = "findit.settings"; os.environ["DJANGO_DEBUG"] = "1"
import django; django.setup()
from django.conf import settings; settings.ALLOWED_HOSTS = ["*"]
from django.test import Client
from django.urls import get_resolver, URLPattern, URLResolver
from django.contrib.auth import get_user_model
from core.models import ItemPost, ClaimApplication, Conversation, ChatQuestion, StatusChangeRequest, AbuseReport, GeneralReport, Comment, Category, QuestionTemplate, IdReviewCase, TurnInTicket
U = get_user_model()
ids = {
    "post_id": [str(p.pk) for p in ItemPost.objects.all()[:6]],
    "claim_id": [str(c.pk) for c in ClaimApplication.objects.all()[:4]],
    "conversation_id": [str(c.pk) for c in Conversation.objects.all()[:4]],
    "question_id": [str(q.pk) for q in ChatQuestion.objects.all()[:2]] or ["1"],
    "request_id": [str(r.pk) for r in StatusChangeRequest.objects.all()[:2]] or ["1"],
    "report_id": [str(r.pk) for r in list(AbuseReport.objects.all()[:1]) + list(GeneralReport.objects.all()[:1])] or ["00000000-0000-0000-0000-000000000000"],
    "comment_id": [str(c.pk) for c in Comment.objects.all()[:1]] or ["1"],
    "category_id": [str(Category.objects.first().pk)],
    "template_id": [str(QuestionTemplate.objects.first().pk)],
    "user_id": [str(u.pk) for u in U.objects.all()],
    "case_id": ["1"],
    "code": [t.code for t in TurnInTicket.objects.all()[:2]] + ["NOPE1234"],
    "uidb64": ["MQ"], "token": ["x-y"],
    "attachment_id": [str(a.pk) for a in __import__("core.models", fromlist=["ChatAttachment"]).ChatAttachment.objects.all()[:2]] or ["1"],
    "part": ["file", "preview", "../../etc/passwd"],
}
def walk(patterns, prefix=""):
    for p in patterns:
        if isinstance(p, URLResolver):
            yield from walk(p.url_patterns, prefix + str(p.pattern))
        elif isinstance(p, URLPattern):
            yield prefix + str(p.pattern)
import re
routes = [r for r in walk(get_resolver().url_patterns) if not r.startswith(("django-admin", "captcha", "static", "media"))]
payloads = [{}, {"action": "x", "reason": "'; DROP TABLE x;--", "text": "x"*5000, "decision": "transfer", "user_id": "abc",
             "role": "developer", "is_active": "1", "first_name": "A", "code": "12345678901234567890", "student_id": "' or 1=1",
             "recipient_id": "999999", "claim_id": "not-a-uuid", "requested_status": "OPEN", "answer": "y", "questions": ["a", "999"],
             "next": "https://evil.example.com/"}]
problems = []
for username in ["2026-0001", "2026-0005", "security.demo", "moderator.demo", "findit-admin"]:
    user = U.objects.get(username=username)
    for route in routes:
        names = re.findall(r"<(?:\w+:)?(\w+)>", route)
        options = [ids.get(n, ["1"]) for n in names]
        for combo in itertools.product(*[o[:2] for o in options]):
            url = "/" + route
            for n, v in zip(names, combo):
                url = re.sub(r"<(?:\w+:)?" + n + ">", v, url, count=1)
            for data in payloads:
                c = Client(raise_request_exception=False); c.force_login(user)
                if url.startswith("/logout"): continue
                r = c.post(url, data)
                if r.status_code >= 500:
                    problems.append((username, url, sorted(data)[:3], r.status_code))
print("routes:", len(routes)); print("PROBLEMS:", len(problems))
for p in problems[:40]: print(p)
