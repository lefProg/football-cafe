import logging
import uuid

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, Throttled
from rest_framework.generics import GenericAPIView, ListAPIView, ListCreateAPIView, RetrieveAPIView
from rest_framework.response import Response

from core import services
from core.enums import ReplyStatus
from core.models import Article
from core.serializers import (
    ClaimSerializer,
    CouponSerializer,
    PieceDetailSerializer,
    PieceListSerializer,
    ReplyCreateSerializer,
    ReplyListQuerySerializer,
    ReplyResultSerializer,
    ReplySerializer,
    VoteResultSerializer,
    VoteSerializer,
)

logger = logging.getLogger(__name__)

_NO_PIECE = OpenApiResponse(
    description='No published piece with this slug. Drafts and pieces dated in the future are not public.'
)
_VOTE_400 = OpenApiResponse(
    description='Validation error:<br>'
    '`{"choice": ["This field is required."]}`<br>'
    '`{"choice": ["\\"3\\" is not a valid choice."]}`'
)
_REPLY_400 = OpenApiResponse(
    description='Validation error, keyed by field:<br>'
    '`{"nickname": ["Pick a nickname between 2 and 30 characters."]}`<br>'
    '`{"text": ["That is a bit short for an argument. Give the house a sentence or two."]}`<br>'
    '`{"text": ["Keep it under 1200 characters. Yours is 1340."]}`'
)


def published_piece(slug: str) -> Article:
    return get_object_or_404(Article.objects.published(), slug=slug)


@extend_schema_view(
    get=extend_schema(
        summary='List the published pieces',
        description='Every piece the public can read, newest first. Drafts and pieces dated in the future '
        'are left out. Paginated: 20 per page, `page_size` up to 100.',
        responses={200: PieceListSerializer(many=True)},
    ),
)
class PieceListView(ListAPIView):
    serializer_class = PieceListSerializer

    def get_queryset(self):
        return Article.objects.published().with_reply_count()


@extend_schema_view(
    get=extend_schema(
        summary='Read one piece',
        description='The piece, its claims and the arguments readers make against it.<br>'
        'The `claims` are personal to the reader behind the `fc_visitor` cookie: `my_choice` is '
        'their tick, and `percent_agree` / `vote_count` stay hidden (null / 0) on a claim until '
        'they have ticked it, so nobody votes with the crowd. Without the cookie every claim '
        'comes back unticked.',
        responses={200: PieceDetailSerializer, 404: _NO_PIECE},
    ),
)
class PieceDetailView(RetrieveAPIView):
    serializer_class = PieceDetailSerializer
    lookup_field = 'slug'

    def get_queryset(self):
        return Article.objects.published()

    def get_serializer_context(self):
        return {**super().get_serializer_context(), 'visitor': services.get_visitor(self.request)}


class ClaimVoteView(GenericAPIView):
    serializer_class = VoteSerializer

    @extend_schema(
        summary='Tick agree or disagree on a claim',
        description='`choice`: 1 agree, 2 disagree. Voting again on the same claim replaces the earlier tick.'
        '<br>The first vote sets the signed `fc_visitor` cookie (one year, HttpOnly). Send it '
        'back on later requests, or every vote counts as a new reader.<br>'
        'The response is the claim with its split now visible, and the state of the coupon: '
        '`coupon.verdict` is filled once every claim of the piece is ticked.',
        request=VoteSerializer,
        responses={
            200: VoteResultSerializer,
            400: _VOTE_400,
            404: OpenApiResponse(
                description='No published piece with this slug, or the piece has no claim at this position.'
            ),
        },
    )
    def post(self, request, slug, position):
        article = published_piece(slug)
        claim = get_object_or_404(article.claims, position=position)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        visitor = services.get_visitor(request) or uuid.uuid4()
        services.cast_vote(claim, visitor, serializer.validated_data['choice'])

        coupon = services.coupon_state(article, visitor)
        row = next(row for row in coupon['rows'] if row['claim'].id == claim.id)
        response = Response({'claim': ClaimSerializer(row).data, 'coupon': CouponSerializer(coupon).data})
        services.remember_visitor(response, visitor)
        return response


@extend_schema_view(
    get=extend_schema(
        summary='List the published replies to a piece',
        description='What readers wrote back, oldest first. Only replies that passed moderation. '
        'Paginated: 20 per page, `page_size` up to 100.',
        parameters=[
            OpenApiParameter(
                name='argument',
                type=int,
                location=OpenApiParameter.QUERY,
                required=False,
                description='Only the replies behind this argument (an `id` from the `arguments` of the piece). '
                'An id that is not an argument of this piece gives an empty list.',
            )
        ],
        responses={
            200: ReplySerializer(many=True),
            400: OpenApiResponse(description='`{"argument": ["A valid integer is required."]}`'),
            404: _NO_PIECE,
        },
    ),
    post=extend_schema(
        summary='Post a reply to a piece',
        description='No login: send a nickname and the text. A moderator agent reads the reply before '
        'anything is shown, so the request takes a few seconds, and answers with one of three '
        'statuses: 2 published, 3 rejected (`message` says what to change), 4 waiting for the '
        'house (the writer reads it personally; also the answer when the moderator cannot be '
        'reached).<br>'
        'Sets the `fc_visitor` cookie like a vote does. One reader can post 3 replies in ten '
        'minutes.',
        request=ReplyCreateSerializer,
        responses={
            201: ReplyResultSerializer,
            400: _REPLY_400,
            403: OpenApiResponse(description='`{"detail": "Replies to this piece are closed."}`'),
            404: _NO_PIECE,
            429: OpenApiResponse(
                description='`{"detail": "You have posted a few replies in a row. '
                'Give it ten minutes, then come back."}`'
            ),
        },
    ),
)
class ReplyListCreateView(ListCreateAPIView):
    def get_serializer_class(self):
        return ReplyCreateSerializer if self.request.method == 'POST' else ReplySerializer

    def get_queryset(self):
        article = published_piece(self.kwargs['slug'])
        query = ReplyListQuerySerializer(data=self.request.query_params)
        query.is_valid(raise_exception=True)
        replies = article.replies.published()
        if 'argument' in query.validated_data:
            replies = replies.filter(arguments__id=query.validated_data['argument'], arguments__article=article)
        return replies

    def create(self, request, *args, **kwargs):
        article = published_piece(self.kwargs['slug'])
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        if data.get('website'):
            # A bot filled the hidden field. It hears what a person would hear, and nothing is stored.
            body = {'status': ReplyStatus.REVIEW, 'message': services.WAITING_MESSAGE}
            return Response(ReplyResultSerializer(body).data, status=status.HTTP_201_CREATED)

        visitor = services.get_visitor(request) or uuid.uuid4()
        try:
            reply = services.submit_reply(
                article, visitor, data['nickname'], data['text'], ip=request.META.get('REMOTE_ADDR', '')
            )
        except services.RepliesClosed as error:
            raise PermissionDenied(str(error))
        except services.TooManyReplies as error:
            raise Throttled(detail=str(error))

        body = {'status': reply.status, 'message': services.reader_message(reply)}
        response = Response(ReplyResultSerializer(body).data, status=status.HTTP_201_CREATED)
        services.remember_visitor(response, visitor)
        return response
