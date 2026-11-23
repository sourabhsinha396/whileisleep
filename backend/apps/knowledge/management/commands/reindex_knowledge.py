from django.core.management.base import BaseCommand

from apps.knowledge.indexing import reindex_all


class Command(BaseCommand):
    help = "Rebuilds the search passages of every article (after changing SEARCH_LANGUAGE)."

    def handle(self, *args, **options):
        self.stdout.write(f"Indexed {reindex_all()} articles.")
