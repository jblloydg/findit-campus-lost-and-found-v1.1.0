from django.core.management.base import BaseCommand, CommandError

from core.backup import BackupError, engine, resolve_backup_path, restore_backup, validate_backup_file, write_log


class Command(BaseCommand):
    help = (
        "Restore the database from a Find-IT backup. The current database is backed up first. "
        "Stop the website and the timer runner before restoring."
    )

    def add_arguments(self, parser):
        parser.add_argument("backup", help="Backup file name in the backup folder, or a full path.")
        parser.add_argument("--yes", action="store_true",
                            help="Skip the typed confirmation (for scripted, supervised use only).")
        parser.add_argument("--check-only", action="store_true", help="Only validate the backup; change nothing.")

    def handle(self, *args, **options):
        path = resolve_backup_path(options["backup"])
        try:
            validate_backup_file(path, expected_engine=engine())
        except BackupError as exc:
            write_log("restore", "failed", f"Validation failed: {exc}", file=path.name)
            raise CommandError(f"Restore refused: {exc}") from exc
        self.stdout.write(self.style.SUCCESS(f"Backup is valid: {path.name}"))
        if options["check_only"]:
            return
        if not options["yes"]:
            if not options.get("interactive", True) or not self.stdin_is_interactive():
                raise CommandError("Restore needs confirmation. Run it in a terminal, or add --yes.")
            self.stdout.write(self.style.WARNING(
                "This REPLACES all current Find-IT data with the contents of this backup.\n"
                "A safety copy of the current database is made first.\n"
                "Make sure the website and timer runner are stopped."
            ))
            answer = input(f'Type RESTORE to continue: ')
            if answer.strip() != "RESTORE":
                raise CommandError("Restore cancelled. Nothing was changed.")
        try:
            safety = restore_backup(path)
        except BackupError as exc:
            raise CommandError(f"Restore FAILED: {exc}") from exc
        if safety:
            self.stdout.write(f"Safety copy of the previous database: {safety.name}")
        self.stdout.write(self.style.SUCCESS(f"Restore complete from {path.name}."))
        self.stdout.write("Next: run 'python manage.py migrate' (in case the backup is from an older version), then start the site.")

    @staticmethod
    def stdin_is_interactive():
        import sys
        return sys.stdin.isatty()
