import hashlib
import logging
import uuid

from django.conf import settings
from django.core.cache import cache

from core.agents import moderator
from core.enums import ReplyStatus, VoteChoice
from core.models import Reply, Vote

logger = logging.getLogger(__name__)

NICKNAME_MIN, NICKNAME_MAX = 2, 30
TEXT_MIN, TEXT_MAX = 15, 1200


# ---------- visitors ----------


def get_visitor(request):
    """The anonymous id in the visitor's signed cookie, or None if they have none yet."""
    raw = request.get_signed_cookie(settings.CAFE_VISITOR_COOKIE, default=None)
    try:
        return uuid.UUID(raw) if raw else None
    except ValueError:
        return None


def remember_visitor(response, visitor) -> None:
    response.set_signed_cookie(
        settings.CAFE_VISITOR_COOKIE,
        str(visitor),
        max_age=settings.CAFE_VISITOR_COOKIE_AGE,
        httponly=True,
        samesite='Lax',
        secure=settings.HTTPS,
    )


# ---------- the coupon ----------


def coupon_state(article, visitor) -> dict:
    """Each claim with the visitor's tick, plus the split once they have ticked it."""
    claims = list(article.claims.all())
    mine = {}
    if visitor:
        mine = dict(Vote.objects.filter(claim__in=claims, visitor=visitor).values_list('claim_id', 'choice'))
    rows = []
    for claim in claims:
        choice = mine.get(claim.id)
        row = {
            'claim': claim,
            'mine': choice,
            'percent': None,
            'total': 0,
            'agreed': choice == VoteChoice.AGREE,
            'disagreed': choice == VoteChoice.DISAGREE,
        }
        # The split stays hidden until the reader has ticked, so nobody votes with the crowd.
        if choice is not None:
            row['percent'], row['total'] = claim.tally()
        rows.append(row)
    ticked = sum(row['mine'] is not None for row in rows)
    return {
        'rows': rows,
        'ticked': ticked,
        'total': len(rows),
        'verdict': verdict(rows) if rows and ticked == len(rows) else '',
    }


def verdict(rows) -> str:
    """What the reader hears when the whole coupon is ticked. The claims are the house's, so agreeing is siding with it."""
    with_house = sum(row['agreed'] for row in rows)
    text = f'You are with the house on {with_house} of {len(rows)}.'
    split = min(rows, key=lambda row: abs(row['percent'] - 50))
    return f'{text} The cafe is most divided on claim {split["claim"].position}: {split["percent"]}% agree.'


def cast_vote(claim, visitor, choice) -> None:
    Vote.objects.update_or_create(claim=claim, visitor=visitor, defaults={'choice': choice})


# ---------- replies ----------


class RepliesClosed(Exception):
    """The piece takes no more replies."""


class TooManyReplies(Exception):
    """This visitor or address posted too much, too fast."""


def _ip_key(ip: str) -> str:
    return 'fc-replies-' + hashlib.sha256(ip.encode()).hexdigest()[:24]


def _check_limits(visitor, ip: str) -> None:
    by_visitor = Reply.objects.recent_by(visitor, settings.CAFE_REPLY_WINDOW_SECONDS).count()
    by_ip = cache.get(_ip_key(ip), 0) if ip else 0
    if by_visitor >= settings.CAFE_REPLY_LIMIT or by_ip >= settings.CAFE_REPLY_LIMIT_PER_IP:
        raise TooManyReplies('You have posted a few replies in a row. Give it ten minutes, then come back.')


def _count_for_ip(ip: str) -> None:
    if not ip:
        return
    key = _ip_key(ip)
    # Only a hash of the address is kept, and it expires with the window.
    cache.add(key, 0, settings.CAFE_REPLY_WINDOW_SECONDS)
    cache.incr(key)


def submit_reply(article, visitor, nickname: str, text: str, ip: str = '') -> Reply:
    """Store one reply that already passed the serializer, and let the moderator decide on it."""
    if not article.replies_open:
        raise RepliesClosed('Replies to this piece are closed.')
    _check_limits(visitor, ip)

    reply = Reply.objects.create(article=article, visitor=visitor, nickname=nickname, text=text)
    _count_for_ip(ip)
    try:
        result = moderator.review(article, nickname, text)
    except moderator.ModeratorUnavailable as error:
        # No moderator, no automatic publishing: the house reads it instead.
        logger.warning('Moderator unavailable for reply %s: %s', reply.id, error)
        reply.status, reply.moderation_note = ReplyStatus.REVIEW, f'Moderator unavailable: {error}'[:300]
    else:
        reply.status = {
            moderator.PUBLISH: ReplyStatus.PUBLISHED,
            moderator.REJECT: ReplyStatus.REJECTED,
        }.get(result.decision, ReplyStatus.REVIEW)
        reply.moderation_note = result.reason
    reply.save(update_fields=['status', 'moderation_note'])
    return reply


WAITING_MESSAGE = 'Thanks. The house will read your reply before it goes up.'


def reader_message(reply) -> str:
    if reply.status == ReplyStatus.PUBLISHED:
        return 'Your reply is up.'
    if reply.status == ReplyStatus.REJECTED:
        reason = reply.moderation_note or 'It breaks the house rules.'
        return f'Not published. {reason} You can rewrite it and post again.'
    return WAITING_MESSAGE
