def parse_response(response: dict) -> tuple[list[str], int | None]:
    return response.get("data", []), response.get("nextCursor")
