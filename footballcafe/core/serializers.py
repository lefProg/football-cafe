from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from core import services
from core.enums import ReplyStatus, VoteChoice
from core.models import Argument, Article, Reply
from core.templatetags.core_extras import markdown


class PieceListSerializer(serializers.ModelSerializer):
    """A piece as it appears in a list"""

    reply_count = serializers.IntegerField(read_only=True, help_text='Published replies.')

    class Meta:
        model = Article
        fields = ['slug', 'title', 'standfirst', 'reading_minutes', 'published_at', 'replies_open', 'reply_count']


class ClaimSerializer(serializers.Serializer):
    """One claim on the coupon, with this reader's tick"""

    position = serializers.IntegerField(source='claim.position', help_text='Its number on the coupon, from 1.')
    text = serializers.CharField(source='claim.text')
    my_choice = serializers.ChoiceField(
        choices=VoteChoice.choices,
        source='mine',
        allow_null=True,
        help_text='What this reader ticked. Null: not ticked yet.',
    )
    percent_agree = serializers.IntegerField(
        source='percent',
        allow_null=True,
        help_text='Share of all readers who agree, 0 to 100. Null until this reader has ticked the claim.',
    )
    vote_count = serializers.IntegerField(
        source='total', help_text='Votes on the claim. 0 until this reader has ticked the claim.'
    )


class CouponSerializer(serializers.Serializer):
    """How far this reader is through the coupon"""

    ticked = serializers.IntegerField(help_text='Claims this reader has ticked.')
    total = serializers.IntegerField(help_text='Claims on the coupon.')
    verdict = serializers.CharField(
        allow_blank=True, help_text='One sentence for the reader. Empty until every claim is ticked.'
    )


class ArgumentSerializer(serializers.ModelSerializer):
    """One argument the readers make against the piece, summed up from their replies"""

    claim_position = serializers.IntegerField(
        source='claim.position',
        allow_null=True,
        default=None,
        help_text='The claim it argues against. Null: against the piece as a whole.',
    )
    supporter_count = serializers.IntegerField(help_text='Different readers whose replies make this argument.')
    first_raised_by = serializers.CharField(help_text='Nickname on the earliest of those replies.')
    house_reply = serializers.CharField(help_text="The writer's answer. Empty: not answered yet.")

    class Meta:
        model = Argument
        fields = ['id', 'claim_position', 'title', 'summary', 'supporter_count', 'first_raised_by', 'house_reply']


class PieceDetailSerializer(serializers.ModelSerializer):
    """A whole piece: the text, its coupon for this reader, and the arguments against it"""

    body = serializers.CharField(help_text='The piece as the writer typed it, in Markdown.')
    body_html = serializers.SerializerMethodField(help_text='The same text as HTML, ready to show.')
    round_number = serializers.IntegerField(help_text='1, or 2 once the writer has answered an argument.')
    reply_count = serializers.SerializerMethodField(help_text='Published replies.')
    claims = serializers.SerializerMethodField()
    coupon = serializers.SerializerMethodField()
    arguments = serializers.SerializerMethodField(help_text='Most supported first.')

    class Meta:
        model = Article
        fields = [
            'slug',
            'title',
            'standfirst',
            'body',
            'body_html',
            'reading_minutes',
            'published_at',
            'replies_open',
            'round_number',
            'reply_count',
            'claims',
            'coupon',
            'arguments',
        ]

    def _coupon(self, article) -> dict:
        if not hasattr(self, '_coupon_state'):
            self._coupon_state = services.coupon_state(article, self.context.get('visitor'))
        return self._coupon_state

    @extend_schema_field(serializers.CharField())
    def get_body_html(self, article):
        return markdown(article.body)

    @extend_schema_field(serializers.IntegerField())
    def get_reply_count(self, article):
        return article.replies.published().count()

    @extend_schema_field(ClaimSerializer(many=True))
    def get_claims(self, article):
        return ClaimSerializer(self._coupon(article)['rows'], many=True).data

    @extend_schema_field(CouponSerializer())
    def get_coupon(self, article):
        return CouponSerializer(self._coupon(article)).data

    @extend_schema_field(ArgumentSerializer(many=True))
    def get_arguments(self, article):
        arguments = sorted(
            article.arguments.select_related('claim'), key=lambda argument: argument.supporter_count(), reverse=True
        )
        return ArgumentSerializer(arguments, many=True).data


class VoteSerializer(serializers.Serializer):
    """A tick on one claim"""

    choice = serializers.ChoiceField(choices=VoteChoice.choices)


class VoteResultSerializer(serializers.Serializer):
    """The claim after the tick, and where the coupon stands"""

    claim = ClaimSerializer()
    coupon = CouponSerializer()


class ReplySerializer(serializers.ModelSerializer):
    """A published reply"""

    class Meta:
        model = Reply
        fields = ['uuid', 'nickname', 'text', 'created_at']


class ReplyListQuerySerializer(serializers.Serializer):
    """Query parameters of the reply list"""

    argument = serializers.IntegerField(required=False, min_value=1)


class ReplyCreateSerializer(serializers.Serializer):
    """A reply a reader wants to post"""

    nickname = serializers.CharField(
        help_text=f'{services.NICKNAME_MIN} to {services.NICKNAME_MAX} characters. The only thing shown next '
        f'to the reply.'
    )
    text = serializers.CharField(help_text=f'{services.TEXT_MIN} to {services.TEXT_MAX} characters.')
    website = serializers.CharField(
        required=False,
        allow_blank=True,
        write_only=True,
        help_text='Leave this out or empty. It is a trap for bots that fill in every field: a reply that '
        'has it filled is answered as if it was accepted, and thrown away.',
    )

    def validate_nickname(self, value):
        value = ' '.join(value.split())
        if not services.NICKNAME_MIN <= len(value) <= services.NICKNAME_MAX:
            raise serializers.ValidationError(
                f'Pick a nickname between {services.NICKNAME_MIN} and {services.NICKNAME_MAX} characters.'
            )
        return value

    def validate_text(self, value):
        value = value.strip()
        if len(value) < services.TEXT_MIN:
            raise serializers.ValidationError('That is a bit short for an argument. Give the house a sentence or two.')
        if len(value) > services.TEXT_MAX:
            raise serializers.ValidationError(f'Keep it under {services.TEXT_MAX} characters. Yours is {len(value)}.')
        return value


class ReplyResultSerializer(serializers.Serializer):
    """What became of a posted reply"""

    status = serializers.ChoiceField(
        choices=ReplyStatus.choices,
        help_text='2 published: it is on the site. 3 rejected: `message` says why. '
        '4 waiting for the house: the writer will read it first.',
    )
    message = serializers.CharField(help_text='One sentence to show the reader.')
