def any(parser):
    return parser.consume_char()


def lookahead(parser, pattern):
    return parser._lookahead(pattern)
