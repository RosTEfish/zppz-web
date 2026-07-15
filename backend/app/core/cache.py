from fastapi import Response


PUBLIC_API_CACHE_CONTROL = "public, max-age=30, s-maxage=30, stale-while-revalidate=60"
ANONYMOUS_BOOTSTRAP_CACHE_CONTROL = "public, max-age=0, s-maxage=30, stale-while-revalidate=60"


def set_public_api_cache(response: Response) -> None:
    response.headers["Cache-Control"] = PUBLIC_API_CACHE_CONTROL
