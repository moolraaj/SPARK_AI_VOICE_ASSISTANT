from math import ceil


def pagination_response(
    total_records: int,
    page: int,
    limit: int,
):
    total_pages = ceil(total_records / limit)

    return {
        "page": page,
        "limit": limit,
        "total_records": total_records,
        "total_pages": total_pages,
        "has_previous": page > 1,
        "has_next": page < total_pages,
    }