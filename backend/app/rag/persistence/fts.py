TS_CONFIG = "jiebacfg"


def tsvector_sql(param: str) -> str:
    return f"to_tsvector('{TS_CONFIG}', :{param})"


def tsquery_or_sql(param: str) -> str:
    return (
        f"to_tsquery('{TS_CONFIG}', "
        f"replace(plainto_tsquery('{TS_CONFIG}', :{param})::text, ' & ', ' | '))"
    )
