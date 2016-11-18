import parser

print(parser.File("test.dparse").parse(
    open("test.src", 'r').read(),
    closed=False
))
