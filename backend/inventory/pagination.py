import math

from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class ProductPagination(PageNumberPagination):
    page_size             = 75
    page_size_query_param = "page_size"
    max_page_size         = 100

    def get_paginated_response(self, data):
        return Response({
            "count":       self.page.paginator.count,
            "next":        self.get_next_link(),
            "previous":    self.get_previous_link(),
            "page_size":   self.get_page_size(self.request),
            "total_pages": math.ceil(
                self.page.paginator.count / self.get_page_size(self.request)
            ),
            "results":     data,
        })

    def get_paginated_response_schema(self, schema):
        return {
            "type": "object",
            "properties": {
                "count":       {"type": "integer"},
                "next":        {"type": "string", "nullable": True},
                "previous":    {"type": "string", "nullable": True},
                "page_size":   {"type": "integer"},
                "total_pages": {"type": "integer"},
                "results":     schema,
            },
        }


class ProductListPagination(ProductPagination):
    """Pagination for the product list admin UI.

    Default page_size=150 so all 150 demo medicines fit on one page.
    Callers may pass ?page_size=N up to max_page_size.
    """
    page_size     = 150
    max_page_size = 200
