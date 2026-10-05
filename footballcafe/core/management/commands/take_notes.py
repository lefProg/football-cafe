from django.core.management.base import BaseCommand, CommandError

from core.agents import notetaker
from core.models import Article


class Command(BaseCommand):
    help = 'Ask the note-taker agent to sum up the published replies to one piece.'

    def add_arguments(self, parser):
        parser.add_argument('slug', help="The piece's slug, as in its web address.")

    def handle(self, *args, slug, **options):
        try:
            article = Article.objects.get(slug=slug)
        except Article.DoesNotExist:
            raise CommandError(f"There is no piece with the slug '{slug}'.")
        try:
            count = notetaker.take_notes(article)
        except notetaker.NoteTakerError as error:
            raise CommandError(str(error))
        self.stdout.write(
            self.style.SUCCESS(f'{article}: {count} argument{"" if count == 1 else "s"} on the page now.')
        )
