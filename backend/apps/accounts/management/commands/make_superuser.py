from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Makes an account that already exists a superuser: it can edit the docs' videos and use /admin/."

    def add_arguments(self, parser):
        parser.add_argument("email")

    def handle(self, *args, email, **options):
        user = get_user_model().objects.filter(username=email.strip().lower()).first()
        if user is None:
            raise CommandError("No account with that email. Sign up with it first.")
        user.is_staff = user.is_superuser = True
        user.save(update_fields=["is_staff", "is_superuser"])
        self.stdout.write(f"{user.email} is a superuser now.")
