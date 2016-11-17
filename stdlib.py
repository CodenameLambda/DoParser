import parser as p


def any(parser):
    return parser.consume_char()


def lookahead(parser, pattern):
    return parser._lookahead(pattern)


def lowercase(parser):
    c = parser.consume_char()
    if c.islower():
        return c
    else:
        raise p.ParseFail("Expected lowercase character")


def uppercase(parser):
    c = parser.consume_char()
    if c.isupper():
        return c
    else:
        raise p.ParseFail("Expected uppercase character")


def numeric(parser):
    c = parser.consume_char()
    if c.isnumeric():
        return c
    else:
        raise p.ParseFail("Expected numeric character")
