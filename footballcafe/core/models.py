import uuid as uuid_lib

from django.db import models
from django.urls import reverse
from django.utils import timezone

from core.enums import ReplyStatus, VoteChoice
from core.managers import ArticleManager, ClaimManager, ReplyManager


class Article(models.Model):
    """One piece by the house. It goes public once `published_at` has passed."""

    title = models.CharField(max_length=160, help_text='The headline. It is shown in capitals.')
    slug = models.SlugField(
        max_length=80,
        unique=True,
        help_text='The last part of the web address. Filled in from the headline; avoid changing it after '
        'publishing, or old links break.',
    )
    standfirst = models.TextField(help_text='The one or two sentences under the headline.')
    body = models.TextField(
        help_text='The piece itself, in Markdown. A blank line starts a new paragraph, "## " a heading, '
        '"> " a pull quote, **bold**, *italic*, [link text](https://address).'
    )
    reading_minutes = models.PositiveSmallIntegerField(default=5, help_text='Shown next to the byline.')
    published_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Empty: a draft only you can see. A time in the future: goes live by itself then.',
    )
    replies_open = models.BooleanField(default=True, help_text='Untick to stop new replies to this piece.')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ArticleManager()

    class Meta:
        ordering = ['-published_at', '-id']
        verbose_name = 'piece'

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse('article', args=[self.slug])

    @property
    def is_published(self) -> bool:
        return self.published_at is not None and self.published_at <= timezone.now()

    @property
    def round_number(self) -> int:
        """Round 1 is the piece; round 2 starts once the house has answered back."""
        return 2 if self.arguments.exclude(house_reply='').exists() else 1


class Claim(models.Model):
    """One of the few statements a piece stands on. Readers agree or disagree with each."""

    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name='claims')
    position = models.PositiveSmallIntegerField(help_text='Order on the coupon: 1, 2, 3…')
    text = models.CharField(max_length=200, help_text='One sentence a reader can agree or disagree with.')

    objects = ClaimManager()

    class Meta:
        ordering = ['position']
        constraints = [
            models.UniqueConstraint(fields=['article', 'position'], name='one_claim_per_position'),
        ]

    def __str__(self):
        return f'{self.position}. {self.text}'

    def tally(self) -> tuple:
        """(percent who agree, total votes). The percent is None before the first vote."""
        counts = self.votes.aggregate(
            total=models.Count('id'), agree=models.Count('id', filter=models.Q(choice=VoteChoice.AGREE))
        )
        if not counts['total']:
            return None, 0
        return round(100 * counts['agree'] / counts['total']), counts['total']


class Vote(models.Model):
    """One visitor's tick on one claim. A visitor is the random id in their cookie."""

    claim = models.ForeignKey(Claim, on_delete=models.CASCADE, related_name='votes')
    visitor = models.UUIDField()
    choice = models.PositiveSmallIntegerField(choices=VoteChoice.choices)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['claim', 'visitor'], name='one_vote_per_visitor'),
        ]


class Reply(models.Model):
    """What one reader wrote back to a piece, and what the moderator made of it."""

    uuid = models.UUIDField(default=uuid_lib.uuid4, unique=True, editable=False)
    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name='replies')
    visitor = models.UUIDField()
    nickname = models.CharField(max_length=30)
    text = models.TextField(max_length=1200)
    status = models.PositiveSmallIntegerField(choices=ReplyStatus.choices, default=ReplyStatus.PENDING)
    moderation_note = models.CharField(
        max_length=300, blank=True, help_text='Why the moderator rejected it or passed it to the house.'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ReplyManager()

    class Meta:
        ordering = ['created_at', 'id']
        verbose_name_plural = 'replies'

    def __str__(self):
        return f'{self.nickname}: {self.text[:60]}'


class Argument(models.Model):
    """One counter-argument the readers make, summed up from their replies by the note-taker."""

    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name='arguments')
    claim = models.ForeignKey(
        Claim,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='arguments',
        help_text='The claim it argues against. Empty: against the piece as a whole.',
    )
    title = models.CharField(max_length=120)
    summary = models.TextField()
    replies = models.ManyToManyField(Reply, related_name='arguments', blank=True)
    house_reply = models.TextField(blank=True, help_text='Your answer to this argument. Shown on the piece.')
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    def published_replies(self):
        return self.replies.filter(status=ReplyStatus.PUBLISHED)

    def supporter_count(self) -> int:
        """Readers behind this argument. One person counts once, however often they replied."""
        return self.published_replies().values('visitor').distinct().count()

    def first_raised_by(self) -> str:
        first = self.published_replies().order_by('created_at', 'id').first()
        return first.nickname if first else ''
