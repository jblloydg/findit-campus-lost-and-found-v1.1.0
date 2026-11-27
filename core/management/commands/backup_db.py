from django.core.management.base import BaseCommand, CommandError

from core.backup import BackupError, apply_retention, create_backup


class Command(BaseCommand):
    help = "Create a validated, date-stamped database backup, then apply the retention policy."

    def add_arguments(self, parser):
        parser.add_argument("--kind", choices=["daily", "manual"], default="manual",
                            help="Label in the file name. The scheduled task uses --kind daily.")
        parser.add_argument("--no-prune", action="store_true", help="Skip the retention clean-up after the backup.")

    def handle(self, *args, **options):
        try:
            path = create_backup(options["kind"])
        except BackupError as exc:
            # A non-zero exit code lets Task Scheduler / cron report the failure.
            raise CommandError(f"Backup FAILED: {exc}") from exc
        self.stdout.write(self.style.SUCCESS(f"Backup created and validated: {path}"))
        if not options["no_prune"]:
            deleted = apply_retention()
            if deleted:
                self.stdout.write(f"Retention removed {len(deleted)} expired backup(s): {', '.join(deleted)}")
            else:
                self.stdout.write("Retention: nothing to remove.")
