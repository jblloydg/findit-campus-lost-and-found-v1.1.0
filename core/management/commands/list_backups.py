from django.core.management.base import BaseCommand

from core.backup import status_summary


class Command(BaseCommand):
    help = "Show backup status, available backups, and the retention policy."

    def handle(self, *args, **options):
        info = status_summary()
        self.stdout.write(f"Database engine: {info['engine']}")
        self.stdout.write(f"Backup folder:   {info['backup_dir']}")
        self.stdout.write(f"Retention:       {info['retention_days']} days, always keep newest {info['min_keep']}")
        for label, entry in (("Last attempt", info["last_attempt"]), ("Last success", info["last_success"])):
            text = f"{entry['time']} {entry['status']} {entry.get('file', '')} {entry.get('message', '')}" if entry else "none"
            self.stdout.write(f"{label + ':':16} {text}")
        self.stdout.write(f"\n{len(info['backups'])} backup file(s):")
        for item in info["backups"]:
            state = {True: "ok", False: "CHECKSUM MISMATCH", None: "no checksum"}[item.checksum_ok]
            self.stdout.write(f"  {item.name:48} {item.size / 1024:9.1f} KB  {item.kind:11} {state}")
