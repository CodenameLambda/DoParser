#!/usr/bin/env python3

import re


class ParseFail(Exception):
    pass


class RuleElement(object):
    def __init__(self, var):
        self.var = var

    def match(self, parser):
        raise NotImplemented()


class IncludedRule(RuleElement):
    def __init__(self, rule, pattern_args):
        self.rule = rule
        self.pattern_args = pattern_args
        super().__init__(None)

    def match(self, parser):
        return (
            parser.specification.rules[self.rule].match(
                parser,
                *self.pattern_args
            )
        )


class StringRule(RuleElement):
    def __init__(self, s):
        self.string = s
        super().__init__(None)

    def match(self, parser):
        return parser.consume_string(self.string)


class Rule(object):
    def __init__(self, pattern_args, choices):
        self.pattern_args = pattern_args
        self.choices = choices

    def match(self, parser, *args):
        if len(args) != len(self.pattern_args):
            raise TypeError()

        if args:
            x = {
                name: default
                for name, default in self.pattern_args
                if default is not None
            }
            x.update({
                nd[0]: v
                for nd, v in zip(self.pattern_args, args)
            })
            return Rule([], [
                [
                    args[x[j]] if j in x.keys() else j
                    for j in i
                ]
                for i in self.choices
            ]).parse(parser, *args)
        else:
            fails = []
            for i in self.choices:
                index = parser.index
                try:
                    varspace = {}
                    for j in i:
                        if j.var is not None:
                            varspace[j.var] = j.match(parser)
                        else:
                            j.match(parser)
                    # TODO: Actions
                    return parser.s[index:parser.index]
                except ParseFail as e:
                    fails.append(e)
            if len(fails) == 1:
                raise fails[0]
            else:
                raise ParseFail(
                    "All alternatives failed:\n    {}".format(
                        "\n    ".join(
                            i.args[0]
                            if len(i.args) != 0
                            else "(unknown)"
                            for i in fails
                        )
                    )
                )

    @staticmethod
    def parse(pattern_args, source, *, no_choice=False):
        if source.strip() == "...":
            return ImplementationBoundRule()
        out = Rule(pattern_args, [])
        if source.strip() == "":
            raise SyntaxError("rule source can't be empty.\n"
                              "Tip: Use '\"\"' instead.")
        try:
            current = []
            index = 0
            while index < len(source):
                i = source[index]
                if i in "\"'":
                    c = ""
                    index2 = index + 1
                    while True:
                        j = source[index2]
                        if j == i:
                            current.append(StringRule(c))
                            break
                        elif j == "\\":
                            if source[index2 + 1] == "x":
                                c += chr(
                                    int(source[index2 + 2:index2 + 4])
                                )
                            elif source[index2 + 1] == "n":
                                c += "\n"
                            elif source[index2 + 1] == "t":
                                c += "\t"
                            elif source[index2 + 1] == "\\":
                                c += "\\"
                            elif source[index2 + 1] in "\"'":
                                c += source[index2 + 1]
                            else:
                                raise SyntaxError(
                                    "unknown escape sequence"
                                )
                            index2 += 2
                        else:
                            c += j
                            index2 += 1
                    index = index2 + 1
                elif i == "|":
                    out.choices.append(current)
                    current = []
                    index += 1
                elif i == "$":
                    c = ""
                    index2 = index + 1
                    while index2 < len(source):
                        j = source[index2]
                        if not (j.isalpha() or j.isdigit()):
                            if c == "":
                                raise SyntaxError("empty identifier")
                            current[-1].var = c
                        else:
                            c += j
                            index2 += 1
                    index = index2
                elif i == "<":
                    ps = []
                    c = ""
                    index2 = index + 1
                    while True:
                        j = source[index2]
                        if j == ">":
                            if c == "":
                                raise SyntaxError("too many commas")
                            if isinstance(current[-1], IncludedRule):
                                current[-1].pattern_args += [
                                    Rule.parse([], m, no_choice=True)
                                    for m in ps + [c]
                                ]
                            else:
                                raise SyntaxError(
                                    "a string doesn't have template "
                                    "arguments"
                                )
                            break
                        elif j == ",":
                            if c == "":
                                raise SyntaxError("too many commas")
                            ps.append(c)
                            c = ""
                            index2 += 1
                        else:
                            c += j
                            index2 += 1
                    index = index2 + 1
                elif i.isspace():
                    index += 1
                else:
                    name = i
                    index2 = index + 1
                    while index2 < len(source):
                        j = source[index2]
                        if j.isspace() or j in "\"'<>|":
                            current.append(IncludedRule(name, []))
                            break
                        else:
                            name += j
                            index2 += 1
                    if index2 == len(source):
                        current.append(IncludedRule(name, []))
                    index = index2
                # TODO: Parse actions
            out.choices.append(current)
            if no_choice and len(out.choices) != 1:
                raise SyntaxError("choices are not allowed")
        except IndexError:
            raise SyntaxError("unexpected end")

        return out


class ImplementationBoundRule(Rule):
    def __init__(self, implementation=None):
        super().__init__([], "")
        self.implementation = implementation

    def match(self, parser, *args):
        self.implementation(parser, *args)


_rule_re = re.compile(
    r"^"
    r"([^<>=, ]+) *"
    r"(< *([^<>=, ]+( *= *([^<>=, ]+))?) *"
    r"(, *([^<>=, ]+( *= *[^<>=, ]+)?))* *>)? "
    r" *= *(.+)$"
)


class Specification(object):
    def __init__(self, source: str):
        self.rules = {}
        for i in (i.strip() for i in source.split("\n")):
            if i == "":
                continue
            if not _rule_re.match(i):
                raise SyntaxError("formal error")
            pattern_args = []
            current_parg = [""]
            mode = "name"
            name = ""
            implementation = ""
            for j in i:
                if mode == "name":
                    if j == "<":
                        mode = "pattern_args"
                    elif j == "=":
                        mode = "implementation"
                    elif not j.isspace():
                        name += j
                elif mode == "pattern_args":
                    if j == ">":
                        mode = "preimplementation"
                    elif j == "=":
                        current_parg.append("")
                    elif j == ",":
                        if len(current_parg) < 2:
                            current_parg.append(None)
                        pattern_args.append(tuple(current_parg))
                        current_parg = [""]
                    elif not j.isspace():
                        current_parg[-1] += j
                elif mode == "preimplementation":
                    if j == "=":
                        pattern_args.append(tuple(current_parg))
                        mode = "implementation"
                else:
                    implementation += j
            if implementation == "...":
                self.rules[name] = ImplementationBoundRule()
            else:
                self.rules[name] = Rule.parse(
                    pattern_args,
                    implementation
                )


class Parser(object):
    def __init__(self, specification):
        self.specification = specification
        self.s = None
        self.index = None
        self.jump_back = None
        self.choices = None

    def parse(self, s, p):
        self.s = s
        self.index = 0
        self.choices = []
        return self.consume_pattern(p)

    def consume_char(self):
        self.index += 1
        return self.s[self.index - 1]

    def consume_string(self, s):
        l = len(s)
        self.index += l
        if self.s[self.index - l:self.index] != s:
            raise ParseFail(
                "Expected {!r}, saw {!r}".format(
                    s,
                    self.s[self.index - l:self.index]
                )
            )
        else:
            return s

    def consume_pattern(self, pattern, *args):
        return self.specification.rules[pattern].match(self, *args)

    def _lookahead(self, pattern):
        jump_back = self.index
        x = self.consume_pattern(pattern)
        self.index = jump_back
        return x
