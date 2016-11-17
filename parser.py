#!/usr/bin/env python3

import re


class ParseFail(Exception):
    pass


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
            for i in self.choices:
                for j in i:
                    pass # TODO
                    # if (works):
                    #     return x
                    # else:
                    #     break

    @staticmethod
    def parse(pattern_args, source, *, no_choice=False):
        self = Rule(pattern_args, [])
        current = []
        if source.strip() == "":
            raise SyntaxError("rule source can't be empty.\n"
                              "Tip: Use '\"\"' instead.")
        try:
            index = 0
            while index < len(source):
                i = source[index]
                if i in "\"'":
                    c = ""
                    index2 = index + 1
                    while True:
                        j = source[index2]
                        if j == i:
                            current.append((True, c, [], None))
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
                    self.choices.append(current)
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
                            current[-1] = current[-1][:-1] + (c,)
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
                            l = current[-1][2]
                            l += [
                                Rule.parse([], m, no_choice=True)
                                for m in ps + [c]
                                ]
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
                            current.append((False, name, [], None))
                            break
                        else:
                            name += j
                            index2 += 1
                    if index2 == len(source):
                        current.append((False, name, [], None))
                    index = index2
            self.choices.append(current)
            if no_choice and len(self.choices) != 1:
                raise SyntaxError("choices are not allowed")
        except IndexError:
            raise SyntaxError("unexpected end")


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

    def consume_pattern(self, pattern, *args):
        return self.specification.rules[pattern].match(self, *args)

    def _lookahead(self, pattern):
        jump_back = self.index
        x = self.consume_pattern(pattern)
        self.index = jump_back
        return x
