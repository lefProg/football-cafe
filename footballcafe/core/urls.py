from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from core.views import ClaimVoteView, PieceDetailView, PieceListView, ReplyListCreateView

urlpatterns = [
    path('schema/', SpectacularAPIView.as_view(), name='schema'),
    path('swagger/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path(
        'pieces/',
        include(
            [
                path('', PieceListView.as_view(), name='piece-list'),
                path('<slug:slug>/', PieceDetailView.as_view(), name='piece-detail'),
                path('<slug:slug>/claims/<int:position>/vote/', ClaimVoteView.as_view(), name='claim-vote'),
                path('<slug:slug>/replies/', ReplyListCreateView.as_view(), name='piece-replies'),
            ]
        ),
    ),
]
