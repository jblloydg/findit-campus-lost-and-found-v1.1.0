"""Fictional local demo data. Never deploy with demo data enabled.

Creates demo accounts plus example listings that show every feature:
shared FOUND post with approved / submitted / declined claims, a LOST post
with an owner verification in progress (answered question cards), an item
at the guard house with a pending finder status request, and a walk-in item.
Photos are simple generated pictures, not real photos.
"""
import io

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from PIL import Image, ImageDraw

from core import demo_logins
from core.models import (
    Category, ClaimAnswer, ModeratorVerification, ClaimApplication, Comment, Conversation, GuardhouseIntake, ItemPost, PostPhoto,
    PostShare, PostStatusEvent, Profile, QuestionTemplate, StatusChangeRequest,
)
from core.services import (
    answer_chat_question, apply_post_questions, change_moderator_verification, approve_claim, ask_chat_questions, create_claim_conversation,
    create_lost_post_conversation, decline_claim, record_status, turn_over_to_guardhouse,
)

User = get_user_model()

# Fictional people with reserved example.com addresses (RFC 2606), never real students.
# (username, first name, last name, email, role, label). Passwords are NOT here (CHG-008):
# each PC gets random ones, saved in demo-logins.txt (see core/demo_logins.py).
ACCOUNTS = [
    ("2026-0001", "Alex", "Finder", "alex.finder@example.com", Profile.Role.STUDENT, "Student, finder (verified)"),
    ("2026-0002", "Jamie", "Claimant", "jamie.claimant@example.com", Profile.Role.STUDENT, "Student, claimant (verified)"),
    ("2026-0003", "Sam", "Second", "sam.second@example.com", Profile.Role.STUDENT, "Student, second claimant (verified)"),
    ("2026-0004", "Riley", "Third", "riley.third@example.com", Profile.Role.STUDENT, "Student, declined claimant (verified)"),
    # v1.1.1: a student who has NOT verified yet, to show the limits and the red warning.
    ("2026-0005", "Casey", "Unverified", "casey.unverified@example.com", Profile.Role.STUDENT, "Student, NOT verified"),
    ("security.demo", "Campus", "Guard", "security.demo@example.com", Profile.Role.STAFF, "Staff, security guard"),
    ("moderator.demo", "Mika", "Moderator", "moderator.demo@example.com", Profile.Role.STAFF, "Staff, verified moderator"),
    ("findit-admin", "Find-IT", "Admin", "findit-admin@example.com", Profile.Role.ADMIN, "Administrator"),
]


def demo_photo(label, color):
    """A plain generated picture (no real photo)."""
    image = Image.new("RGB", (640, 480), (236, 242, 245))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((170, 90, 470, 390), radius=48, fill=color)
    draw.text((24, 440), f"Demo picture: {label}", fill=(23, 52, 79))
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=80)
    return ContentFile(buffer.getvalue(), name=f"demo-{label.lower().replace(' ', '-')}.jpg")


