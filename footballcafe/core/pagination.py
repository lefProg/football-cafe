from rest_framework.pagination import PageNumberPagination


class CafePagination(PageNumberPagination):
    """Pages of 20. `page_size` can raise that up to 100."""

    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100
