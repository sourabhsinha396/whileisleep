from django.core.management.base import BaseCommand

from whileisleep import encryption


class Command(BaseCommand):
    help = "Prints a new key for ENCRYPTION_KEYS (secrets stored in the database)."

    def handle(self, *args, **options):
        self.stdout.write(encryption.new_key())
