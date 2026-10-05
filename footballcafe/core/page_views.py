"""The pages people read. They only show things: every vote and reply goes through the API (views.py)."""

from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.views.decorators.csrf import ensure_csrf_cookie

from core import services
from core.models import Article


def _piece_context(request, article, nav='') -> dict:
    arguments = sorted(
        article.arguments.select_related('claim'),
        key=lambda argument: argument.supporter_count(),
        reverse=True,
    )
    return {
        'nav': nav,
        'article': article,
        'coupon': services.coupon_state(article, services.get_visitor(request)),
        'arguments': arguments,
        'answered': [argument for argument in arguments if argument.house_reply],
        'reply_count': article.replies.published().count(),
        'text_max': services.TEXT_MAX,
        'nickname_max': services.NICKNAME_MAX,
    }


@ensure_csrf_cookie
def home(request):
    article = Article.objects.published().first()
    if article is None:
        return render(request, 'empty.html', {'nav': 'home'})
    return render(request, 'article.html', _piece_context(request, article, nav='home'))


@ensure_csrf_cookie
def article(request, slug):
    article = get_object_or_404(Article, slug=slug)
    # A draft is a page only the house can open, to see the piece as readers will.
    if not article.is_published and not request.user.is_staff:
        raise Http404
    return render(request, 'article.html', _piece_context(request, article))


def past_rounds(request):
    pieces = Article.objects.published().with_reply_count()
    return render(request, 'past_rounds.html', {'pieces': pieces, 'nav': 'past'})


def replies(request, slug):
    article = get_object_or_404(Article.objects.published(), slug=slug)
    published = article.replies.published()
    argument = None
    if request.GET.get('argument', '').isdigit():
        argument = article.arguments.filter(id=request.GET['argument']).first()
    if argument:
        published = published.filter(arguments=argument)
    return render(
        request,
        'replies.html',
        {'article': article, 'replies': published, 'argument': argument, 'reply_count': published.count()},
    )


def house_rules(request):
    return render(request, 'house_rules.html', {'nav': 'rules'})
