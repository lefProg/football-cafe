import random
import uuid

from django.core.management.base import BaseCommand
from django.utils import timezone

from core.enums import ReplyStatus, VoteChoice
from core.models import Argument, Article, Reply, Vote

BODY = """\
Ask anyone why the classic playmaker vanished and you will hear the same answer: the press ate him. No space between the lines, no time on the ball, no room for a man who walks.

I don't buy it. Space still opens up, every single match. What changed is who is allowed to stand in it. A coach who picks a 10 is betting on one player's ideas. A coach who picks a third runner is buying insurance. Most of them buy insurance.

## The insurance policy

Watch any big match and count the players allowed to lose the ball trying something. It is usually one, sometimes none. The rest are there to keep the shape. That is a choice, and it is made on the training ground long before the press arrives.

> A 10 is a bet on one player's ideas. A third runner is insurance.

The next great team will be the one whose coach tears up the policy."""

CLAIMS = [
    ("Pressing didn't kill the No. 10. Cautious coaching did.", 62),
    ('A great 10 is worth one lost duel in midfield.', 48),
    ('Academies coach the risk out of creative kids.', 81),
    ('The false nine was a 10 in disguise.', 57),
    ('The next great team will be built around one.', 39),
]

ARGUMENTS = [
    (
        'The space is gone, not the trust.',
        'Teams now defend in a block barely 25 metres deep. Between the lines there is nowhere left for a 10 to stand still.',
        "Fair, the block is tighter than it used to be. But tight isn't closed. The gap opens for a second after every switch of play, and somebody has to be standing there who wants the ball. That is a choice of player, and coaches make it.",
        [
            (
                'kopite_nikos',
                'Come on. Teams defend in a 25 metre block now. There is no space between the lines for a 10 to stand in, it has nothing to do with trust.',
            ),
            (
                'Stavros',
                "You can't walk around behind the strikers any more, the lines are too compact. The space he lived in does not exist.",
            ),
            (
                'old_trafford_al',
                'Watch any mid-table side out of possession. Two banks of four, ten metres apart. Where exactly does your playmaker stand?',
            ),
        ],
    ),
    (
        "He didn't die, he moved.",
        'The playmaker now starts as an 8 or drifts in from the wing. Same brain, different postcode.',
        '',
        [
            (
                'Marta',
                'The 10 is still there, he just starts deeper as an 8 or comes in off the wing. Same player, different position on the teamsheet.',
            ),
            ('fabio_calcio', 'Every top side has a creator. He is called a left-sided 8 now. Nothing died.'),
        ],
    ),
    (
        'One passenger costs you the midfield.',
        "Pick a 10 who doesn't run and you are two against three in the middle every time the ball is lost.",
        '',
        [
            (
                'dimi_7',
                "If your 10 doesn't run you are 2 v 3 in midfield every time you lose it. No coach can afford that, it's maths not cowardice.",
            ),
        ],
    ),
]


class Command(BaseCommand):
    help = 'Fill the cafe with one sample piece, votes, replies and arguments, so there is something to look at.'

    def handle(self, *args, **options):
        if Article.objects.filter(slug='the-no-10-never-died').exists():
            self.stdout.write('The sample piece is already there. Nothing to do.')
            return
        article = Article.objects.create(
            title='The No. 10 never died. Coaches just stopped trusting him.',
            slug='the-no-10-never-died',
            standfirst='Everyone blames the press for killing the playmaker. The truth is simpler, and less flattering for the men on the touchline.',
            body=BODY,
            reading_minutes=8,
            published_at=timezone.now(),
        )
        rng = random.Random(10)
        visitors = [uuid.uuid4() for _ in range(60)]
        for position, (text, percent) in enumerate(CLAIMS, start=1):
            claim = article.claims.create(position=position, text=text)
            agreeing = set(rng.sample(range(len(visitors)), round(len(visitors) * percent / 100)))
            Vote.objects.bulk_create(
                Vote(
                    claim=claim, visitor=visitor, choice=VoteChoice.AGREE if index in agreeing else VoteChoice.DISAGREE
                )
                for index, visitor in enumerate(visitors)
            )
        for title, summary, house_reply, replies in ARGUMENTS:
            argument = Argument.objects.create(
                article=article,
                claim=article.claims.get(position=1),
                title=title,
                summary=summary,
                house_reply=house_reply,
            )
            for nickname, text in replies:
                argument.replies.add(
                    Reply.objects.create(
                        article=article,
                        visitor=uuid.uuid4(),
                        nickname=nickname,
                        text=text,
                        status=ReplyStatus.PUBLISHED,
                    )
                )
        Reply.objects.create(
            article=article,
            visitor=uuid.uuid4(),
            nickname='quiet_one',
            text='Honestly I think the house has this one right. Nothing to add.',
            status=ReplyStatus.PUBLISHED,
        )
        self.stdout.write(self.style.SUCCESS('Sample piece added.'))
