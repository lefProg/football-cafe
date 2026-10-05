from django.db.models import IntegerChoices


class VoteChoice(IntegerChoices):
    """What a reader ticks on one claim of the coupon"""

    AGREE = 1, 'Agree'
    DISAGREE = 2, 'Disagree'


class ReplyStatus(IntegerChoices):
    """Where a reader's reply stands with the moderator"""

    PENDING = 1, 'Being checked'
    PUBLISHED = 2, 'Published'
    REJECTED = 3, 'Rejected'
    REVIEW = 4, 'Waiting for the house'
