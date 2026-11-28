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


# v2.0.0 example accounts made by _verification_examples (no Student ID sign-in: not verified).
EXTRA_LOGINS = (
    ("2026-0016", "Student, red-flagged (disabled)"),
    ("2026-0017", "Student, NOT verified, ID conflict"),
)


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
        testers = self._tester_accounts(login_rows)
        if logins_only:
            for username, label in EXTRA_LOGINS:
                extra = User.objects.filter(username=username).first()
                if extra:
                    self._demo_login(extra, known, login_rows, label, created=False)
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
            self._verification_examples(riley, known, login_rows)
            self._tester_chats(testers)
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

    def _demo_login(self, user, known, login_rows, label, created):
        """v2.0.0 + CHG-008: the v2 example accounts get a random per-PC password like every demo account."""
        password = known.get(user.username)
        if created or not password or not user.check_password(password):
            password = demo_logins.new_password()
            user.set_password(password)
            user.save(update_fields=["password"])
        login_rows.append((label, user.username, user.email, "", password))

    def _verification_examples(self, riley, known, login_rows):
        """v2.0.0: examples so the red-flag list, ID conflict and ID review screens have something to show.

        - Drew used three different Student IDs, so the account is red-flagged and disabled (decision 12).
        - Morgan (not verified) typed Riley's Student ID; Riley verified first, so Morgan has 14 days
          before the ID is cleared, and Morgan asked for an ID review (which Morgan can withdraw).
        """
        from datetime import timedelta
        from core.models import IdReviewCase, StudentIdRecord
        drew, created = User.objects.get_or_create(
            username="2026-0016", defaults={"first_name": "Drew", "last_name": "Flagged", "email": "drew.flagged@example.com"},
        )
        self._demo_login(drew, known, login_rows, dict(EXTRA_LOGINS)[drew.username], created)
        if created:
            drew.is_active = False
            drew.save(update_fields=["is_active"])
            profile, _ = Profile.objects.get_or_create(user=drew)
            for student_id in ("2026-0016", "2026-0026", "2026-0036"):
                StudentIdRecord.objects.get_or_create(user=drew, student_id=student_id, defaults={"source": "CHANGE"})
            profile.student_id = "2026-0036"
            profile.flagged_at = timezone.now()
            profile.flag_reason = "Used 3 different Student IDs (demo)."
            profile.save()
            self.stdout.write("Created demo account: 2026-0016 (red-flagged, inactive)")
        morgan, created = User.objects.get_or_create(
            username="2026-0017", defaults={"first_name": "Morgan", "last_name": "Shared", "email": "morgan.shared@example.com"},
        )
        self._demo_login(morgan, known, login_rows, dict(EXTRA_LOGINS)[morgan.username], created)
        if created:
            profile, _ = Profile.objects.get_or_create(user=morgan)
            shared_id = riley.profile.student_id
            StudentIdRecord.objects.get_or_create(user=morgan, student_id=shared_id, defaults={"source": "SIGNUP"})
            profile.student_id = shared_id
            profile.id_conflict_deadline = timezone.now() + timedelta(days=14)
            profile.save()
            IdReviewCase.objects.create(
                kind=IdReviewCase.Kind.IMPOSTOR, requester=morgan, student_id=shared_id, holder=riley,
                message="Demo: I think this Student ID is mine; the verified account is not me.",
            )
            self.stdout.write("Created demo account: morgan.shared@example.com (ID conflict + open ID review)")

    def _tester_accounts(self, login_rows):
        """CHG-014: the owner's tester accounts from tester-accounts.txt (private copy only; none without it).
        Their passwords are fixed in that file, so they are the same on every PC that has it."""
        from core.models import StudentIdRecord
        made = {}
        for row in demo_logins.tester_accounts():
            user, created = User.objects.get_or_create(
                username=row["username"],
                defaults={"first_name": row["first_name"], "last_name": row["last_name"], "email": row["email"]},
            )
            if created or not user.check_password(row["password"]):
                user.set_password(row["password"])
                user.save(update_fields=["password"])
            profile, _ = Profile.objects.get_or_create(user=user)
            profile.role = Profile.Role.STUDENT
            profile.student_id = row["username"]
            profile.email_verified_at = profile.email_verified_at or timezone.now()
            profile.student_id_locked = True
            profile.save()
            StudentIdRecord.objects.get_or_create(user=user, student_id=row["username"], defaults={"source": "SIGNUP"})
            login_rows.append((f"Tester, posted {row['posts']} (verified)", user.username, user.email, user.username, row["password"]))
            made.setdefault(row["posts"], user)
            self.stdout.write(f"{'Created' if created else 'Ready'} tester account ({row['posts']})")
        return made

    def _tester_chats(self, testers):
        """CHG-014: one tester found something, the other lost something, and they chat on both posts.

        - The LOST tester messaged the FOUND tester's post ("Message poster"): the FOUND tester is the finder.
        - The FOUND tester messaged the LOST tester's post ("I found this – message the owner"): the
          FOUND tester is the finder there too and can send ownership questions from the chat's ＋ menu.
        """
        if "FOUND" not in testers or "LOST" not in testers:
            return
        from core.models import ChatMessage
        finder, owner = testers["FOUND"], testers["LOST"]
        found, created_found = self._post(
            finder, "Gray backpack with keychain", ItemPost.Type.FOUND, "Bags & backpacks",
            "Gray backpack found near the covered walk. Has a small keychain on the zipper.", (110, 116, 122),
        )
        if created_found:
            apply_post_questions(found, [])
        lost, _ = self._post(
            owner, "Silver USB flash drive", ItemPost.Type.LOST, "Electronics & gadgets",
            "Lost a small silver USB flash drive, probably in the computer laboratory.", (170, 174, 180),
        )
        chat_on_found = create_lost_post_conversation(found, owner)
        chat_on_lost = create_lost_post_conversation(lost, finder)
        if not chat_on_found.messages.exists():
            for sender, text in (
                (owner, "Hi! I think this might be my backpack. Where did you find it?"),
                (finder, "Hello! Near the covered walk this morning. Can you describe the keychain?"),
            ):
                ChatMessage.objects.create(conversation=chat_on_found, sender=sender, text=text)
        if not chat_on_lost.messages.exists():
            for sender, text in (
                (finder, "Hi, I found a silver flash drive in the computer lab. It could be yours."),
                (owner, "That would be great! What should I do to show it's mine?"),
            ):
                ChatMessage.objects.create(conversation=chat_on_lost, sender=sender, text=text)

    def _walk_in(self, staff):
        post, created = self._post(
            staff, "Scientific calculator", ItemPost.Type.FOUND, "School supplies",
            "Handed in at the guard house.", (30, 30, 30),
        )
        if not created:
            return
        apply_post_questions(post, [])
        turn_over_to_guardhouse(post, staff, handed_over_by_name="Walk-in visitor (demo)", method=GuardhouseIntake.Method.WALK_IN)