class Command(BaseCommand):
    help = "Create fictional local demo accounts and example listings. Do not use these credentials online."

    def add_arguments(self, parser):
        parser.add_argument(
            "--logins-only", action="store_true",
            help="Only (re)make the demo accounts' passwords and demo-logins.txt; no example listings.",
        )

    def handle(self, *args, **options):
        if not settings.DEBUG:
            # Demo accounts are for a local PC only. Never put them on an online (DEBUG off) site.
            raise CommandError("seed_demo only runs on a local PC (DEBUG on). It must never run on an online site.")
        users = {}
        known = demo_logins.load()
        login_rows = []
        logins_only = options.get("logins_only")
        for username, first_name, last_name, email, role, label in ACCOUNTS:
            if logins_only and not User.objects.filter(username=username).exists():
                continue  # --logins-only never adds accounts, it only gives existing demo accounts new passwords
            user, created = User.objects.get_or_create(
                username=username, defaults={"first_name": first_name, "last_name": last_name, "email": email},
            )
            password = known.get(username)
            if created or not password or not user.check_password(password):
                # New account, or one still using an old published password: give it a new random one.
                password = demo_logins.new_password()
                user.set_password(password)
                user.save(update_fields=["password"])
            login_rows.append((label, username, email, username if role == Profile.Role.STUDENT and username != "2026-0005" else "", password))
            profile, _ = Profile.objects.get_or_create(user=user)
            profile.role = role
            if role == Profile.Role.STUDENT:
                from core.models import StudentIdRecord
                profile.student_id = username
                StudentIdRecord.objects.get_or_create(user=user, student_id=username, defaults={"source": "SIGNUP"})
                if username != "2026-0005":
                    # Demo students are verified so they can sign in with their Student ID too.
                    profile.email_verified_at = profile.email_verified_at or timezone.now()
                    profile.student_id_locked = True
            # v1.1.1: the demo admin is NOT a Django superuser and cannot open /django-admin/.
            profile.save()
            users[username] = User.objects.select_related("profile").get(pk=user.pk)
            self.stdout.write(f"{'Created' if created else 'Ready'} demo account: {username} ({role})")
        if logins_only:
            path = demo_logins.save(login_rows)
            self.stdout.write(f"Demo sign-ins for this PC saved in {path.name}.")
            return

        # Session 1: an administrator-verified moderator (a Staff account with moderator authorization).
        moderator = users["moderator.demo"]
        if not ModeratorVerification.objects.filter(staff=moderator).exists():
            change_moderator_verification(moderator, users["findit-admin"], "request", "Demo moderator.")
            change_moderator_verification(moderator, users["findit-admin"], "approve", "Demo moderator.")
        alex, jamie, sam, riley = (users[k] for k in ("2026-0001", "2026-0002", "2026-0003", "2026-0004"))
        staff = users["security.demo"]
        with transaction.atomic():
            self._shared_found_post(alex, jamie, sam, riley, staff)
            self._lost_post_verification(alex, jamie)
            self._guardhouse_item(alex, sam, staff)
            self._walk_in(staff)
        path = demo_logins.save(login_rows)
        self.stdout.write(f"Demo sign-ins for this PC saved in {path.name} (FindIT.cmd menu 2 shows them).")
        self.stdout.write(self.style.WARNING(
            "Fictional accounts and example listings are for a local demo only. Never deploy with demo data enabled."
        ))

    # -- helpers -----------------------------------------------------------
    def _post(self, author, title, post_type, category_name, description, color):
        post, created = ItemPost.objects.get_or_create(
            author=author, title=title,
            defaults={
                "post_type": post_type,
                "category": Category.objects.filter(name=category_name).first(),
                "description": description,
                "approximate_date": timezone.localdate(),
            },
        )
        if created:
            PostPhoto.objects.create(post=post, image=demo_photo(title, color), order=1)
            PostStatusEvent.objects.create(post=post, previous_status="", new_status=post.status, actor=author, note="Demo listing created.")
        return post, created

    def _claim(self, post, claimant, description):
        claim = ClaimApplication.objects.create(post=post, claimant=claimant, description=description)
        for question in post.verification_questions.all():
            answer = question.choices[0] if question.choices else "A demo answer only the owner would know"
            ClaimAnswer.objects.create(claim=claim, question=question, answer_text=answer)
        create_claim_conversation(claim)
        if post.status == ItemPost.Status.OPEN:
            record_status(post, ItemPost.Status.CLAIM_IN_PROGRESS, claimant, "A private claim was submitted.", claim)
        return claim

    # -- scenarios ---------------------------------------------------------
    def _shared_found_post(self, alex, jamie, sam, riley, staff):
        post, created = self._post(
            alex, "Blue insulated bottle", ItemPost.Type.FOUND, "Water bottles & tumblers",
            "Reusable bottle with a matte blue exterior and a silver-colored lid.", (52, 104, 170),
        )
        if not created:
            return
        picks = list(QuestionTemplate.objects.filter(text__in=[
            "What kind of lid does it have?", "Describe any stickers or dents on it.",
        ]))
        apply_post_questions(post, picks)
        for user in (alex, jamie):
            PostShare.objects.get_or_create(post=post, user=user)
        ItemPost.objects.filter(pk=post.pk).update(is_shared=True, shared_at=timezone.now())
        first = self._claim(post, jamie, "Blue bottle with a dent near the bottom and a cat sticker under the lid.")
        approve_claim(first, alex)
        self._claim(post, sam, "I lost a blue bottle in the library last week.")
        third = self._claim(post, riley, "It's my bottle.")
        decline_claim(third, alex, "The lid and sticker details didn't match.")
        Comment.objects.get_or_create(
            post=post, author=staff,
            text="Keep your verification details private and arrange hand-off within school premises.",
        )

    def _lost_post_verification(self, alex, jamie):
        post, created = self._post(
            jamie, "Black folding umbrella", ItemPost.Type.LOST, "Umbrellas",
            "Compact black folding umbrella with a curved handle.", (40, 40, 48),
        )
        if not created:
            return
        conversation = create_lost_post_conversation(post, alex)
        templates = list(QuestionTemplate.objects.filter(is_default=True)[:3])
        for question in ask_chat_questions(conversation, alex, templates):
            answer = question.choices[0] if question.choices else "A small white tag on the strap"
            answer_chat_question(question, jamie, answer)

    def _guardhouse_item(self, alex, sam, staff):
        post, created = self._post(
            alex, "Gray earbuds case", ItemPost.Type.FOUND, "Electronics & gadgets",
            "Small gray earbuds charging case.", (120, 126, 134),
        )
        if not created:
            return
        apply_post_questions(post, [])
        self._claim(post, sam, "Gray case with a scratch on the hinge.")
        ticket = post.turn_in_tickets.get(finder=alex)
        ticket.requested_at = timezone.now()
        ticket.save(update_fields=["requested_at"])
        turn_over_to_guardhouse(post, staff, ticket=ticket, handed_over_by_user=alex, method=GuardhouseIntake.Method.QR)
        StatusChangeRequest.objects.create(
            post=post, requester=alex, requested_status=StatusChangeRequest.Requested.OPEN,
            reason="Demo request: the owner contacted me directly, I'd like to return it myself.",
        )

    def _walk_in(self, staff):
        post, created = self._post(
            staff, "Scientific calculator", ItemPost.Type.FOUND, "School supplies",
            "Handed in at the guard house.", (30, 30, 30),
        )
        if not created:
            return
        apply_post_questions(post, [])
        turn_over_to_guardhouse(post, staff, handed_over_by_name="Walk-in visitor (demo)", method=GuardhouseIntake.Method.WALK_IN)
