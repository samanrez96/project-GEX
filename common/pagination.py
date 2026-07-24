import math

from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class StandardPagination(PageNumberPagination):
    """
    Project-wide pagination class used by list ViewSets.

    Adds ``total_pages`` and ``page_size`` to the standard DRF envelope so
    that the JavaScript frontend can render page-number buttons without
    computing them from count and page_size on the client side.
    """

    page_size             = 25
    page_size_query_param = 'page_size'
    max_page_size         = 100

    def get_paginated_response(self, data):
        return Response({
            'count':       self.page.paginator.count,
            'next':        self.get_next_link(),
            'previous':    self.get_previous_link(),
            'page_size':   self.get_page_size(self.request),
            'total_pages': math.ceil(
                self.page.paginator.count / self.get_page_size(self.request)
            ),
            'results': data,
        })

    def get_paginated_response_schema(self, schema):
        return {
            'type': 'object',
            'properties': {
                'count':       {'type': 'integer'},
                'next':        {'type': 'string',  'nullable': True},
                'previous':    {'type': 'string',  'nullable': True},
                'page_size':   {'type': 'integer'},
                'total_pages': {'type': 'integer'},
                'results':     schema,
            },
        }
