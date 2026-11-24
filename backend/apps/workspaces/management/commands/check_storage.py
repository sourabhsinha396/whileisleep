import uuid

import httpx
from botocore.exceptions import BotoCoreError, ClientError
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError
from storages.backends.s3 import S3Storage

# OSError: django-storages reports a missing file as FileNotFoundError.
FAILURES = (BotoCoreError, ClientError, OSError)


class Command(BaseCommand):
    help = "Checks the file storage settings: writes a small file, opens its public address, deletes it."

    def handle(self, *args, **options):
        if not isinstance(default_storage, S3Storage):
            raise CommandError("No bucket is configured: the S3_* and STORAGE_* settings are empty.")
        content = uuid.uuid4().hex
        try:
            name = default_storage.save(f"storage-check/{content}.txt", ContentFile(content.encode()))
        except FAILURES as error:
            raise CommandError(f"Can't write to the bucket: {error}") from error
        self.stdout.write("Write: OK")
        try:
            self.check_readable(name, content)
        finally:
            try:
                default_storage.delete(name)
            except FAILURES as error:
                raise CommandError(f"Can't delete from the bucket, so {name} is still there: {error}") from error
        self.stdout.write("Delete: OK")
        self.stdout.write(self.style.SUCCESS("File storage works."))

    def check_readable(self, name: str, content: str):
        try:
            with default_storage.open(name) as file:
                read = file.read().decode()
        except FAILURES as error:
            raise CommandError(f"Can't read from the bucket: {error}") from error
        if read != content:
            raise CommandError("The bucket returned something other than what was written.")
        self.stdout.write("Read: OK")

        url = default_storage.url(name)
        try:
            response = httpx.get(url, timeout=20)
        except httpx.HTTPError as error:
            raise CommandError(f"Can't open {url}: {error}") from error
        if response.status_code != 200 or response.text != content:
            raise CommandError(
                f"{url} answered {response.status_code} instead of the file. "
                "Is STORAGE_PUBLIC_BASE_URL the bucket's public address?"
            )
        self.stdout.write("Public address: OK")
