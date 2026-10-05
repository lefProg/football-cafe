from datetime import timedelta

from django.db.models import Count, Manager, Q, QuerySet
from django.utils import timezone

from core.enums import ReplyStatus, VoteChoice


class ArticleQuerySet(QuerySet):
    """Overrides the Article QuerySet"""

    def published(self) -> QuerySet:
        """Pieces the public can read: they have a publish date and it has passed"""
        return self.filter(published_at__isnull=False, published_at__lte=timezone.now())

    def with_reply_count(self) -> QuerySet:
        """Adds `reply_count`, the number of published replies. Newest first."""
        # Grouping for the count drops the model's default ordering, so it is named again here.
        return self.annotate(reply_count=Count('replies', filter=Q(replies__status=ReplyStatus.PUBLISHED))).order_by(
            '-published_at', '-id'
        )


class ArticleManager(Manager):
    """Overrides the Article Manager"""

    def get_queryset(self):
        return ArticleQuerySet(self.model, using=self._db)

    def published(self) -> QuerySet:
        return self.get_queryset().published()


class ClaimQuerySet(QuerySet):
    """Overrides the Claim QuerySet"""

    def with_tally(self) -> QuerySet:
        """Adds `vote_count` and `agree_count`"""
        return self.annotate(
            vote_count=Count('votes'),
            agree_count=Count('votes', filter=Q(votes__choice=VoteChoice.AGREE)),
        )


class ClaimManager(Manager):
    """Overrides the Claim Manager"""

    def get_queryset(self):
        return ClaimQuerySet(self.model, using=self._db)

    def with_tally(self) -> QuerySet:
        return self.get_queryset().with_tally()


class ReplyQuerySet(QuerySet):
    """Overrides the Reply QuerySet"""

    def published(self) -> QuerySet:
        """Replies the moderator or the house let through"""
        return self.filter(status=ReplyStatus.PUBLISHED)

    def waiting_for_the_house(self) -> QuerySet:
        """Replies the moderator could not decide on"""
        return self.filter(status=ReplyStatus.REVIEW)

    def recent_by(self, visitor, seconds: int) -> QuerySet:
        """Everything one visitor posted in the last `seconds`, whatever became of it"""
        return self.filter(visitor=visitor, created_at__gte=timezone.now() - timedelta(seconds=seconds))


class ReplyManager(Manager):
    """Overrides the Reply Manager"""

    def get_queryset(self):
        return ReplyQuerySet(self.model, using=self._db)

    def published(self) -> QuerySet:
        return self.get_queryset().published()

    def waiting_for_the_house(self) -> QuerySet:
        return self.get_queryset().waiting_for_the_house()

    def recent_by(self, visitor, seconds: int) -> QuerySet:
        return self.get_queryset().recent_by(visitor, seconds)
