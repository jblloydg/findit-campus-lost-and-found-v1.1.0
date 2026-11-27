import io
import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from PIL import Image

from core.models import Category, ItemPost, Profile, QuestionTemplate

User = get_user_model()
PASSWORD = "TestOnly!Pass2026"
MEDIA_DIR = tempfile.mkdtemp(prefix="findit-test-media-")
BACKUP_DIR = tempfile.mkdtemp(prefix="findit-test-backups-")


def photo(name="item.jpg"):
    buffer = io.BytesIO()
    Image.new("RGB", (40, 30), (40, 90, 140)).save(buffer, "JPEG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/jpeg")


@override_settings(
    MEDIA_ROOT=MEDIA_DIR,
    BACKUP_DIR=BACKUP_DIR,
    CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}},
)
class FindItTestCase(TestCase):
    """Fictional test accounts and helpers. Migrations seed categories and the question bank."""

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_DIR, ignore_errors=True)
        shutil.rmtree(BACKUP_DIR, ignore_errors=True)

    def setUp(self):
        self.finder = self.make_user("2026-0001")
        self.alice = self.make_user("2026-0002")
        self.bob = self.make_user("2026-0003")
        self.carol = self.make_user("2026-0004")
        self.staff = self.make_user("guard.test", role=Profile.Role.STAFF)
        self.admin = self.make_user("admin.test", role=Profile.Role.ADMIN)
        self.category = Category.objects.get(name="Keys")

    def make_user(self, username, role=Profile.Role.STUDENT, verified=True):
        user = User.objects.create_user(username=username, password=PASSWORD, first_name=username)
        profile = Profile.objects.get(user=user)
        profile.role = role
        if role == Profile.Role.STUDENT:
            profile.student_id = username
            if verified:
                # v1.1.1: existing tests use verified students (normal limits).
                from django.utils import timezone
                profile.email_verified_at = timezone.now()
                profile.student_id_locked = True
        profile.save()
        return User.objects.select_related("profile").get(pk=user.pk)

    def client_for(self, user):
        client = Client()
        client.force_login(user)
        return client

    def create_post(self, user=None, post_type="FOUND", questions=(), **extra):
        client = self.client_for(user or self.finder)
        data = {"post_type": post_type, "category": self.category.pk, "photos": [photo()]}
        if questions:
            data["questions"] = [q.pk for q in questions]
        data.update(extra)
        response = client.post("/posts/new/", data)
        self.assertEqual(response.status_code, 302, getattr(response, "context", None) and response.context["form"].errors)
        return ItemPost.objects.filter(author=user or self.finder).latest("created_at")

    def claim(self, post, user, description="It has a red tag on it."):
        data = {f"answer_{q.pk}": (q.choices[0] if q.choices else "an answer") for q in post.verification_questions.all()}
        data["description"] = description
        return self.client_for(user).post(f"/posts/{post.pk}/claim/", data)

    def default_templates(self):
        return list(QuestionTemplate.objects.filter(is_default=True))
