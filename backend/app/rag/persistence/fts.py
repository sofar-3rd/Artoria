TS_CONFIG = "jiebacfg"


def tsvector_sql(param: str) -> str:
    return f"to_tsvector('{TS_CONFIG}', :{param})"


def tsquery_or_sql(param: str) -> str:
    """OR-joined tsquery over the lexemes of a natural-language string.

    Built from `to_tsvector` lexemes, NOT from `plainto_tsquery(...)::text`: pg_jieba emits a
    whitespace lexeme ' ' for every space, and `'a' | ' ' | 'b'` matches any chunk that contains a
    space. Each lexeme is quote_literal'd, so user text cannot inject tsquery operators. A query
    with no usable lexeme (stop words only) evaluates to NULL; `tsv @@ NULL` matches no rows, so the
    keyword route returns nothing and the dense route still works.
    """
    return (
        f"to_tsquery('{TS_CONFIG}', ("
        f"SELECT string_agg(quote_literal(l), ' | ') "
        f"FROM unnest(tsvector_to_array(to_tsvector('{TS_CONFIG}', :{param}))) AS l "
        f"WHERE btrim(l) <> ''))"
    )
