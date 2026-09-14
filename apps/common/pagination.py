from rest_framework.pagination import PageNumberPagination


class StandardPagination(PageNumberPagination):
    page_size = 24
    page_size_query_param = "page_size"
    # Cheklov bo'lmasa kimdir ?page_size=100000 yuborib bazani qotiradi
    max_page_size = 100
