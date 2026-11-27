from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import Comment, ItemPost, PostStatusEvent, Profile, VerificationQuestion

User = get_user_model()


class Command(BaseCommand):
    help = "Create fictional local demo accounts. Do not use these credentials online."

    def handle(self, *args, **options):
        # Fictional people with reserved example.com addresses (RFC 2606) — never real students.
        accounts = [
            ("2026-0001", "Alex", "Finder", "alex.finder@example.com", Profile.Role.STUDENT, "DemoFindIt!2026"),
            ("2026-0002", "Jamie", "Claimant", "jamie.claimant@example.com", Profile.Role.STUDENT, "DemoFindIt!2026"),
            ("security.demo", "Campus", "Staff", "security.demo@example.com", Profile.Role.STAFF, "DemoStaff!2026"),
            ("findit-admin", "Find-IT", "Admin", "findit-admin@example.com", Profile.Role.ADMIN, "DemoAdmin!2026"),
        ]
        for username, first_name, last_name, email, role, password in accounts:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={"first_name": first_name, "last_name": last_name, "email": email},
            )
            if created:
                user.set_password(password)
                user.save(update_fields=["password"])
            profile, _ = Profile.objects.get_or_create(user=user)
            profile.role = role
            if role == Profile.Role.STUDENT:
                profile.student_id = username
            if role == Profile.Role.ADMIN:
                user.is_staff = True
                user.is_superuser = True
                user.save(update_fields=["is_staff", "is_superuser"])
            profile.save()
            self.stdout.write(f"{'Created' if created else 'Ready'} demo account: {username} ({role})")
        finder = User.objects.get(username="2026-0001")
        found_post, found_created = ItemPost.objects.get_or_create(
            author=finder,
            title="Blue insulated bottle",
            defaults={
                "post_type": ItemPost.Type.FOUND,
                "category": ItemPost.Category.BOTTLE,
                "location": "Library 2nd floor",
                "description": "Reusable bottle with a matte blue exterior and a silver-colored lid. The owner should know a few details not shown in this broad description.",
                "approximate_date": timezone.localdate(),
            },
        )
        if found_created:
            PostStatusEvent.objects.create(
                post=found_post,
                previous_status="",
                new_status=found_post.status,
                actor=finder,
                note="Demo found listing created.",
            )
        questions = [
            "What color or mark is on the underside?",
            "What detail is on the inside of the lid?",
            "Describe one small mark that is not in this listing.",
            "What did you usually carry with this bottle?",
            "What is one detail about its cap or seal?",
        ]
        for order, text in enumerate(questions, start=1):
            VerificationQuestion.objects.get_or_create(post=found_post, order=order, defaults={"text": text})
        lost_post, lost_created = ItemPost.objects.get_or_create(
            author=User.objects.get(username="2026-0002"),
            title="Black folding umbrella",
            defaults={
                "post_type": ItemPost.Type.LOST,
                "category": ItemPost.Category.UMBRELLA,
                "location": "Canteen",
                "description": "Compact black folding umbrella with a curved handle. If you found something similar, message the poster privately.",
                "approximate_date": timezone.localdate(),
            },
        )
        if lost_created:
            PostStatusEvent.objects.create(
                post=lost_post,
                previous_status="",
                new_status=lost_post.status,
                actor=lost_post.author,
                note="Demo lost listing created.",
            )
        Comment.objects.get_or_create(
            post=found_post,
            author=User.objects.get(username="security.demo"),
            text="Keep your verification details private and arrange hand-off within school premises.",
        )
        self.stdout.write(self.style.WARNING(
            "Fictional accounts and example listings are for a local demo only. Never deploy with demo data enabled."
        ))
